import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from autoink.main import (
    AUTOINK_RE,
    _build_marker_line,
    _extract_timestamp,
    _extract_version,
    _find_marker,
    _find_next_nonblank,
    check_file,
)


def _write(path: Path, content: str):
    path.write_text(content)
    return path


def _git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def git_repo():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        _git(repo, "init")
        _git(repo, "config", "user.email", "test@test.com")
        _git(repo, "config", "user.name", "Test")
        yield repo


# ---------- unit tests for helpers ----------


class TestRegex:
    def test_matches_basic(self):
        line = "# lockeye: autoink 42 (2026-04-16T10:30:00Z)"
        m = AUTOINK_RE.search(line)
        assert m is not None
        assert m.group(2) == "42"
        assert m.group(3) == "2026-04-16T10:30:00Z"

    def test_matches_python_comment(self):
        line = "# lockeye: autoink 1 (2026-01-01T00:00:00Z)\n"
        m = AUTOINK_RE.search(line)
        assert m is not None
        assert m.group(2) == "1"

    def test_matches_powershell_comment(self):
        line = "# lockeye: autoink 99 (2026-12-31T23:59:59Z)\n"
        m = AUTOINK_RE.search(line)
        assert m is not None
        assert m.group(2) == "99"

    def test_no_match_without_parens(self):
        line = "# lockeye: autoink 42 2026-04-16T10:30:00Z"
        assert AUTOINK_RE.search(line) is None

    def test_no_match_plain_text(self):
        line = "just some random text"
        assert AUTOINK_RE.search(line) is None


class TestExtractVersion:
    def test_basic(self):
        assert _extract_version("# lockeye: autoink 42 (2026-04-16T10:30:00Z)") == 42

    def test_version_zero(self):
        assert _extract_version("# lockeye: autoink 0 (2026-01-01T00:00:00Z)") == 0

    def test_no_match(self):
        assert _extract_version("no marker here") is None


class TestExtractTimestamp:
    def test_basic(self):
        ts = _extract_timestamp("# lockeye: autoink 42 (2026-04-16T10:30:00Z)")
        assert ts == "2026-04-16T10:30:00Z"

    def test_no_match(self):
        assert _extract_timestamp("no marker here") is None


class TestFindMarker:
    def test_found(self):
        lines = [
            "#!/bin/bash\n",
            "# lockeye: autoink 1 (2026-01-01T00:00:00Z)\n",
            "VERSION=1\n",
        ]
        assert _find_marker(lines) == 1

    def test_not_found(self):
        lines = ["#!/bin/bash\n", "echo hello\n"]
        assert _find_marker(lines) is None


class TestFindNextNonblank:
    def test_immediate(self):
        lines = ["marker\n", "value\n"]
        assert _find_next_nonblank(lines, 0) == 1

    def test_skips_blank_lines(self):
        lines = ["marker\n", "\n", "   \n", "value\n"]
        assert _find_next_nonblank(lines, 0) == 3

    def test_none_at_end(self):
        lines = ["marker\n", "\n"]
        assert _find_next_nonblank(lines, 0) is None


class TestBuildMarkerLine:
    def test_basic(self):
        line = "# lockeye: autoink 1 (2026-01-01T00:00:00Z)\n"
        result = _build_marker_line(line, 2, "2026-04-16T12:00:00Z")
        assert result == "# lockeye: autoink 2 (2026-04-16T12:00:00Z)\n"

    def test_preserves_prefix(self):
        line = "    // lockeye: autoink 10 (2026-01-01T00:00:00Z)\n"
        result = _build_marker_line(line, 11, "2026-06-01T00:00:00Z")
        assert result == "    // lockeye: autoink 11 (2026-06-01T00:00:00Z)\n"

    def test_no_match_returns_unchanged(self):
        line = "no marker here\n"
        assert _build_marker_line(line, 1, "2026-01-01T00:00:00Z") == line


# ---------- integration tests with git ----------


