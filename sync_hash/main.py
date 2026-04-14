import argparse
import hashlib
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

logger = logging.getLogger(__name__)

SYNC_HASH_RE = re.compile(r"lockeye:\s+sync-hash\s+(\w+)\s+([0-9a-f]+)\s+(.+)")

start_color = {"red": "\x1b[0;31m", "green": "\x1b[0;32m"}
end_color = "\x1b[0m"


def _color(color: str, text: str):
    return f"{start_color[color]}{text}{end_color}"


REPO_PREFIX = "repo://"


def compute_hash(method: str, file_path: Path) -> str:
    h = hashlib.new(method)
    h.update(file_path.read_bytes())
    return h.hexdigest()


def _get_repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip())


def _resolve_source_path(ref_file: Path, raw_path: str) -> Path:
    """Resolve a sync-hash source path.

    - repo://path — relative to git repo root
    - /absolute   — rejected (raises ValueError)
    - relative    — relative to the referencing file's directory
    """
    if raw_path.startswith(REPO_PREFIX):
        return (_get_repo_root() / raw_path[len(REPO_PREFIX) :]).resolve()
    if raw_path.startswith("/"):
        raise ValueError(f"absolute paths not allowed: {raw_path}")
    return (ref_file.parent / raw_path).resolve()


def check_file(file_path: Path) -> list:
    """Check a single file for sync-hash directives. Return list of errors."""
    errors = []
    try:
        content = file_path.read_text()
    except Exception as e:
        logger.debug(f"Cannot read {file_path}: {e}")
        return errors

    for line_no, line in enumerate(content.splitlines(), 1):
        match = SYNC_HASH_RE.search(line)
        if not match:
            continue

        method = match.group(1)
        expected_hash = match.group(2)
        rel_path = match.group(3).strip()

        try:
            source_path = _resolve_source_path(file_path, rel_path)
        except ValueError as e:
            errors.append(f"{file_path}:{line_no}: {e}")
            continue
        if not source_path.is_file():
            errors.append(f"{file_path}:{line_no}: source file not found: {rel_path} (resolved to {source_path})")
            continue

        try:
            actual_hash = compute_hash(method, source_path)
        except ValueError:
            errors.append(f"{file_path}:{line_no}: unsupported hash method: {method}")
            continue

        if actual_hash != expected_hash:
            errors.append(
                f"{file_path}:{line_no}: hash mismatch for {rel_path}\n"
                f"  expected: {expected_hash}\n"
                f"  actual:   {actual_hash}\n"
                f"  Regenerate the file and stage both."
            )

    return errors


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate generated files are in sync with their sources",
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


def find_reverse_references(staged_files: list[Path], repo_root: Optional[Path] = None) -> list[str]:
    """Find repo files that have sync-hash directives pointing to any staged file."""
    git_cwd = str(repo_root) if repo_root else None
    try:
        result = subprocess.run(
            ["git", "grep", "-n", "--cached", "lockeye:.*sync-hash"],
            capture_output=True,
            text=True,
            cwd=git_cwd,
        )
    except FileNotFoundError:
        logger.warning("git not found, skipping reverse reference check")
        return []

    if result.returncode != 0:
        return []

    if repo_root is None:
        repo_root = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
            ).stdout.strip()
        )

    staged_resolved = {f.resolve() for f in staged_files}
    errors = []

    for line in result.stdout.splitlines():
        # format: file:line_no:content
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        ref_file, line_no, content = parts[0], parts[1], parts[2]

        match = SYNC_HASH_RE.search(content)
        if not match:
            continue

        method = match.group(1)
        expected_hash = match.group(2)
        rel_path = match.group(3).strip()

        ref_file_path = repo_root / ref_file
        try:
            source_path = _resolve_source_path(ref_file_path, rel_path)
        except ValueError:
            continue

        if source_path not in staged_resolved:
            continue

        if not source_path.is_file():
            continue

        try:
            actual_hash = compute_hash(method, source_path)
        except ValueError:
            continue

        if actual_hash != expected_hash:
            errors.append(
                f"{ref_file}:{line_no}: hash mismatch for {rel_path} "
                f"(source file was staged but referencing file not updated)\n"
                f"  expected: {expected_hash}\n"
                f"  actual:   {actual_hash}\n"
                f"  Regenerate {ref_file} and stage it."
            )

    return errors


def main():
    args = parse_args()
    config_logger(args)
    logger.debug(f"Arguments: {args}")

    all_errors = []
    staged_files = []
    for file_arg in args.get("files", []):
        file_path = Path(file_arg)
        if not file_path.is_file():
            continue
        staged_files.append(file_path)
        errors = check_file(file_path)
        all_errors.extend(errors)

    all_errors.extend(find_reverse_references(staged_files))

    if all_errors:
        print(_color("red", "sync-hash validation failed:"))
        for error in all_errors:
            print(f"  {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
