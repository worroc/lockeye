import argparse
import logging
import re
import subprocess
import sys
from collections import defaultdict, namedtuple
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Sequence, Set

# Default comment introducers per file extension. For a file of a known type
# the marker matches ONLY when it appears (as a whole token) after one of these
# on the line. Files with an unknown extension, or no extension at all, match
# the marker anywhere on the line.
DEFAULT_COMMENT_SYNTAX: Dict[str, List[str]] = {
    ".py": ["#"],
    ".sh": ["#"],
    ".bash": ["#"],
    ".zsh": ["#"],
    ".yaml": ["#"],
    ".yml": ["#"],
    ".toml": ["#"],
    ".cfg": ["#"],
    ".ini": ["#"],
    ".rb": ["#"],
    ".pl": ["#"],
    ".r": ["#"],
    ".js": ["//", "/*"],
    ".ts": ["//", "/*"],
    ".jsx": ["//", "/*"],
    ".tsx": ["//", "/*"],
    ".go": ["//", "/*"],
    ".c": ["//", "/*"],
    ".h": ["//", "/*"],
    ".cpp": ["//", "/*"],
    ".hpp": ["//", "/*"],
    ".cc": ["//", "/*"],
    ".java": ["//", "/*"],
    ".rs": ["//", "/*"],
    ".cs": ["//", "/*"],
    ".php": ["//", "/*", "#"],
    ".swift": ["//", "/*"],
    ".kt": ["//", "/*"],
    ".scala": ["//", "/*"],
    ".md": ["<!--"],
    ".markdown": ["<!--"],
    ".html": ["<!--"],
    ".htm": ["<!--"],
    ".xml": ["<!--"],
    ".vue": ["<!--"],
    ".rst": [".."],
    ".sql": ["--"],
    ".lua": ["--"],
}

# Files never scanned for the marker (they legitimately contain it as config).
DEFAULT_EXCLUDE: Set[str] = {".pre-commit-config.yaml"}

logger = logging.getLogger(__name__)

Location = namedtuple("Location", ["file", "line", "lstrip"])

start_color = {"red": "\x1b[0;31m", "green": "\x1b[0;32m", "magenta": "\x1b[36m"}
end_color = "\x1b[0m"


def _color(color: str, text: str):
    return f"{start_color[color]}{text}{end_color}"


highlight_file = partial(_color, "red")
highlight_info = partial(_color, "green")


Match = namedtuple("Match", ["file", "matched_lines"])


def make_marker_re(marker: str, case_sensitive: bool = False) -> Pattern[str]:
    """Compile a whole-word matcher for `marker`.

    Look-arounds require the marker not be flanked by word characters, so it is
    found even when glued to comment delimiters (`/*no-commit*/`,
    `<!--no-commit-->`) yet never as a substring of a longer word
    (`no-committed`, `xno-commit`).
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", flags)


def _comment_body(content: str, introducers: List[str]) -> Optional[str]:
    """Return the line portion at/after the earliest comment introducer,
    or None when the line has no comment for this file type."""
    positions = [content.find(intro) for intro in introducers]
    positions = [p for p in positions if p != -1]
    if not positions:
        return None
    return content[min(positions) :]


def _line_matches(file: Path, content: str, marker_re: Pattern[str], comment_syntax: Dict[str, List[str]]) -> bool:
    introducers = comment_syntax.get(file.suffix.lower())
    if not introducers:
        # unknown or missing extension: match the marker anywhere on the line
        return marker_re.search(content) is not None
    body = _comment_body(content, introducers)
    if body is None:
        return False
    return marker_re.search(body) is not None


def build_comment_syntax(args: Dict) -> Dict[str, List[str]]:
    """Start from the built-in map, then apply `--comment EXT=SYNTAX` overrides."""
    syntax = {ext: list(intros) for ext, intros in DEFAULT_COMMENT_SYNTAX.items()}
    for entry in args.get("comment", []):
        ext, _, intros = entry.partition("=")
        syntax[ext.lower()] = [s for s in intros.split(",") if s]
    return syntax


def build_exclude(args: Dict) -> Set[str]:
    return set(DEFAULT_EXCLUDE) | set(args.get("exclude", []))


def _read_cached_diff() -> Optional[str]:
    res = subprocess.run("git diff --cached", shell=True, capture_output=True)
    if res.returncode:
        return None
    return res.stdout.decode("utf-8")


def _parse_diff_file(line: str) -> Path:
    # `diff --git a/exclude_marked/main.py b/exclude_marked/main.py`
    return Path(line.split(" ")[-1][2:].strip())


def _is_excluded(file: Path, exclude: Set[str]) -> bool:
    return file.name in exclude or str(file) in exclude


def _scan_diff(
    diff: str,
    marker_re: Pattern[str],
    comment_syntax: Dict[str, List[str]],
    exclude: Set[str],
) -> Dict[Path, List[str]]:
    file_2_matches: Dict[Path, List[str]] = defaultdict(list)
    file = Path("")
    skip = False

    for line in diff.split("\n"):
        if line.startswith("diff --git"):
            file = _parse_diff_file(line)
            skip = _is_excluded(file, exclude)
            logger.debug(f"file: {file} (skip={skip})")
            continue
        if skip or line.startswith("+++") or not line.startswith("+"):
            continue
        content = line[1:].lstrip()
        if _line_matches(file, content, marker_re, comment_syntax):
            file_2_matches[file].append(line)

    return file_2_matches


def get_matches(args: Dict) -> List[Match]:
    case_sensitive = args.get("case_sensitive", False)
    marker_re = make_marker_re(args["marker"], case_sensitive)
    comment_syntax = build_comment_syntax(args)
    exclude = build_exclude(args)
    logger.debug(f"looking for marker `{args['marker']}` (case_sensitive={case_sensitive}, exclude={exclude})")

    diff = _read_cached_diff()
    if diff is None:
        return []
    if not marker_re.search(diff):
        return []

    file_2_matches = _scan_diff(diff, marker_re, comment_syntax, exclude)
    return [Match(file, lines) for file, lines in file_2_matches.items()]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="",
        add_help=False,
    )
    env_group = parser.add_argument_group("env options")
    env_group.add_argument("--log-level", default="info", help="log level output")
    env_group.add_argument("--marker", default="no-commit", help="marker to discard from commit")
    env_group.add_argument(
        "--case-sensitive",
        action="store_true",
        help="match marker case-sensitively (default: case-insensitive)",
    )
    env_group.add_argument(
        "--comment",
        action="append",
        default=[],
        metavar="EXT=SYNTAX",
        help="add/override comment syntax for a file extension, "
        "e.g. --comment .vue=<!-- or --comment .foo=//,/* (repeatable)",
    )
    env_group.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="FILE",
        help="filename or path to skip entirely (repeatable); .pre-commit-config.yaml is always excluded",
    )
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
