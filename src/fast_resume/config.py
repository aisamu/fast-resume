"""Configuration and constants for fast-resume."""

import os
from collections.abc import Mapping
from pathlib import Path

# Agent colors and badges (badge is the display name shown in UI)
AGENTS = {
    "claude": {"color": "#E87B35", "badge": "claude"},
    "codex": {"color": "#00A67E", "badge": "codex"},
    "pi": {"color": "#E535AB", "badge": "pi"},
    "opencode": {"color": "#CFCECD", "badge": "opencode"},
    "vibe": {"color": "#FF6B35", "badge": "vibe"},
    "crush": {"color": "#6B51FF", "badge": "crush"},
    "copilot-cli": {"color": "#9CA3AF", "badge": "copilot"},
    "copilot-vscode": {"color": "#007ACC", "badge": "vscode"},
}


# Resolve each agent's home the way the agent does, so that every indexed
# session is one its --resume can find. None of them reads XDG variables.
# An empty value counts as unset, matching Codex and pi.
def claude_projects_dir(environ: Mapping[str, str] = os.environ) -> Path:
    """Return $CLAUDE_CONFIG_DIR/projects, or ~/.claude/projects if unset."""
    home = environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"
    return Path(home) / "projects"


def codex_sessions_dir(environ: Mapping[str, str] = os.environ) -> Path:
    """Return $CODEX_HOME/sessions, or ~/.codex/sessions if unset."""
    home = environ.get("CODEX_HOME") or Path.home() / ".codex"
    return Path(home) / "sessions"


def pi_sessions_dir(environ: Mapping[str, str] = os.environ) -> Path:
    """Return $PI_CODING_AGENT_DIR/sessions, or ~/.pi/agent/sessions if unset.

    Unlike Claude Code and Codex, pi expands a leading "~" itself. Sessions
    relocated through PI_CODING_AGENT_SESSION_DIR or the sessionDir setting
    are stored flat, without per-cwd folders, and are not found here.
    """
    home = environ.get("PI_CODING_AGENT_DIR") or "~/.pi/agent"
    if home == "~" or home.startswith("~/"):
        home = os.path.expanduser(home)
    return Path(home) / "sessions"


# Storage paths
CLAUDE_DIR = claude_projects_dir()
CODEX_DIR = codex_sessions_dir()
PI_DIR = pi_sessions_dir()
OPENCODE_DIR = Path.home() / ".local" / "share" / "opencode"
OPENCODE_LEGACY_DIR = OPENCODE_DIR / "storage"
OPENCODE_DB = OPENCODE_DIR / "opencode.db"
VIBE_DIR = Path.home() / ".vibe" / "logs" / "session"
CRUSH_PROJECTS_FILE = Path.home() / ".local" / "share" / "crush" / "projects.json"
COPILOT_DIR = Path.home() / ".copilot" / "session-state"

# Storage location
CACHE_DIR = Path.home() / ".cache" / "fast-resume"
INDEX_DIR = CACHE_DIR / "tantivy_index"
LOG_FILE = CACHE_DIR / "parse-errors.log"
SCHEMA_VERSION = (
    20  # Bump when schema changes (20: fast timestamp field for sorting by date)
)
