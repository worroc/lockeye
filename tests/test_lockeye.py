import re
import tempfile
from pathlib import Path

import pytest

import lockeye.main as lk
from lockeye.main import (
    CodeRef,
    get_samples,
    parse_args,
    read_orig_code,
)


@pytest.fixture
def globals_set():
    """main() sets these module globals before using CodeRef; mirror it."""
    lk.derective_rex = re.compile(r"(\s*).*?lockeye:\s+(.*?)\s[+](\d+)$")
    lk.ref_terminator = "lockeye-stop"
    yield


def _mkref(**kw) -> CodeRef:
    base = dict(
        ref_file=Path("doc.rst"),
        ref_line=1,
        ref_code=[],
        orig_file=Path("do.py"),
        orig_line=1,
        orig_code=[],
        size=0,
    )
    base.update(kw)
    return CodeRef(**base)


# ---------- argument parsing ----------


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args["pattern"] == ["*.rst"]
        assert args["anchor"] == ["lockeye"]

    def test_custom_pattern_and_anchor(self):
        args = parse_args(["--pattern", "*.md", "*.rst", "--anchor", "lock"])
        assert args["pattern"] == ["*.md", "*.rst"]
        assert args["anchor"] == ["lock"]


# ---------- sync_report ----------


class TestSyncReport:
    def test_synced_when_identical(self):
        ref = _mkref(ref_code=["a\n", "b\n"], orig_code=["a\n", "b\n"], size=2)
        synced, report = ref.sync_report()
        assert synced is True
        assert report == ""

    def test_not_synced_when_different(self):
        ref = _mkref(ref_code=["a\n", "X\n"], orig_code=["a\n", "b\n"], size=2)
        synced, report = ref.sync_report()
        assert synced is False
        assert "do.py" in report

    def test_blank_lines_are_equal(self):
        ref = _mkref(ref_code=["a\n", "   \n"], orig_code=["a\n", "\n"], size=2)
        synced, _ = ref.sync_report()
        assert synced is True


# ---------- read_orig_code ----------


class TestReadOrigCode:
    def test_reads_size_lines_from_offset(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "src.py"
            f.write_text("l1\nl2\nl3\nl4\n")
            code = read_orig_code(f, 2, 2)
            assert code == ["l2\n", "l3\n"]

    def test_missing_file_returns_empty(self):
        assert read_orig_code(Path("/does/not/exist.py"), 1, 3) == []

    def test_stops_at_eof(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "src.py"
            f.write_text("only\n")
            assert read_orig_code(f, 1, 5) == ["only\n"]


# ---------- end-to-end via get_samples ----------


class TestGetSamples:
    def _build(self, root: Path, source_body: str):
        (root / "src").mkdir()
        (root / "src" / "do.py").write_text(source_body)
        (root / "doc.rst").write_text(
            "intro line\n   # lockeye: src/do.py +1\n   def foo():\n       print('hi')\n   # lockeye-stop\n"
        )

    def test_sample_in_sync(self, globals_set):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._build(root, "def foo():\n    print('hi')\n")
            samples = get_samples(root, {"pattern": ["*.rst"], "anchor": ["lockeye"]})
            assert len(samples) == 1
            synced, _ = samples[0].sync_report()
            assert synced is True

    def test_sample_out_of_sync(self, globals_set):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._build(root, "def foo():\n    print('CHANGED')\n")
            samples = get_samples(root, {"pattern": ["*.rst"], "anchor": ["lockeye"]})
            assert len(samples) == 1
            synced, report = samples[0].sync_report()
            assert synced is False
            assert "do.py" in report
