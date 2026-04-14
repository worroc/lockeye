import subprocess
import tempfile
from pathlib import Path

import pytest

from sync_hash.main import _resolve_source_path, check_file, compute_hash, find_reverse_references


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def _write(path: Path, content: str):
    path.write_text(content)
    return path


class TestComputeHash:
    def test_md5(self, tmp_dir):
        src = _write(tmp_dir / "src.yaml", "hello: world\n")
        h = compute_hash("md5", src)
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)

    def test_sha256(self, tmp_dir):
        src = _write(tmp_dir / "src.yaml", "hello: world\n")
        h = compute_hash("sha256", src)
        assert len(h) == 64

    def test_deterministic(self, tmp_dir):
        src = _write(tmp_dir / "src.yaml", "data\n")
        assert compute_hash("md5", src) == compute_hash("md5", src)

    def test_changes_with_content(self, tmp_dir):
        src = tmp_dir / "src.yaml"
        _write(src, "v1\n")
        h1 = compute_hash("md5", src)
        _write(src, "v2\n")
        h2 = compute_hash("md5", src)
        assert h1 != h2


class TestCheckFile:
    def test_correct_hash(self, tmp_dir):
        src = _write(tmp_dir / "src.yaml", "hello: world\n")
        h = compute_hash("md5", src)
        gen = _write(tmp_dir / "gen.conf", f"# lockeye: sync-hash md5 {h} src.yaml\n")
        assert check_file(gen) == []

    def test_correct_hash_sha256(self, tmp_dir):
        src = _write(tmp_dir / "src.yaml", "data\n")
        h = compute_hash("sha256", src)
        gen = _write(tmp_dir / "gen.conf", f"# lockeye: sync-hash sha256 {h} src.yaml\n")
        assert check_file(gen) == []

    def test_wrong_hash(self, tmp_dir):
        _write(tmp_dir / "src.yaml", "hello\n")
        gen = _write(tmp_dir / "gen.conf", "# lockeye: sync-hash md5 deadbeef00000000deadbeef00000000 src.yaml\n")
        errors = check_file(gen)
        assert len(errors) == 1
        assert "hash mismatch" in errors[0]

    def test_missing_source(self, tmp_dir):
        gen = _write(tmp_dir / "gen.conf", "# lockeye: sync-hash md5 abc123 nonexistent.yaml\n")
        errors = check_file(gen)
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_no_directive(self, tmp_dir):
        gen = _write(tmp_dir / "gen.conf", "# just a comment\nsome content\n")
        assert check_file(gen) == []

    def test_relative_path(self, tmp_dir):
        sub = tmp_dir / "sub"
        sub.mkdir()
        src = _write(tmp_dir / "src.yaml", "content\n")
        h = compute_hash("md5", src)
        gen = _write(sub / "gen.conf", f"# lockeye: sync-hash md5 {h} ../src.yaml\n")
        assert check_file(gen) == []

    def test_multiple_directives(self, tmp_dir):
        src1 = _write(tmp_dir / "a.yaml", "aaa\n")
        src2 = _write(tmp_dir / "b.yaml", "bbb\n")
        h1 = compute_hash("md5", src1)
        h2 = compute_hash("md5", src2)
        gen = _write(
            tmp_dir / "gen.conf",
            f"# lockeye: sync-hash md5 {h1} a.yaml\n# lockeye: sync-hash md5 {h2} b.yaml\n",
        )
        assert check_file(gen) == []

    def test_multiple_directives_one_wrong(self, tmp_dir):
        src1 = _write(tmp_dir / "a.yaml", "aaa\n")
        _write(tmp_dir / "b.yaml", "bbb\n")
        h1 = compute_hash("md5", src1)
        gen = _write(
            tmp_dir / "gen.conf",
            f"# lockeye: sync-hash md5 {h1} a.yaml\n# lockeye: sync-hash md5 0000000000000000 b.yaml\n",
        )
        errors = check_file(gen)
        assert len(errors) == 1
        assert "b.yaml" in errors[0]

    def test_stale_after_source_change(self, tmp_dir):
        src = _write(tmp_dir / "src.yaml", "v1\n")
        h = compute_hash("md5", src)
        gen = _write(tmp_dir / "gen.conf", f"# lockeye: sync-hash md5 {h} src.yaml\n")
        assert check_file(gen) == []

        # Change source without regenerating
        _write(src, "v2\n")
        errors = check_file(gen)
        assert len(errors) == 1
        assert "hash mismatch" in errors[0]


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