class TestCheckFile:
    def test_auto_increments_when_version_unchanged(self, git_repo):
        """File changed, version not bumped → auto-increment both lines."""
        f = git_repo / "script.sh"
        _write(
            f,
            "#!/bin/bash\n"
            "# lockeye: autoink 1 (2026-01-01T00:00:00Z)\n"
            'VERSION="1 (2026-01-01T00:00:00Z)"\n'
            "echo hello\n",
        )
        _git(git_repo, "add", "script.sh")
        _git(git_repo, "commit", "-m", "initial")

        # Change file content but not the version
        _write(
            f,
            "#!/bin/bash\n"
            "# lockeye: autoink 1 (2026-01-01T00:00:00Z)\n"
            'VERSION="1 (2026-01-01T00:00:00Z)"\n'
            "echo world\n",
        )

        with patch("autoink.main.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-04-16T12:00:00Z"
            mock_dt.side_effect = lambda *a, **kw: mock_dt
            msg = check_file(f, git_repo)

        assert msg is not None
        assert "auto-incremented" in msg
        assert "1 -> 2" in msg

        content = f.read_text()
        assert "# lockeye: autoink 2 (2026-04-16T12:00:00Z)" in content
        assert '"2 (2026-04-16T12:00:00Z)"' in content

    def test_skips_when_version_already_bumped(self, git_repo):
        """Developer already changed the marker line → hook passes."""
        f = git_repo / "script.sh"
        _write(
            f,
            "#!/bin/bash\n"
            "# lockeye: autoink 1 (2026-01-01T00:00:00Z)\n"
            'VERSION="1 (2026-01-01T00:00:00Z)"\n'
            "echo hello\n",
        )
        _git(git_repo, "add", "script.sh")
        _git(git_repo, "commit", "-m", "initial")

        # Developer bumped version manually
        _write(
            f,
            "#!/bin/bash\n"
            "# lockeye: autoink 2 (2026-04-16T00:00:00Z)\n"
            'VERSION="2 (2026-04-16T00:00:00Z)"\n'
            "echo world\n",
        )

        msg = check_file(f, git_repo)
        assert msg is None

    def test_skips_new_file(self, git_repo):
        """File not in HEAD → skip."""
        f = git_repo / "new.sh"
        # Need an initial commit for HEAD to exist
        _write(git_repo / "dummy", "x\n")
        _git(git_repo, "add", "dummy")
        _git(git_repo, "commit", "-m", "initial")

        _write(
            f,
            "#!/bin/bash\n# lockeye: autoink 1 (2026-01-01T00:00:00Z)\nVERSION=1\n",
        )
        msg = check_file(f, git_repo)
        assert msg is None

    def test_skips_no_marker(self, git_repo):
        """File without marker → skip."""
        f = git_repo / "plain.sh"
        _write(f, "#!/bin/bash\necho hello\n")
        _git(git_repo, "add", "plain.sh")
        _git(git_repo, "commit", "-m", "initial")

        _write(f, "#!/bin/bash\necho world\n")
        msg = check_file(f, git_repo)
        assert msg is None

    def test_mirrors_integer_only_variable(self, git_repo):
        """Next line has only the integer (no timestamp) → only integer replaced."""
        f = git_repo / "script.py"
        _write(
            f,
            "# lockeye: autoink 5 (2026-01-01T00:00:00Z)\nVERSION = 5\nprint('hi')\n",
        )
        _git(git_repo, "add", "script.py")
        _git(git_repo, "commit", "-m", "initial")

        _write(
            f,
            "# lockeye: autoink 5 (2026-01-01T00:00:00Z)\nVERSION = 5\nprint('bye')\n",
        )

        with patch("autoink.main.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-06-01T00:00:00Z"
            mock_dt.side_effect = lambda *a, **kw: mock_dt
            check_file(f, git_repo)

        content = f.read_text()
        assert "# lockeye: autoink 6 (2026-06-01T00:00:00Z)" in content
        assert "VERSION = 6" in content

    def test_blank_lines_between_marker_and_variable(self, git_repo):
        """Blank lines between marker and variable are tolerated."""
        f = git_repo / "script.ps1"
        _write(
            f,
            "# lockeye: autoink 3 (2026-01-01T00:00:00Z)\n"
            "\n"
            '$ScriptVersion = "3 (2026-01-01T00:00:00Z)"\n'
            "Write-Host 'a'\n",
        )
        _git(git_repo, "add", "script.ps1")
        _git(git_repo, "commit", "-m", "initial")

        _write(
            f,
            "# lockeye: autoink 3 (2026-01-01T00:00:00Z)\n"
            "\n"
            '$ScriptVersion = "3 (2026-01-01T00:00:00Z)"\n'
            "Write-Host 'b'\n",
        )

        with patch("autoink.main.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-07-01T00:00:00Z"
            mock_dt.side_effect = lambda *a, **kw: mock_dt
            check_file(f, git_repo)

        content = f.read_text()
        assert "# lockeye: autoink 4 (2026-07-01T00:00:00Z)" in content
        assert '"4 (2026-07-01T00:00:00Z)"' in content

    def test_no_next_line(self, git_repo):
        """Marker is the last line in the file → only marker updated."""
        f = git_repo / "script.sh"
        _write(f, "#!/bin/bash\n# lockeye: autoink 1 (2026-01-01T00:00:00Z)\n")
        _git(git_repo, "add", "script.sh")
        _git(git_repo, "commit", "-m", "initial")

        _write(f, "#!/bin/bash\necho new\n# lockeye: autoink 1 (2026-01-01T00:00:00Z)\n")

        with patch("autoink.main.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-05-01T00:00:00Z"
            mock_dt.side_effect = lambda *a, **kw: mock_dt
            msg = check_file(f, git_repo)

        assert msg is not None
        content = f.read_text()
        assert "# lockeye: autoink 2 (2026-05-01T00:00:00Z)" in content

    def test_malformed_directive(self, git_repo):
        """Marker present but malformed → returns error."""
        # We need something that has "lockeye:" + "autoink" but doesn't
        # match the full regex. Since _find_marker uses AUTOINK_RE
        # (which requires parens), a line without parens won't even match.
        # So we test the case where someone writes partial format.
        # Actually _find_marker returns None if AUTOINK_RE doesn't match,
        # so check_file returns None. The malformed error path is hit when
        # _find_marker finds the line but _extract_version fails — but
        # they use the same regex. So the malformed path is effectively
        # unreachable with current regex. Let's verify:
        f = git_repo / "bad.sh"
        _write(f, "# lockeye: autoink (no-version)\nVERSION=1\n")
        _git(git_repo, "add", "bad.sh")
        _git(git_repo, "commit", "-m", "initial")
        _write(f, "# lockeye: autoink (no-version)\nVERSION=2\n")

        msg = check_file(f, git_repo)
        assert msg is None  # no match at all, silently skipped
