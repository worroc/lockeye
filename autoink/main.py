import argparse
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

logger = logging.getLogger(__name__)

# Matches: lockeye: autoink <integer> (<ISO-timestamp>)
# e.g. "# lockeye: autoink 42 (2026-04-16T10:30:00Z)"
AUTOINK_RE = re.compile(r"(lockeye:\s+autoink)\s+(\d+)\s+\((\S+)\)")

start_color = {"red": "\x1b[0;31m", "green": "\x1b[0;32m"}
end_color = "\x1b[0m"


def _color(color: str, text: str):
    return f"{start_color[color]}{text}{end_color}"


def _get_repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip())


def _get_committed_content(rel_path: str, repo_root: Path) -> Optional[str]:
    """Get file content from the last commit (HEAD)."""
    result = subprocess.run(
        ["git", "show", f"HEAD:{rel_path}"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _find_marker(lines: list[str]) -> Optional[int]:
    """Return the line index of the first lockeye: autoink directive, or None."""
    for i, line in enumerate(lines):
        if AUTOINK_RE.search(line):
            return i
    return None


def _find_next_nonblank(lines: list[str], after_idx: int) -> Optional[int]:
    """Return the index of the first non-blank line after *after_idx*, or None."""
    for i in range(after_idx + 1, len(lines)):
        if lines[i].strip():
            return i
    return None


def _extract_version(line: str) -> Optional[int]:
    """Extract the integer value from an autoink directive line."""
    match = AUTOINK_RE.search(line)
    return int(match.group(2)) if match else None


def _extract_timestamp(line: str) -> Optional[str]:
    """Extract the timestamp from an autoink directive line."""
    match = AUTOINK_RE.search(line)
    return match.group(3) if match else None


def _build_marker_line(line: str, new_version: int, timestamp: str) -> str:
    """Replace the version and timestamp in a marker line, keeping everything else."""
    match = AUTOINK_RE.search(line)
    if not match:
        return line
    before = line[: match.start(2)]
    suffix = line[match.end(3) + 1 :]  # +1 to skip closing ')'
    return f"{before}{new_version} ({timestamp}){suffix}"


def check_file(file_path: Path, repo_root: Path) -> Optional[str]:
    """Check a single file for autoink directive.

    Returns a message string if the file was modified or misconfigured,
    None if no action was needed.
    """
    try:
        content = file_path.read_text()
    except Exception as e:
        logger.debug(f"Cannot read {file_path}: {e}")
        return None

    lines = content.splitlines(keepends=True)

    marker_idx = _find_marker(lines)
    if marker_idx is None:
        return None

    marker_line = lines[marker_idx]
    staged_version = _extract_version(marker_line)
    if staged_version is None:
        return _color(
            "red",
            f"{file_path}:{marker_idx + 1}: "
            "autoink directive malformed (expected: lockeye: autoink <int> (<timestamp>))",
        )

    # Get committed content
    try:
        rel_path = file_path.resolve().relative_to(repo_root)
    except ValueError:
        logger.debug(f"{file_path}: not under repo root")
        return None

    committed_content = _get_committed_content(str(rel_path), repo_root)
    if committed_content is None:
        logger.debug(f"{file_path}: not in HEAD, skipping")
        return None

    committed_lines = committed_content.splitlines(keepends=True)
    committed_marker_idx = _find_marker(committed_lines)
    if committed_marker_idx is None:
        logger.debug(f"{file_path}: no autoink marker in committed version")
        return None

    # Compare the full marker line (stripped) between staged and committed
    committed_marker_line = committed_lines[committed_marker_idx]
    if marker_line.strip() != committed_marker_line.strip():
        logger.debug(f"{file_path}: marker line already changed, skipping")
        return None

    # Same marker line → file changed but version not bumped → auto-increment
    old_version = staged_version
    old_timestamp = _extract_timestamp(marker_line)
    new_version = old_version + 1
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines[marker_idx] = _build_marker_line(marker_line, new_version, now_utc)

    # Mirror: update the next non-blank line if it contains the old value
    next_idx = _find_next_nonblank(lines, marker_idx)
    if next_idx is not None:
        next_line = lines[next_idx]
        old_full = f"{old_version} ({old_timestamp})"
        new_full = f"{new_version} ({now_utc})"
        if old_full in next_line:
            lines[next_idx] = next_line.replace(old_full, new_full, 1)
        elif str(old_version) in next_line:
            lines[next_idx] = next_line.replace(str(old_version), str(new_version), 1)

    file_path.write_text("".join(lines))

    return _color(
        "green",
        f"{file_path}:{marker_idx + 1}: version auto-incremented {old_version} -> {new_version}",
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Auto-increment version in files marked with lockeye: autoink",
        add_help=False,
    )
    parser.add_argument("--log-level", default="info", help="log level")
    parser.add_argument("files", nargs="*", help="Files to check")
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = _build_arg_parser()
    return vars(parser.parse_args(argv))


def config_logger(args):
    ll = args.get("log_level", "info").upper()
    numeric_level = getattr(logging, ll, logging.INFO)
    logging.basicConfig(
        format="%(levelname)s %(module)s.%(funcName)s:%(lineno)d # %(message)s",
        encoding="utf-8",
        level=numeric_level,
    )


def main():
    args = parse_args()
    config_logger(args)
    logger.debug(f"Arguments: {args}")

    repo_root = _get_repo_root()
    messages = []

    for file_arg in args.get("files", []):
        file_path = Path(file_arg)
        if not file_path.is_file():
            continue
        msg = check_file(file_path, repo_root)
        if msg:
            messages.append(msg)

    if messages:
        for msg in messages:
            print(msg)
        print("Stage the updated file(s) and commit again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
