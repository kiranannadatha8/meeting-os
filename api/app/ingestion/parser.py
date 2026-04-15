"""Transcript parsing — turn an uploaded file (.txt or .vtt) into raw text.

Pure functions, no I/O. Decoded text is what the chunker eats next (T07).
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

SUPPORTED_EXTENSIONS = frozenset({".txt", ".vtt"})

# WebVTT cue timestamp lines look like: "00:00:01.000 --> 00:00:04.000"
_VTT_TIMESTAMP_RE = re.compile(
    r"^\s*\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}.*$"
)


class UnsupportedTranscriptFormatError(ValueError):
    """Raised when an upload has an extension other than .txt or .vtt."""


def parse_transcript(filename: str, body: bytes) -> str:
    """Decode and normalise a transcript upload.

    Why: the rest of the pipeline assumes plain text with `\n` line endings
    and no WebVTT cue scaffolding. Centralising that here lets the route
    handler stay format-agnostic.
    """
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedTranscriptFormatError(
            f"Unsupported transcript extension: {extension or '<none>'}"
        )

    text = body.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")

    if extension == ".vtt":
        return _strip_vtt_scaffolding(text)
    return text


def _strip_vtt_scaffolding(text: str) -> str:
    """Drop the WEBVTT header, cue identifiers, and timestamp lines."""
    lines = text.split("\n")
    output: list[str] = []
    in_header = True

    for raw in lines:
        line = raw.strip()
        if in_header:
            if line == "" or line.upper().startswith("WEBVTT"):
                continue
            in_header = False

        if _VTT_TIMESTAMP_RE.match(line):
            continue
        if _is_vtt_cue_identifier(line, raw, lines, output):
            continue

        output.append(raw)

    return "\n".join(output).strip() + ("\n" if text.endswith("\n") else "")


def _is_vtt_cue_identifier(
    stripped: str, raw: str, all_lines: list[str], output: list[str]
) -> bool:
    """A cue identifier is a non-empty line that immediately precedes a
    timestamp line. It's optional in WebVTT and easy to spot positionally."""
    if not stripped:
        return False
    try:
        idx = all_lines.index(raw)
    except ValueError:
        return False
    if idx + 1 >= len(all_lines):
        return False
    return bool(_VTT_TIMESTAMP_RE.match(all_lines[idx + 1].strip()))
