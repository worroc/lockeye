import argparse
import logging
import re
import sys
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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


def has_workitem(message: str, pattern: str, case_sensitive: bool = False) -> bool:
    body = _strip_comments(message)
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.search(pattern, body, flags) is not None


def missing_patterns(message: str, patterns: Sequence[str], case_sensitive: bool = False) -> List[str]:
    """Return the patterns from `patterns` that do not match the message."""
    return [p for p in patterns if not has_workitem(message, p, case_sensitive)]


def _read_message(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="", add_help=False)
    env_group = parser.add_argument_group("env options")
    env_group.add_argument("--log-level", default="info", help="log level output")
    env_group.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        default=[],
        metavar="REGEX",
        help="regex the commit message must contain; repeat to require several patterns",
    )
    env_group.add_argument(
        "--case-sensitive",
        action="store_true",
        help="match pattern case-sensitively (default: case-insensitive)",
    )
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

    patterns = args.get("patterns", [])
    if not patterns:
        print(
            highlight_error("no pattern configured; pass at least one `--pattern <regex>` (e.g. --pattern 'AB#\\d+')")
        )
        sys.exit(1)

    case_sensitive = args.get("case_sensitive", False)
    message = _read_message(files[0])
    missing = missing_patterns(message, patterns, case_sensitive)
    if not missing:
        return

    for pattern in missing:
        print(highlight_error(f"commit message must contain a work item matching `{pattern}`"))
    sys.exit(1)


if __name__ == "__main__":
    main()
