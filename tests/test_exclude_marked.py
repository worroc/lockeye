import subprocess
import tempfile
from pathlib import Path

import pytest

from exclude_marked.main import (
    build_comment_syntax,
    get_matches,
    make_marker_re,
    parse_args,
)


def _git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def git_repo(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        _git(repo, "init")
        _git(repo, "config", "user.email", "test@test.com")
        _git(repo, "config", "user.name", "Test")
        monkeypatch.chdir(repo)
        yield repo


def _stage(repo: Path, name: str, content: str):
    (repo / name).write_text(content)
    _git(repo, "add", name)


# ---------- whole-word marker matching ----------


class TestMarkerRegex:
    def test_matches_plain(self):
        assert make_marker_re("no-commit").search("debug no-commit line")

    def test_matches_glued_block_comment(self):
        assert make_marker_re("no-commit").search("/*no-commit*/")

    def test_matches_glued_html_comment(self):
        assert make_marker_re("no-commit").search("<!--no-commit-->")

    def test_rejects_longer_word_suffix(self):
        assert make_marker_re("no-commit").search("no-committed") is None

    def test_rejects_longer_word_prefix(self):
        assert make_marker_re("no-commit").search("xno-commit") is None

    def test_case_insensitive_by_default(self):
        assert make_marker_re("NO-COMMIT").search("# no-commit")

    def test_case_sensitive_rejects_other_case(self):
        assert make_marker_re("NO-COMMIT", case_sensitive=True).search("# no-commit") is None


# ---------- argument parsing ----------


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args["marker"] == "no-commit"
        assert args["log_level"] == "info"

    def test_custom_marker(self):
        args = parse_args(["--marker", "NO-COMMIT"])
        assert args["marker"] == "NO-COMMIT"

    def test_case_sensitive_flag(self):
        args = parse_args(["--case-sensitive"])
        assert args["case_sensitive"] is True

    def test_comment_option(self):
        args = parse_args(["--comment", ".foo=#"])
        assert args["comment"] == [".foo=#"]

    def test_exclude_option(self):
        args = parse_args(["--exclude", "gen.py"])
        assert args["exclude"] == ["gen.py"]


# ---------- comment-syntax config ----------


class TestBuildCommentSyntax:
    def test_defaults_present(self):
        syntax = build_comment_syntax({})
        assert syntax[".py"] == ["#"]
        assert "//" in syntax[".js"]
        assert syntax[".md"] == ["<!--"]

    def test_override_adds_new_extension(self):
        syntax = build_comment_syntax({"comment": [".foo=#"]})
        assert syntax[".foo"] == ["#"]

    def test_override_replaces_existing(self):
        syntax = build_comment_syntax({"comment": [".py=//,/*"]})
        assert syntax[".py"] == ["//", "/*"]


# ---------- get_matches against a real staged diff ----------


class TestGetMatches:
    def test_matches_whole_token(self, git_repo):
        _stage(git_repo, "a.py", "x = 1  # NO-COMMIT debug\n")
        matches = get_matches({"marker": "NO-COMMIT"})
        assert len(matches) == 1
        assert matches[0].file == Path("a.py")

    def test_no_match_when_absent(self, git_repo):
        _stage(git_repo, "a.py", "x = 1  # keep me\n")
        assert get_matches({"marker": "NO-COMMIT"}) == []

    def test_substring_does_not_match(self, git_repo):
        # marker embedded inside a larger token must NOT trigger
        _stage(git_repo, "a.py", "x = 'NO-COMMITTED'\n")
        assert get_matches({"marker": "NO-COMMIT"}) == []

    def test_case_insensitive_by_default(self, git_repo):
        _stage(git_repo, "a.py", "x = 1  # no-commit\n")
        matches = get_matches({"marker": "NO-COMMIT"})
        assert len(matches) == 1

    def test_case_sensitive_rejects_other_case(self, git_repo):
        _stage(git_repo, "a.py", "x = 1  # no-commit\n")
        matches = get_matches({"marker": "NO-COMMIT", "case_sensitive": True})
        assert matches == []

    # ---- comment-only matching (marker outside a comment is ignored) ----

    def test_py_comment_at_line_start_matches(self, git_repo):
        # Claim 1: marker as the first content token of a comment must match
        _stage(git_repo, "a.py", "# no-commit\n")
        assert len(get_matches({"marker": "NO-COMMIT"})) == 1

    def test_py_marker_in_string_is_ignored(self, git_repo):
        # not a comment -> must NOT trigger
        _stage(git_repo, "a.py", 'x = "no-commit"\n')
        assert get_matches({"marker": "NO-COMMIT"}) == []

    def test_py_marker_as_bare_code_is_ignored(self, git_repo):
        _stage(git_repo, "a.py", "no-commit = 1\n")
        assert get_matches({"marker": "NO-COMMIT"}) == []

    def test_markdown_html_comment_matches(self, git_repo):
        _stage(git_repo, "doc.md", "text\n<!-- no-commit draft -->\n")
        assert len(get_matches({"marker": "NO-COMMIT"})) == 1

    def test_markdown_plain_text_is_ignored(self, git_repo):
        _stage(git_repo, "doc.md", "please no-commit this section\n")
        assert get_matches({"marker": "NO-COMMIT"}) == []

    def test_rst_comment_matches(self, git_repo):
        _stage(git_repo, "doc.rst", ".. no-commit\n")
        assert len(get_matches({"marker": "NO-COMMIT"})) == 1

    def test_go_line_comment_matches(self, git_repo):
        _stage(git_repo, "m.go", "x++ // no-commit\n")
        assert len(get_matches({"marker": "NO-COMMIT"})) == 1

    def test_go_glued_block_comment_matches(self, git_repo):
        _stage(git_repo, "m.go", "x++ /*no-commit*/\n")
        assert len(get_matches({"marker": "NO-COMMIT"})) == 1

    def test_markdown_glued_comment_matches(self, git_repo):
        _stage(git_repo, "doc.md", "text\n<!--no-commit-->\n")
        assert len(get_matches({"marker": "NO-COMMIT"})) == 1

    # ---- no / unknown extension: match anywhere ----

    def test_no_extension_matches_anywhere(self, git_repo):
        # Claim 1: bare first-token marker must match in an extensionless file
        _stage(git_repo, "NOTES", "no-commit leftover\n")
        assert len(get_matches({"marker": "NO-COMMIT"})) == 1

    def test_unknown_extension_matches_anywhere(self, git_repo):
        _stage(git_repo, "a.txt", "no-commit here\n")
        assert len(get_matches({"marker": "NO-COMMIT"})) == 1

    # ---- exclusions ----

    def test_precommit_config_is_excluded(self, git_repo):
        _stage(git_repo, ".pre-commit-config.yaml", "args: [--marker, NO-COMMIT]\n")
        assert get_matches({"marker": "NO-COMMIT"}) == []

    def test_custom_exclude(self, git_repo):
        _stage(git_repo, "gen.py", "# no-commit\n")
        assert get_matches({"marker": "NO-COMMIT", "exclude": ["gen.py"]}) == []

    # ---- config override drives matching ----

    def test_comment_override_enables_matching(self, git_repo):
        # `.foo` is unknown -> matches anywhere by default; overriding to `#`
        # restricts it to comments, so a bare-code marker stops matching
        _stage(git_repo, "a.foo", "no-commit = 1\n")
        assert get_matches({"marker": "NO-COMMIT", "comment": [".foo=#"]}) == []
