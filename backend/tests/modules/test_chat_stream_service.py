"""Tests for the pure service logic of SSE chat streaming.

These tests are isolated from FastAPI and Redis — we just test the
frame-building and event-relaying logic with hand-built fakes.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import pytest

from app.modules.chat.service import PubSubLike, relay_job_events, sse_frame


class FakePubSub:
    """A controllable fake pubsub for testing relay_job_events without real Redis."""

    def __init__(self, messages: list[dict] | None = None) -> None:
        self.messages = messages or []
        self._index = 0

    async def listen(self) -> AsyncIterator[dict]:
        for message in self.messages:
            yield message
            self._index += 1


class TestSSEFrame:
    """Tests for sse_frame() helper that builds SSE message bytes."""

    def test_sse_frame_encodes_json_payload(self) -> None:
        payload = {"type": "token", "delta": "hello"}
        result = sse_frame(payload)
        assert result == b'data: {"type":"token","delta":"hello"}\n\n'

    def test_sse_frame_handles_empty_dict(self) -> None:
        result = sse_frame({})
        assert result == b"data: {}\n\n"

    def test_sse_frame_handles_complex_payload(self) -> None:
        payload = {
            "type": "done",
            "reply": "Hello world",
            "session_id": "sess-123",
            "iterations": 2,
            "stopped_on": "final_answer",
        }
        result = sse_frame(payload)
        decoded = result.decode().strip()
        assert decoded.startswith("data: ")
        data_str = decoded[6:]  # strip "data: "
        reparsed = json.loads(data_str)
        assert reparsed == payload


class TestRelayJobEvents:
    """Tests for relay_job_events() async generator that reads pubsub and yields frames."""

    @pytest.mark.asyncio
    async def test_relay_job_events_yields_frames_then_stops_on_done(self) -> None:
        """Fake pubsub yields subscription confirmation, a token, and done.
        Only the token and done should be yielded as frames, and iteration stops."""
        fake_pubsub = FakePubSub(
            [
                {"type": "subscribe", "pattern": None, "channel": b"chat:job:123", "data": 1},
                {"type": "message", "pattern": None, "channel": b"chat:job:123", "data": b'{"type":"token","delta":"hi"}'},
                {"type": "message", "pattern": None, "channel": b"chat:job:123", "data": b'{"type":"done","reply":"hi","session_id":"s","iterations":1,"stopped_on":"final_answer"}'},
            ]
        )

        frames = []
        async for frame in relay_job_events(fake_pubsub):
            frames.append(frame)

        assert len(frames) == 2
        # First frame: token
        assert frames[0] == sse_frame({"type": "token", "delta": "hi"})
        # Second frame: done
        assert frames[1] == sse_frame(
            {
                "type": "done",
                "reply": "hi",
                "session_id": "s",
                "iterations": 1,
                "stopped_on": "final_answer",
            }
        )

    @pytest.mark.asyncio
    async def test_relay_job_events_stops_on_error(self) -> None:
        """When an error message is received, stop iteration right after."""
        fake_pubsub = FakePubSub(
            [
                {"type": "message", "pattern": None, "channel": b"chat:job:123", "data": b'{"type":"error","message":"Something went wrong"}'},
            ]
        )

        frames = []
        async for frame in relay_job_events(fake_pubsub):
            frames.append(frame)

        assert len(frames) == 1
        assert frames[0] == sse_frame({"type": "error", "message": "Something went wrong"})

    @pytest.mark.asyncio
    async def test_relay_job_events_ignores_subscribe_confirmation_messages(self) -> None:
        """Subscribe confirmation messages (type != 'message') are skipped."""
        fake_pubsub = FakePubSub(
            [
                {"type": "subscribe", "pattern": None, "channel": b"chat:job:123", "data": 1},
                {"type": "message", "pattern": None, "channel": b"chat:job:123", "data": b'{"type":"done","reply":"ok","session_id":"s","iterations":1,"stopped_on":"final_answer"}'},
            ]
        )

        frames = []
        async for frame in relay_job_events(fake_pubsub):
            frames.append(frame)

        assert len(frames) == 1
        assert json.loads(frames[0].decode().split("data: ")[1])["type"] == "done"

    @pytest.mark.asyncio
    async def test_relay_job_events_decodes_bytes_payload(self) -> None:
        """The 'data' field may be bytes; decode it to str before JSON parsing."""
        fake_pubsub = FakePubSub(
            [
                {"type": "message", "pattern": None, "channel": b"chat:job:123", "data": b'{"type":"token","delta":"test"}'},
                {"type": "message", "pattern": None, "channel": b"chat:job:123", "data": b'{"type":"done","reply":"done","session_id":"s","iterations":1,"stopped_on":"final_answer"}'},
            ]
        )

        frames = []
        async for frame in relay_job_events(fake_pubsub):
            frames.append(frame)

        assert len(frames) == 2
        # Both should have decoded properly
        parsed_token = json.loads(frames[0].decode().split("data: ")[1])
        assert parsed_token["type"] == "token"
        assert parsed_token["delta"] == "test"

    @pytest.mark.asyncio
    async def test_relay_job_events_handles_string_data_too(self) -> None:
        """The 'data' field may be a string instead of bytes."""
        fake_pubsub = FakePubSub(
            [
                {"type": "message", "pattern": None, "channel": "chat:job:123", "data": '{"type":"token","delta":"str_data"}'},
                {"type": "message", "pattern": None, "channel": "chat:job:123", "data": '{"type":"done","reply":"done","session_id":"s","iterations":1,"stopped_on":"final_answer"}'},
            ]
        )

        frames = []
        async for frame in relay_job_events(fake_pubsub):
            frames.append(frame)

        assert len(frames) == 2
        parsed_token = json.loads(frames[0].decode().split("data: ")[1])
        assert parsed_token["type"] == "token"
        assert parsed_token["delta"] == "str_data"

    @pytest.mark.asyncio
    async def test_relay_job_events_multiple_tokens_before_done(self) -> None:
        """Multiple token messages should all be yielded before done."""
        fake_pubsub = FakePubSub(
            [
                {"type": "message", "pattern": None, "channel": b"chat:job:123", "data": b'{"type":"token","delta":"Hi"}'},
                {"type": "message", "pattern": None, "channel": b"chat:job:123", "data": b'{"type":"token","delta":" "}'},
                {"type": "message", "pattern": None, "channel": b"chat:job:123", "data": b'{"type":"token","delta":"there"}'},
                {"type": "message", "pattern": None, "channel": b"chat:job:123", "data": b'{"type":"done","reply":"Hi there","session_id":"s","iterations":1,"stopped_on":"final_answer"}'},
            ]
        )

        frames = []
        async for frame in relay_job_events(fake_pubsub):
            frames.append(frame)

        assert len(frames) == 4
        # Verify token sequence
        assert json.loads(frames[0].decode().split("data: ")[1])["delta"] == "Hi"
        assert json.loads(frames[1].decode().split("data: ")[1])["delta"] == " "
        assert json.loads(frames[2].decode().split("data: ")[1])["delta"] == "there"
        assert json.loads(frames[3].decode().split("data: ")[1])["type"] == "done"
