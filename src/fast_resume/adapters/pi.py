"""pi (numtide/llm-agents) coding agent session adapter."""

import orjson
from datetime import datetime
from pathlib import Path

from ..config import AGENTS, PI_DIR
from ..logging_config import log_parse_error
from .base import BaseSessionAdapter, ErrorCallback, ParseError, Session, truncate_title


class PiAdapter(BaseSessionAdapter):
    """Adapter for pi coding agent sessions.

    pi stores one JSONL file per session under
    ~/.config/pi/agent/sessions/<encoded-cwd>/<timestamp>_<uuid>.jsonl.
    Line types of interest:
        - "session": carries the session ``id`` and ``cwd``
        - "session_info": carries a human ``name`` used as the title
        - "message": ``{message: {role, content: [{type: "text", text}]}}``
    """

    name = "pi"
    color = AGENTS["pi"]["color"]
    badge = AGENTS["pi"]["badge"]
    supports_yolo = False

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._sessions_dir = sessions_dir if sessions_dir is not None else PI_DIR

    def find_sessions(self) -> list[Session]:
        """Find all pi sessions."""
        if not self.is_available():
            return []

        sessions = []
        for session_file in self._sessions_dir.rglob("*.jsonl"):
            session = self._parse_session_file(session_file)
            if session:
                sessions.append(session)

        return sessions

    @staticmethod
    def _extract_text(content: object) -> list[str]:
        """Pull text parts out of a pi message ``content`` value."""
        texts: list[str] = []
        if isinstance(content, str):
            if content.strip():
                texts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text", "")
                    if text:
                        texts.append(text)
        return texts

    def _parse_session_file(
        self, session_file: Path, on_error: ErrorCallback = None
    ) -> Session | None:
        """Parse a pi session file."""
        try:
            session_id = ""
            directory = ""
            title = ""
            session_name = ""  # canonical name: session_info or a user-sourced title
            # mtime reflects last activity → recency sort, matching other adapters
            timestamp = datetime.fromtimestamp(session_file.stat().st_mtime)
            messages: list[str] = []
            user_prompts: list[str] = []  # Actual human inputs for title fallback
            turn_count = 0  # Count user + assistant turns

            with open(session_file, "rb") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = orjson.loads(line)
                    except orjson.JSONDecodeError:
                        continue

                    msg_type = data.get("type", "")

                    if msg_type == "session":
                        session_id = data.get("id", "") or session_id
                        directory = data.get("cwd", "") or directory
                        # omp and newer pi carry the canonical name as a
                        # user-sourced title on the session header itself.
                        if data.get("titleSource") == "user":
                            header_title = data.get("title", "")
                            if header_title:
                                session_name = header_title
                    elif msg_type == "title":
                        # A standalone rename record (omp). Only user-sourced
                        # titles are canonical names; auto/assistant titles are
                        # display-only. Latest wins (records are chronological).
                        if (
                            data.get("source") == "user"
                            or data.get("titleSource") == "user"
                        ):
                            new_title = data.get("title", "")
                            if new_title:
                                session_name = new_title
                    elif msg_type == "session_info":
                        # Older pi format: an explicit session-name record.
                        name = data.get("name", "")
                        if name:
                            session_name = name
                    elif msg_type == "message":
                        message = data.get("message", {})
                        role = message.get("role", "")
                        if role in ("user", "assistant"):
                            role_prefix = "» " if role == "user" else "  "
                            text_parts = self._extract_text(message.get("content", []))
                            for text in text_parts:
                                messages.append(f"{role_prefix}{text}")
                                if role == "user":
                                    user_prompts.append(text)
                            if text_parts:
                                turn_count += 1

            if not session_id:
                # filename: 2026-05-06T19-41-14-673Z_<uuid>.jsonl
                stem = session_file.stem
                session_id = stem.split("_", 1)[-1] if "_" in stem else stem

            # Skip sessions with no actual user prompt (system-only/aborted)
            if not user_prompts:
                return None

            # Prefer the canonical session name; fall back to first user prompt.
            title = session_name or truncate_title(
                user_prompts[0], max_length=80, word_break=False
            )

            full_content = "\n\n".join(messages)

            return Session(
                id=session_id,
                agent=self.name,
                title=title,
                directory=directory,
                timestamp=timestamp,
                content=full_content,
                message_count=turn_count,
                yolo=False,
                name=session_name,
            )
        except OSError as e:
            error = ParseError(
                agent=self.name,
                file_path=str(session_file),
                error_type="OSError",
                message=str(e),
            )
            log_parse_error(
                error.agent, error.file_path, error.error_type, error.message
            )
            if on_error:
                on_error(error)
            return None
        except (KeyError, TypeError, AttributeError) as e:
            error = ParseError(
                agent=self.name,
                file_path=str(session_file),
                error_type=type(e).__name__,
                message=str(e),
            )
            log_parse_error(
                error.agent, error.file_path, error.error_type, error.message
            )
            if on_error:
                on_error(error)
            return None

    def _get_session_id_from_file(self, session_file: Path) -> str:
        """Extract session ID from the ``session`` line or the filename."""
        try:
            with open(session_file, "rb") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = orjson.loads(line)
                    except orjson.JSONDecodeError:
                        continue
                    if data.get("type") == "session":
                        session_id = data.get("id", "")
                        if session_id:
                            return session_id
                        break
        except OSError:
            pass

        stem = session_file.stem
        return stem.split("_", 1)[-1] if "_" in stem else stem

    def _scan_session_files(self) -> dict[str, tuple[Path, float]]:
        """Scan all pi session files."""
        current_files: dict[str, tuple[Path, float]] = {}

        for session_file in self._sessions_dir.rglob("*.jsonl"):
            try:
                mtime = session_file.stat().st_mtime
            except OSError:
                continue
            session_id = self._get_session_id_from_file(session_file)
            current_files[session_id] = (session_file, mtime)

        return current_files

    def get_resume_command(self, session: Session, yolo: bool = False) -> list[str]:
        """Get command to resume a pi session.

        pi resolves a specific session by id (partial UUID accepted) via
        ``--session``; the calling shell has already cd'd into the session
        directory, so pi looks it up in its own session store.
        """
        return ["pi", "--session", session.id]
