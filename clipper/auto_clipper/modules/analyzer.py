"""Viral clip analyzer using the official google-genai SDK."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

try:
    import config
except ModuleNotFoundError:  # Allow direct execution via `python modules\analyzer.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config


SYSTEM_INSTRUCTION = """You are an expert viral short-form video editor (TikTok, YouTube Shorts, Instagram Reels).
Analyze the provided timestamped transcript and select 3 to 5 standalone, high-retention video clips.

Strict rules:
1. Each clip MUST be strictly between 30 and 60 seconds long (30 <= end_time - start_time <= 60).
2. Each clip must start with a strong, attention-grabbing hook and feel complete on its own.
3. Clip timestamps MUST NOT overlap with each other.
4. Use exact or clean boundary timestamps present in the transcript.
5. Write the `title` and `reason` in the EXACT same language as the transcript.
6. Score each clip's hook strength with `hook_score` as an integer from 1 to 10 (10 being strongest)."""


class ClipSuggestion(BaseModel):
    """Schema for a single suggested viral clip."""

    start_time: float = Field(description="Clip start time in seconds.")
    end_time: float = Field(description="Clip end time in seconds.")
    title: str = Field(description="Catchy short-form title in the transcript language.")
    hook_score: int = Field(description="Hook strength score from 1 to 10.")
    reason: str = Field(description="Why this clip works well, in the transcript language.")


class ClipsResponse(BaseModel):
    """Top-level JSON schema returned by Gemini."""

    clips: list[ClipSuggestion]


def _format_compact_transcript(transcript_data: dict[str, Any]) -> str:
    """Format transcript segments into compact `[start - end] text` lines."""
    lines: list[str] = []
    for seg in transcript_data.get("segments", []):
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        start = float(seg["start"])
        end = float(seg["end"])
        lines.append(f"[{start:.2f} - {end:.2f}] {text}")
    return "\n".join(lines)


def analyze_transcript(transcript_path: Path | None = None) -> list[dict[str, Any]]:
    """Analyze temp/transcript.json with Gemini and save suggested clips to temp/clips.json."""
    load_dotenv(dotenv_path=config.BASE_DIR / ".env")
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        raise RuntimeError(
            "GEMINI_API_KEY is missing or unset. Copy .env.example to .env and add your key."
        )

    source_path = (
        Path(transcript_path).expanduser().resolve()
        if transcript_path is not None
        else (config.TEMP_DIR / "transcript.json").resolve()
    )
    if not source_path.is_file():
        raise FileNotFoundError(f"Transcript file not found: {source_path}")

    with source_path.open("r", encoding="utf-8") as f:
        transcript_data = json.load(f)

    compact_transcript = _format_compact_transcript(transcript_data)
    if not compact_transcript:
        raise ValueError(f"Transcript contains no non-empty segments: {source_path}")

    language = transcript_data.get("language", "unknown")
    user_prompt = (
        f"Transcript language: {language}\n\n"
        f"Transcript:\n{compact_transcript}"
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=ClipsResponse,
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")

    parsed = json.loads(response.text)
    clips: list[dict[str, Any]] = parsed.get("clips", [])

    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    clips_path = (config.TEMP_DIR / "clips.json").resolve()
    with clips_path.open("w", encoding="utf-8") as f:
        json.dump({"clips": clips}, f, ensure_ascii=False, indent=2)

    return clips


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze temp/transcript.json and pick viral short-form clips."
    )
    parser.add_argument(
        "transcript_path",
        nargs="?",
        default=str(config.TEMP_DIR / "transcript.json"),
        help="Path to transcript JSON file (defaults to temp/transcript.json).",
    )
    args = parser.parse_args()

    suggested_clips = analyze_transcript(Path(args.transcript_path))
    print(f"Saved {len(suggested_clips)} clips to {config.TEMP_DIR / 'clips.json'}:")
    print(json.dumps(suggested_clips, ensure_ascii=False, indent=2))
