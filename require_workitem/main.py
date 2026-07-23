import argparse
import logging
import re
import sys
from functools import partial
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

logger = logging.getLogger(__name__)

start_color = {"red": "\x1b[0;31m", "green": "\x1b[0;32m", "magenta": "\x1b[36m"}
end_color = "\x1b[0m"


def _color(color: str, text: str):
    return f"{start_color[color]}{text}{end_color}"


highlight_error = partial(_color, "red")
highlight_info = partial(_color, "green")


def _strip_comments(message: str) -> str:
    lines = [line for line in message.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines)


def has_workitem(message: str, pattern: str) -> bool:
    body = _strip_comments(message)
    return re.search(pattern, body, re.IGNORECASE) is not None


def _read_message(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="", add_help=False)
    env_group = parser.add_argument_group("env options")
    env_group.add_argument("--log-level", default="info", help="log level output")
    env_group.add_argument("--pattern", default=r"AB#\d+", help="regex the commit message must contain")
    target_group = parser.add_argument_group("target options")
    target_group.add_argument("files", nargs="*", help="commit message file (passed by pre-commit).")
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

    files = args.get("files", [])
    if not files:
        print(highlight_error("no commit message file passed; use stage `commit-msg`"))
        sys.exit(1)

    pattern = args["pattern"]
    message = _read_message(files[0])
    if has_workitem(message, pattern):
        return

    print(highlight_error(f"commit message must contain a work item matching `{pattern}` (e.g. AB#1234)"))
    sys.exit(1)


if __name__ == "__main__":
    main()
