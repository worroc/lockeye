from unittest.mock import patch

import pytest

from require_workitem.main import (
    _strip_comments,
    has_workitem,
    main,
    missing_patterns,
    parse_args,
)

DEFAULT = r"AB#\d+"


@pytest.fixture
def write_msg(tmp_path):
    """Write a commit message to an auto-cleaned temp file; return its path."""
    counter = {"n": 0}

    def _write(content: str) -> str:
        counter["n"] += 1
        path = tmp_path / f"msg{counter['n']}.txt"
        path.write_text(content)
        return str(path)

    return _write


# ---------- unit tests for helpers ----------


class TestStripComments:
    def test_removes_comment_lines(self):
        msg = "title\n# a comment\nbody"
        assert _strip_comments(msg) == "title\nbody"

    def test_removes_indented_comment_lines(self):
        msg = "title\n   # indented comment\nbody"
        assert _strip_comments(msg) == "title\nbody"

    def test_keeps_hash_inside_text(self):
        msg = "fix AB#12 issue"
        assert _strip_comments(msg) == "fix AB#12 issue"


class TestHasWorkitem:
    def test_found_in_title(self):
        assert has_workitem("fix AB#1234 crash", DEFAULT) is True

    def test_found_in_body(self):
        assert has_workitem("title\n\ndetails AB#7\n", DEFAULT) is True

    def test_missing(self):
        assert has_workitem("no reference here", DEFAULT) is False

    def test_ignores_comment_only_reference(self):
        msg = "title\n\n# only in comment AB#99\n"
        assert has_workitem(msg, DEFAULT) is False

    def test_requires_digits(self):
        assert has_workitem("bare AB# marker", DEFAULT) is False

    def test_case_insensitive_by_default(self):
        assert has_workitem("fix ab#77 bug", DEFAULT) is True

    def test_case_sensitive_rejects_lowercase(self):
        assert has_workitem("fix ab#77 bug", DEFAULT, case_sensitive=True) is False

    def test_case_sensitive_accepts_uppercase(self):
        assert has_workitem("fix AB#77 bug", DEFAULT, case_sensitive=True) is True

    def test_custom_pattern(self):
        assert has_workitem("see JIRA-42 ticket", r"JIRA-\d+") is True


class TestMissingPatterns:
    def test_none_missing(self):
        msg = "fix AB#1 and JIRA-42"
        assert missing_patterns(msg, [r"AB#\d+", r"JIRA-\d+"]) == []

    def test_reports_only_missing(self):
        msg = "fix AB#1 only"
        assert missing_patterns(msg, [r"AB#\d+", r"JIRA-\d+"]) == [r"JIRA-\d+"]

    def test_all_missing(self):
        assert missing_patterns("nothing", [r"AB#\d+", r"JIRA-\d+"]) == [r"AB#\d+", r"JIRA-\d+"]

    def test_case_sensitive(self):
        assert missing_patterns("fix ab#1", [r"AB#\d+"], case_sensitive=True) == [r"AB#\d+"]


# ---------- CLI argument parsing ----------


class TestParseArgs:
    def test_no_pattern_by_default(self):
        args = parse_args(["/path/to/COMMIT_EDITMSG"])
        assert "patterns" not in args  # empty list is dropped
        assert args["files"] == ["/path/to/COMMIT_EDITMSG"]
        assert "case_sensitive" not in args  # store_true false is dropped

    def test_case_sensitive_flag(self):
        args = parse_args(["--case-sensitive", "msg.txt"])
        assert args["case_sensitive"] is True

    def test_single_pattern(self):
        args = parse_args(["--pattern", r"JIRA-\d+", "msg.txt"])
        assert args["patterns"] == [r"JIRA-\d+"]

    def test_multiple_patterns(self):
        args = parse_args(["--pattern", r"AB#\d+", "--pattern", r"JIRA-\d+", "msg.txt"])
        assert args["patterns"] == [r"AB#\d+", r"JIRA-\d+"]


# ---------- main() end-to-end ----------


class TestMain:
    def _run(self, argv):
        with patch("sys.argv", ["require-workitem", *argv]):
            main()

    def test_passes_with_workitem(self, write_msg):
        path = write_msg("fix AB#1234 crash\n")
        self._run(["--pattern", r"AB#\d+", path])  # no SystemExit == success

    def test_fails_without_workitem(self, write_msg):
        path = write_msg("chore: tidy up\n")
        with pytest.raises(SystemExit) as exc:
            self._run(["--pattern", r"AB#\d+", path])
        assert exc.value.code == 1

    def test_fails_when_only_in_comment(self, write_msg):
        path = write_msg("chore: tidy up\n\n# AB#1234\n")
        with pytest.raises(SystemExit) as exc:
            self._run(["--pattern", r"AB#\d+", path])
        assert exc.value.code == 1

    def test_passes_with_multiple_patterns(self, write_msg):
        path = write_msg("fix AB#1 see JIRA-42\n")
        self._run(["--pattern", r"AB#\d+", "--pattern", r"JIRA-\d+", path])

    def test_fails_when_one_of_multiple_missing(self, write_msg):
        path = write_msg("fix AB#1 only\n")
        with pytest.raises(SystemExit) as exc:
            self._run(["--pattern", r"AB#\d+", "--pattern", r"JIRA-\d+", path])
        assert exc.value.code == 1

    def test_fails_when_no_pattern_configured(self, write_msg):
        path = write_msg("fix AB#1234 crash\n")
        with pytest.raises(SystemExit) as exc:
            self._run([path])
        assert exc.value.code == 1

    def test_case_sensitive_rejects_lowercase(self, write_msg):
        path = write_msg("fix ab#77 bug\n")
        with pytest.raises(SystemExit) as exc:
            self._run(["--case-sensitive", "--pattern", r"AB#\d+", path])
        assert exc.value.code == 1

    def test_case_insensitive_passes_lowercase(self, write_msg):
        path = write_msg("fix ab#77 bug\n")
        self._run(["--pattern", r"AB#\d+", path])  # no SystemExit == success

    def test_custom_pattern(self, write_msg):
        path = write_msg("see JIRA-42\n")
        self._run(["--pattern", r"JIRA-\d+", path])

    def test_fails_when_no_message_file(self):
        with pytest.raises(SystemExit) as exc:
            self._run(["--pattern", r"AB#\d+"])
        assert exc.value.code == 1
