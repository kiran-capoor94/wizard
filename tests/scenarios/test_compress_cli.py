"""Behaviour tests for wizard compress CLI command."""
from typer.testing import CliRunner

from wizard.cli.main import app

_runner = CliRunner(mix_stderr=False)


def test_compress_file_prints_to_stdout(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("The authentication middleware should check the database connection.")
    result = _runner.invoke(app, ["compress", str(f)])
    assert result.exit_code == 0
    assert f.read_text() == "The authentication middleware should check the database connection."


def test_compress_file_inplace_creates_backup(tmp_path):
    f = tmp_path / "note.txt"
    original = "The authentication middleware should check the database connection."
    f.write_text(original)
    result = _runner.invoke(app, ["compress", str(f), "--inplace"])
    assert result.exit_code == 0
    backup = tmp_path / "note.txt.original"
    assert backup.exists()
    assert backup.read_text() == original
    assert f.read_text() != original


def test_compress_reports_reduction(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("The authentication middleware should check the database connection.")
    result = _runner.invoke(app, ["compress", str(f)])
    assert result.exit_code == 0
    assert "chars" in result.stderr
    assert "reduction" in result.stderr


def test_compress_rejects_binary_file(tmp_path):
    f = tmp_path / "binary.bin"
    f.write_bytes(b"\x00\x01\x02\x03binary content")
    result = _runner.invoke(app, ["compress", str(f)])
    assert result.exit_code != 0
    assert "text file" in result.stderr.lower()


def test_compress_nonexistent_file_exits_nonzero():
    result = _runner.invoke(app, ["compress", "/nonexistent/path/file.txt"])
    assert result.exit_code != 0


def test_compress_empty_file_passes_through(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("")
    result = _runner.invoke(app, ["compress", str(f)])
    assert result.exit_code == 0
    assert "0%" in result.stderr
