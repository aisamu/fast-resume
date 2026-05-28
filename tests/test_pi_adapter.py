"""Tests for pi session adapter."""

import json
from datetime import datetime

import pytest

from fast_resume.adapters.pi import PiAdapter


@pytest.fixture
def adapter():
    """Create a PiAdapter instance."""
    return PiAdapter()


@pytest.fixture
def pi_session_data():
    """Sample pi session JSONL data."""
    return [
        {
            "type": "session",
            "id": "abc123",
            "timestamp": "2026-05-06T19:41:14.673Z",
            "cwd": "/home/user/project",
        },
        {"type": "session_info", "name": "refactor the parser"},
        {
            "type": "message",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "Help me refactor this function"}],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Here's the refactored code."}],
            },
        },
    ]


@pytest.fixture
def pi_session_file(temp_dir, pi_session_data):
    """Create a mock pi session file under an encoded-cwd subdir."""
    session_dir = temp_dir / "--home-user-project--"
    session_dir.mkdir(parents=True)
    session_file = session_dir / "2026-05-06T19-41-14-673Z_abc123.jsonl"

    with open(session_file, "w") as f:
        for entry in pi_session_data:
            f.write(json.dumps(entry) + "\n")

    return session_file


class TestPiAdapter:
    """Tests for PiAdapter."""

    def test_name_and_attributes(self, adapter):
        """Test adapter has correct name and attributes."""
        assert adapter.name == "pi"
        assert adapter.color is not None
        assert adapter.badge == "pi"
        assert adapter.supports_yolo is False

    def test_parse_session_basic(self, adapter, pi_session_file):
        """Test parsing a basic pi session file."""
        session = adapter._parse_session_file(pi_session_file)

        assert session is not None
        assert session.agent == "pi"
        assert session.id == "abc123"
        assert session.directory == "/home/user/project"
        assert "Help me refactor" in session.content
        assert "Here's the refactored code." in session.content
        assert session.message_count == 2

    def test_title_prefers_session_info_name(self, adapter, pi_session_file):
        """Title comes from session_info.name when present."""
        session = adapter._parse_session_file(pi_session_file)

        assert session is not None
        assert session.title == "refactor the parser"

    def test_title_falls_back_to_first_user_prompt(self, adapter, temp_dir):
        """Without session_info, title is the first user prompt."""
        session_file = temp_dir / "session.jsonl"

        data = [
            {"type": "session", "id": "test123", "cwd": "/test"},
            {
                "type": "message",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "First prompt"}],
                },
            },
            {
                "type": "message",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Second prompt"}],
                },
            },
        ]

        with open(session_file, "w") as f:
            for entry in data:
                f.write(json.dumps(entry) + "\n")

        session = adapter._parse_session_file(session_file)

        assert session is not None
        assert "First prompt" in session.title
        assert "Second prompt" in session.content

    def test_parse_session_extracts_id_from_filename(self, adapter, temp_dir):
        """Session ID falls back to the filename's uuid part."""
        session_file = temp_dir / "2026-05-06T19-41-14-673Z_fallback123.jsonl"

        data = [
            {
                "type": "message",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Test prompt"}],
                },
            },
        ]

        with open(session_file, "w") as f:
            for entry in data:
                f.write(json.dumps(entry) + "\n")

        session = adapter._parse_session_file(session_file)

        assert session is not None
        assert session.id == "fallback123"

    def test_parse_session_no_user_prompts_returns_none(self, adapter, temp_dir):
        """Sessions without any user prompt return None."""
        session_file = temp_dir / "session.jsonl"

        data = [
            {"type": "session", "id": "test123", "cwd": "/test"},
            {"type": "session_info", "name": "named but empty"},
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Just assistant"}],
                },
            },
        ]

        with open(session_file, "w") as f:
            for entry in data:
                f.write(json.dumps(entry) + "\n")

        session = adapter._parse_session_file(session_file)

        assert session is None

    def test_parse_session_truncates_long_title_fallback(self, adapter, temp_dir):
        """Long first-prompt titles are truncated (when no session_info)."""
        session_file = temp_dir / "session.jsonl"

        long_message = "A" * 200
        data = [
            {"type": "session", "id": "test123", "cwd": "/test"},
            {
                "type": "message",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": long_message}],
                },
            },
        ]

        with open(session_file, "w") as f:
            for entry in data:
                f.write(json.dumps(entry) + "\n")

        session = adapter._parse_session_file(session_file)

        assert session is not None
        assert len(session.title) <= 83  # 80 + "..."
        assert session.title.endswith("...")

    def test_ignores_non_text_content_parts(self, adapter, temp_dir):
        """Non-text content parts (e.g. tool calls) are skipped."""
        session_file = temp_dir / "session.jsonl"

        data = [
            {"type": "session", "id": "test123", "cwd": "/test"},
            {
                "type": "message",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Real prompt"},
                        {"type": "tool_use", "name": "read", "input": {}},
                    ],
                },
            },
        ]

        with open(session_file, "w") as f:
            for entry in data:
                f.write(json.dumps(entry) + "\n")

        session = adapter._parse_session_file(session_file)

        assert session is not None
        assert "Real prompt" in session.content
        assert "tool_use" not in session.content

    def test_parse_malformed_json(self, adapter, temp_dir):
        """Malformed lines are skipped, valid lines still parsed."""
        session_file = temp_dir / "session.jsonl"

        with open(session_file, "w") as f:
            f.write("not json\n")
            f.write(json.dumps({"type": "session", "id": "test123", "cwd": "/test"}) + "\n")
            f.write(
                json.dumps(
                    {
                        "type": "message",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": "Valid"}],
                        },
                    }
                )
                + "\n"
            )

        session = adapter._parse_session_file(session_file)

        assert session is not None
        assert "Valid" in session.content

    def test_get_resume_command(self, adapter):
        """Resume command resolves a session by id."""
        from fast_resume.adapters.base import Session

        session = Session(
            id="019df9c2-e868-7488-8fdd-53dedfc3689d",
            agent="pi",
            title="Test",
            directory="/test",
            timestamp=datetime.now(),
            content="",
        )

        cmd = adapter.get_resume_command(session)

        assert cmd == ["pi", "--session", "019df9c2-e868-7488-8fdd-53dedfc3689d"]

    def test_find_sessions_recursive(self, temp_dir):
        """find_sessions searches recursively across encoded-cwd subdirs."""
        for i, name in enumerate(["--home-a--", "--home-b--"]):
            d = temp_dir / name
            d.mkdir(parents=True)
            session_file = d / f"2026-05-0{i + 1}T00-00-00-000Z_id{i}.jsonl"
            with open(session_file, "w") as f:
                f.write(json.dumps({"type": "session", "id": f"id{i}", "cwd": "/test"}) + "\n")
                f.write(
                    json.dumps(
                        {
                            "type": "message",
                            "message": {
                                "role": "user",
                                "content": [{"type": "text", "text": f"Prompt {i}"}],
                            },
                        }
                    )
                    + "\n"
                )

        adapter = PiAdapter(sessions_dir=temp_dir)
        sessions = adapter.find_sessions()

        assert len(sessions) == 2

    def test_scan_skips_dangling_symlinks(self, temp_dir):
        """Dangling symlinks don't crash _scan_session_files."""
        session_dir = temp_dir / "--home-project--"
        session_dir.mkdir(parents=True)

        valid_file = session_dir / "2026-05-06T00-00-00-000Z_valid123.jsonl"
        with open(valid_file, "w") as f:
            f.write(json.dumps({"type": "session", "id": "valid123", "cwd": "/test"}) + "\n")

        dangling = session_dir / ".#2026-05-06T00-00-00-000Z_broken.jsonl"
        dangling.symlink_to(temp_dir / "nonexistent.jsonl")

        adapter = PiAdapter(sessions_dir=temp_dir)
        files = adapter._scan_session_files()

        assert len(files) == 1
        assert "valid123" in files
