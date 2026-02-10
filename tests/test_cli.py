"""Tests for CLI commands via Click CliRunner."""

from click.testing import CliRunner

from second_brain.cli.main import cli


class TestCLI:
    def _runner(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        return CliRunner(), ["--db", db_path]

    def test_add_with_argument(self, tmp_path):
        runner, opts = self._runner(tmp_path)
        result = runner.invoke(cli, [*opts, "add", "Hello world"])
        assert result.exit_code == 0
        assert "Note created:" in result.output

    def test_add_with_tags(self, tmp_path):
        runner, opts = self._runner(tmp_path)
        result = runner.invoke(cli, [*opts, "add", "-t", "python", "-t", "tutorial", "Test note"])
        assert result.exit_code == 0
        assert "python" in result.output
        assert "tutorial" in result.output

    def test_add_with_stdin(self, tmp_path):
        runner, opts = self._runner(tmp_path)
        result = runner.invoke(cli, [*opts, "add"], input="Stdin content\n")
        assert result.exit_code == 0
        assert "Note created:" in result.output

    def test_add_empty_content_fails(self, tmp_path):
        runner, opts = self._runner(tmp_path)
        result = runner.invoke(cli, [*opts, "add"], input="")
        assert result.exit_code != 0

    def test_search_finds_note(self, tmp_path):
        runner, opts = self._runner(tmp_path)
        runner.invoke(cli, [*opts, "add", "Python programming guide"])
        result = runner.invoke(cli, [*opts, "search", "Python"])
        assert result.exit_code == 0
        assert "Python programming guide" in result.output

    def test_search_no_results(self, tmp_path):
        runner, opts = self._runner(tmp_path)
        result = runner.invoke(cli, [*opts, "search", "nonexistent"])
        assert result.exit_code == 0
        assert "No results found" in result.output

    def test_show_displays_note(self, tmp_path):
        runner, opts = self._runner(tmp_path)
        add_result = runner.invoke(cli, [*opts, "add", "Detailed note content"])
        # Extract the UUID from the output
        note_id = add_result.output.split("Note created: ")[1].strip().split("\n")[0]

        result = runner.invoke(cli, [*opts, "show", note_id])
        assert result.exit_code == 0
        assert "Detailed note content" in result.output
        assert note_id in result.output

    def test_show_invalid_uuid(self, tmp_path):
        runner, opts = self._runner(tmp_path)
        result = runner.invoke(cli, [*opts, "show", "not-a-uuid"])
        assert result.exit_code != 0

    def test_show_nonexistent_note(self, tmp_path):
        runner, opts = self._runner(tmp_path)
        result = runner.invoke(cli, [*opts, "show", "00000000-0000-0000-0000-000000000000"])
        assert result.exit_code != 0
