"""Unit tests for transcript parser — pure-function, no I/O."""
from __future__ import annotations

import pytest

from app.ingestion.parser import (
    UnsupportedTranscriptFormatError,
    parse_transcript,
)


class TestParseTxt:
    def test_returns_decoded_text_unchanged(self) -> None:
        body = b"Alice: hello world\nBob: hi"
        result = parse_transcript("notes.txt", body)
        assert result == "Alice: hello world\nBob: hi"

    def test_strips_utf8_bom(self) -> None:
        body = b"\xef\xbb\xbfHello"
        result = parse_transcript("notes.txt", body)
        assert result == "Hello"

    def test_normalises_crlf_line_endings(self) -> None:
        body = b"line one\r\nline two\r\n"
        result = parse_transcript("notes.txt", body)
        assert result == "line one\nline two\n"


class TestParseVtt:
    def test_strips_webvtt_header_and_cue_timestamps(self) -> None:
        body = (
            b"WEBVTT\n\n"
            b"00:00:01.000 --> 00:00:04.000\n"
            b"Alice: Welcome to the meeting.\n\n"
            b"00:00:05.000 --> 00:00:07.500\n"
            b"Bob: Thanks for joining.\n"
        )
        result = parse_transcript("call.vtt", body)
        assert "WEBVTT" not in result
        assert "00:00:01" not in result
        assert "Alice: Welcome to the meeting." in result
        assert "Bob: Thanks for joining." in result

    def test_ignores_cue_identifiers(self) -> None:
        body = (
            b"WEBVTT\n\n"
            b"cue-1\n"
            b"00:00:01.000 --> 00:00:02.000\n"
            b"Just text.\n"
        )
        result = parse_transcript("call.vtt", body)
        assert "cue-1" not in result
        assert result.strip() == "Just text."


class TestUnsupportedExtensions:
    @pytest.mark.parametrize("filename", ["notes.pdf", "audio.mp3", "weird", "notes.TXT.zip"])
    def test_rejects_non_txt_vtt(self, filename: str) -> None:
        with pytest.raises(UnsupportedTranscriptFormatError):
            parse_transcript(filename, b"anything")

    def test_extension_match_is_case_insensitive(self) -> None:
        result = parse_transcript("Notes.TXT", b"hello")
        assert result == "hello"