class TestResolveSourcePath:
    def test_relative_path(self, tmp_dir):
        sub = tmp_dir / "sub"
        sub.mkdir()
        src = _write(tmp_dir / "src.yaml", "data\n")
        ref_file = sub / "gen.conf"
        resolved = _resolve_source_path(ref_file, "../src.yaml")
        assert resolved == src.resolve()

    def test_absolute_path_rejected(self, tmp_dir):
        ref_file = tmp_dir / "gen.conf"
        with pytest.raises(ValueError, match="absolute paths not allowed"):
            _resolve_source_path(ref_file, "/etc/passwd")

    def test_repo_prefix(self, git_repo):
        (git_repo / "hslibs").mkdir()
        src = _write(git_repo / "hslibs" / "src.yaml", "data\n")
        ref_file = git_repo / "deep" / "nested" / "gen.conf"
        import os

        old_cwd = os.getcwd()
        os.chdir(git_repo)
        try:
            resolved = _resolve_source_path(ref_file, "repo://hslibs/src.yaml")
            assert resolved == src.resolve()
        finally:
            os.chdir(old_cwd)

    def test_check_file_absolute_path_error(self, tmp_dir):
        gen = _write(tmp_dir / "gen.conf", "# lockeye: sync-hash md5 abc123 /etc/passwd\n")
        errors = check_file(gen)
        assert len(errors) == 1
        assert "absolute paths not allowed" in errors[0]

    def test_check_file_repo_prefix(self, git_repo):
        src = _write(git_repo / "src.yaml", "data\n")
        h = compute_hash("md5", src)
        (git_repo / "sub").mkdir()
        gen = _write(git_repo / "sub" / "gen.conf", f"# lockeye: sync-hash md5 {h} repo://src.yaml\n")
        import os

        old_cwd = os.getcwd()
        os.chdir(git_repo)
        try:
            assert check_file(gen) == []
        finally:
            os.chdir(old_cwd)


class TestFindReverseReferences:
    def test_staged_source_with_stale_hash(self, git_repo):
        """fileA has sync-hash to fileB, fileB changes — should error."""
        src = git_repo / "src.yaml"
        src.write_text("v1\n")
        h = compute_hash("md5", src)

        gen = git_repo / "gen.conf"
        gen.write_text(f"# lockeye: sync-hash md5 {h} src.yaml\n")

        _git(git_repo, "add", "src.yaml", "gen.conf")
        _git(git_repo, "commit", "-m", "initial")

        # Change source, stage only source
        src.write_text("v2\n")
        _git(git_repo, "add", "src.yaml")

        errors = find_reverse_references([src], repo_root=git_repo)
        assert len(errors) == 1
        assert "hash mismatch" in errors[0]
        assert "gen.conf" in errors[0]

    def test_staged_source_with_valid_hash(self, git_repo):
        """fileA has sync-hash to fileB, both updated — no error."""
        src = git_repo / "src.yaml"
        src.write_text("v1\n")
        h = compute_hash("md5", src)

        gen = git_repo / "gen.conf"
        gen.write_text(f"# lockeye: sync-hash md5 {h} src.yaml\n")

        _git(git_repo, "add", "src.yaml", "gen.conf")
        _git(git_repo, "commit", "-m", "initial")

        # Change source and update gen with new hash
        src.write_text("v2\n")
        h2 = compute_hash("md5", src)
        gen.write_text(f"# lockeye: sync-hash md5 {h2} src.yaml\n")
        _git(git_repo, "add", "src.yaml", "gen.conf")

        errors = find_reverse_references([src], repo_root=git_repo)
        assert errors == []

    def test_staged_file_not_referenced(self, git_repo):
        """Staged file is not referenced by any sync-hash — no error."""
        src = git_repo / "src.yaml"
        src.write_text("data\n")
        other = git_repo / "other.txt"
        other.write_text("unrelated\n")

        _git(git_repo, "add", "src.yaml", "other.txt")
        _git(git_repo, "commit", "-m", "initial")

        src.write_text("changed\n")
        _git(git_repo, "add", "src.yaml")

        errors = find_reverse_references([src], repo_root=git_repo)
        assert errors == []

    def test_multiple_files_reference_same_source(self, git_repo):
        """Two files reference the same source — both should error."""
        src = git_repo / "src.yaml"
        src.write_text("v1\n")
        h = compute_hash("md5", src)

        gen1 = git_repo / "gen1.conf"
        gen1.write_text(f"# lockeye: sync-hash md5 {h} src.yaml\n")
        gen2 = git_repo / "gen2.conf"
        gen2.write_text(f"# lockeye: sync-hash md5 {h} src.yaml\n")

        _git(git_repo, "add", ".")
        _git(git_repo, "commit", "-m", "initial")

        src.write_text("v2\n")
        _git(git_repo, "add", "src.yaml")

        errors = find_reverse_references([src], repo_root=git_repo)
        assert len(errors) == 2
