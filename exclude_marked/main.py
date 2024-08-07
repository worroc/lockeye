import argparse
import logging
import subprocess
import sys
from collections import defaultdict, namedtuple
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

Location = namedtuple("Location", ["file", "line", "lstrip"])

start_color = {"red": "\x1b[0;31m", "green": "\x1b[0;32m", "magenta": "\x1b[36m"}
end_color = "\x1b[0m"


def _color(color: str, text: str):
    return f"{start_color[color]}{text}{end_color}"


highlight_file = partial(_color, "red")
highlight_info = partial(_color, "green")


Match = namedtuple("Match", ["file", "matched_lines"])


def get_matches(
    args: Dict,
) -> List[Match]:
    marker = args["marker"].lower()
    command = "git diff --cached"
    logger.debug(f"looking for marker `{marker}` in diffs {command}")
    res = subprocess.run(command, shell=True, capture_output=True)
    if res.returncode:
        return []
    res = res.stdout.decode("utf-8")
    if marker not in res.lower():
        return []

    lines = res.split("\n")

    matches: List[Match] = []
    file_2_matches = defaultdict(list)
    file = ""

    for line in lines:
        if line.startswith("diff --git"):
            # `diff --git a/exclude_marked/main.py b/exclude_marked/main.py`
            logger.debug(f"file: {line}")
            file = Path(line.split(" ")[-1][2:].strip())
            continue

        if line.startswith("+") and marker in line.lower():
            # `+zx        args: ["--marker=NO-COMMIT", "--log-level", "DEBUG"]`
            file_2_matches[file].append(line)

    for file, lines in file_2_matches.items():
        matches.append(Match(file, lines))

    return matches


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="",
        add_help=False,
    )
    env_group = parser.add_argument_group("env options")
    env_group.add_argument("--log-level", default="info", help="log level output")
    env_group.add_argument("--marker", default="no-commit", help="marker to discard from commit (case insensitive)")
    target_group = parser.add_argument_group("target options")
    target_group.add_argument("files", nargs="*", help="One or more source files.")
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = _build_arg_parser()
    arguments = {key: value for key, value in vars(parser.parse_args(argv)).items() if value}
    return arguments


def config_logger(args):
    ll = args["log_level"].upper()
    numeric_level = getattr(logging, ll.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    logging.basicConfig(
        format="%(levelname)s %(module)s.%(funcName)s:%(lineno)d # %(message)s", encoding="utf-8", level=numeric_level
    )


def main():
    args = parse_args()
    config_logger(args)
    logger.debug(f"running from: '{__file__}'")
    logger.debug(f"Arguments: {args}")
    matches = get_matches(args)
    root = Path().cwd()
    logger.debug(f"working on directory: {root}")
    failed = False
    if matches:
        for match in matches:
            print(highlight_file(f"File: {match.file}"))
            subprocess.run(f"git reset -- {match.file}", shell=True, capture_output=True)
            for line in match.matched_lines:
                print(line)
            failed = failed or True

    if failed:
        print(highlight_info("files were excluded from commit"))
        sys.exit(1)


if __name__ == "__main__":
    main()
