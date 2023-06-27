import argparse
import logging
import re
import subprocess
import sys
from collections import namedtuple
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, TextIO

logger = logging.getLogger(__name__)


# matches the following derective
# """    # lockeye: explorer/explorer/events.py +8"""
# """lockeye: explorer/explorer/events.py +8"""
derective_rex = None
ref_terminator = None
root = None

Location = namedtuple("Location", ["file", "line", "lstrip"])

start_color = {"ref": "\x1b[0;31m", "orig": "\x1b[0;32m", "sep": "\x1b[36m"}
end_color = "\x1b[0m"


def _color(color: str, text: str):
    return f"{start_color[color]}{text}{end_color}"


color_orig = partial(_color, "orig")
color_ref = partial(_color, "ref")
color_sep = partial(_color, "sep")


@dataclass
class CodeRef:
    """representation od a single code referrence"""

    ref_file: Path
    ref_line: int
    ref_code: str
    orig_file: Path
    orig_line: int
    orig_code: str
    size: int

    @classmethod
    def from_grep(cls, root: Path, line: str):
        rst_name, line_number, mark = line.split(":", 2)
        ref_line = int(line_number)
        ref_file = Path(rst_name)

        with ref_file.open() as f:
            for i in range(ref_line - 1):
                f.readline()

            orig_file, orig_line, prefix_size = read_derective(root, f)
            ref_code = read_ref_code(f, prefix_size)
            size = len(ref_code)
            orig_code = read_orig_code(orig_file, orig_line, size)

        return CodeRef(
            ref_file=ref_file,
            ref_line=ref_line,
            ref_code=ref_code,
            orig_file=orig_file,
            orig_line=orig_line,
            orig_code=orig_code,
            size=size,
        )

    def sync_report(self):
        for i in range(self.size):
            if self.ref_code[i].strip() == self.orig_code[i].strip() == "":
                # do not match empty lines
                continue
            if self.ref_code[i] != self.orig_code[i]:
                self.ref_code[i] = "> " + self.ref_code[i]
                break
        else:
            return True, ""

        return (
            False,
            f"""

{color_ref("***")} "{self.ref_file}" +{self.ref_line}
{color_orig("---")} "{self.orig_file}" +{self.orig_line}
***************
{color_sep("***")} {self.ref_line},{self.ref_line + self.size} {color_sep("***")}
{color_ref("".join(self.ref_code))}
{color_sep("---")} {self.orig_line},{self.orig_line + self.size} {color_sep("---")}
{color_orig("".join(self.orig_code))}""",
        )


def read_orig_code(orig_file: Path, orig_line: int, size: int):
    if not orig_file.exists():
        return []

    orig_code = []
    with orig_file.open() as f:
        for i in range(orig_line - 1):
            f.readline()
        for i in range(size):
            line = f.readline()
            if not line:  # EOF
                break
            orig_code.append(line)
    return orig_code


def read_ref_code(f: TextIO, prefix_size: int):
    ref_code = []
    line = f.readline()
    while line and ref_terminator not in line:
        code_line = line[prefix_size:] or line[-1]
        ref_code.append(code_line)
        line = f.readline()
    return ref_code


def read_derective(root: Path, f: TextIO):
    # start position of code sample
    line = f.readline()
    file_ref = derective_rex.match(line)
    if file_ref:
        prefix, path, orig_line_num = file_ref.groups()
        orig_path = root / Path(path)
        prefix_size = len(prefix)
        return orig_path, int(orig_line_num), prefix_size
    raise Exception("no header found")


def get_samples(root: Path, args: Dict) -> List[CodeRef]:
    match_patterns = " ".join([f'--include "{pattern}"' for pattern in args["pattern"]])
    anchor = args["anchor"][0]

    samples: List[CodeRef] = []
    command = f"grep -Rn {anchor} {match_patterns} {root}/* | grep -v {anchor}-stop"
    logger.debug(f"looking for references {command}")
    print(f"looking for references {command}")
    res = subprocess.run(command, shell=True, capture_output=True)
    if res.returncode:
        return []
    for grep_line in res.stdout.decode("utf-8").split("\n"):
        if grep_line.strip():
            samples.append(CodeRef.from_grep(root, grep_line))
    return samples


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="",
        add_help=False,
    )
    env_group = parser.add_argument_group("env options")
    env_group.add_argument("--log-level", default="info", nargs="*", help="log level output")
    env_group.add_argument("--pattern", default=["*.rst"], nargs="*", help="file match pattern")
    env_group.add_argument("--anchor", default=["lockeye"], nargs="*", help="anchor name to search for in files")
    target_group = parser.add_argument_group("target options")
    target_group.add_argument(
        "files", nargs="*", help="One or more Python source files that need their imports sorted."
    )
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = _build_arg_parser()
    arguments = {key: value for key, value in vars(parser.parse_args(argv)).items() if value}
    return arguments


def config_logger(args):
    ll = args["log_level"][0].upper()
    numeric_level = getattr(logging, ll.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {ll}")
    logging.basicConfig(
        format="%(levelname)s %(module)s.%(funcName)s:%(lineno)d # %(message)s", encoding="utf-8", level=numeric_level
    )


def main():
    global root, derective_rex, ref_terminator
    args = parse_args()
    config_logger(args)
    logger.debug(f"running from: '{__file__}'")
    logger.debug(f"Arguments: {args}")
    root = Path().cwd()
    logger.debug(f"working on {root}")
    # used to match references
    anchor = args["anchor"][0]
    derective_rex = re.compile(r"(\s*).*?" + anchor + r":\s+(.*?)\s[+](\d+)$")
    ref_terminator = f"{anchor}-stop"
    samples = get_samples(root, args)
    failed = False
    if samples:
        for sample in samples:
            synced, report = sample.sync_report()
            if not synced:
                print(report)
                failed = failed or True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
