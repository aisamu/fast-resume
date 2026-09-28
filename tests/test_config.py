"""Tests for agent storage path resolution."""

from pathlib import Path

from fast_resume.config import claude_projects_dir, codex_sessions_dir

# Where each agent keeps sessions when its variable is unset
CLAUDE_DEFAULT = Path.home() / ".claude" / "projects"
CODEX_DEFAULT = Path.home() / ".codex" / "sessions"


class TestClaudeProjectsDir:
    """Tests for claude_projects_dir."""

    def test_claude_config_dir_relocates_home(self):
        """Test that CLAUDE_CONFIG_DIR replaces ~/.claude."""
        home = Path("/relocated/claude")
        assert (
            claude_projects_dir({"CLAUDE_CONFIG_DIR": str(home)}) == home / "projects"
        )

    def test_unset_uses_default_home(self):
        """Test that an unset CLAUDE_CONFIG_DIR falls back to ~/.claude."""
        assert claude_projects_dir({}) == CLAUDE_DEFAULT

    def test_empty_counts_as_unset(self):
        """Test that an empty CLAUDE_CONFIG_DIR falls back to ~/.claude."""
        assert claude_projects_dir({"CLAUDE_CONFIG_DIR": ""}) == CLAUDE_DEFAULT

    def test_ignores_xdg_config_home(self):
        """Test that XDG_CONFIG_HOME is ignored, as Claude Code ignores it."""
        assert claude_projects_dir({"XDG_CONFIG_HOME": "/xdg"}) == CLAUDE_DEFAULT


class TestCodexSessionsDir:
    """Tests for codex_sessions_dir."""

    def test_codex_home_relocates_home(self):
        """Test that CODEX_HOME replaces ~/.codex."""
        home = Path("/relocated/codex")
        assert codex_sessions_dir({"CODEX_HOME": str(home)}) == home / "sessions"

    def test_unset_uses_default_home(self):
        """Test that an unset CODEX_HOME falls back to ~/.codex."""
        assert codex_sessions_dir({}) == CODEX_DEFAULT

    def test_empty_counts_as_unset(self):
        """Test that an empty CODEX_HOME falls back to ~/.codex."""
        assert codex_sessions_dir({"CODEX_HOME": ""}) == CODEX_DEFAULT

    def test_ignores_xdg_config_home(self):
        """Test that XDG_CONFIG_HOME is ignored, as Codex ignores it."""
        assert codex_sessions_dir({"XDG_CONFIG_HOME": "/xdg"}) == CODEX_DEFAULT
