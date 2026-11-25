"""Subtitle generation (.ass) and FFmpeg burn-in module for auto_clipper."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import config
except ModuleNotFoundError:  # Allow direct execution via `python modules\subtitler.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config


RTL_LANGUAGES = {"ar", "fa", "he", "ur", "ps", "sd", "yi"}
SENTENCE_END_PUNCT = (".", "!", "?", "؟", "،", ";", ":")


def _hex_to_ass_color(hex_color: str) -> str:
    """Convert #RRGGBB hex color into ASS &H00BBGGRR format."""
    cleaned = hex_color.strip().lstrip("#")
    if len(cleaned) != 6:
        raise ValueError(f"Expected 6-digit hex color, got: {hex_color}")
    rr, gg, bb = cleaned[0:2], cleaned[2:4], cleaned[4:6]
    return f"&H00{bb.upper()}{gg.upper()}{rr.upper()}"


def _format_ass_timestamp(seconds: float) -> str:
    """Format seconds into ASS timestamp H:MM:SS.cs."""
    total_cs = max(0, round(seconds * 100))
    cs = total_cs % 100
    total_seconds = total_cs // 100
    sec = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours}:{minutes:02d}:{sec:02d}.{cs:02d}"


def _escape_ass_text(text: str) -> str:
    """Escape ASS special braces/backslashes in subtitle text."""
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _escape_ffmpeg_filter_path(path: Path) -> str:
    """Escape a Windows path for FFmpeg's subtitles filter."""
    escaped = str(path.resolve())
    escaped = escaped.replace("\\", "\\\\")
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace("'", "'\\\\\\''")
    return f"'{escaped}'"


def _extract_clip_words(
    transcript_data: dict[str, Any],
    start_time: float,
    end_time: float,
) -> list[dict[str, Any]]:
    """Slice word timestamps within [start_time, end_time] and offset to 0.0."""
    clip_duration = float(end_time) - float(start_time)
    if clip_duration <= 0:
        raise ValueError(
            f"Invalid clip range: start_time={start_time}, end_time={end_time}"
        )

    words: list[dict[str, Any]] = []
    for seg in transcript_data.get("segments", []):
        for w in seg.get("words", []):
            text = str(w.get("word", "")).strip()
            if not text:
                continue
            w_start = float(w["start"])
            w_end = float(w["end"])
            midpoint = (w_start + w_end) / 2.0
            if not (start_time <= midpoint <= end_time):
                continue

            offset_start = max(0.0, w_start - start_time)
            offset_end = min(clip_duration, w_end - start_time)
            if offset_end <= offset_start:
                offset_end = min(clip_duration, offset_start + 0.08)
            if offset_end > offset_start:
                words.append(
                    {
                        "word": text,
                        "start": offset_start,
                        "end": offset_end,
                    }
                )
    return words


def _group_words_into_chunks(
    words: list[dict[str, Any]],
    max_words: int = 4,
    min_words_on_break: int = 3,
    pause_threshold: float = 0.6,
) -> list[list[dict[str, Any]]]:
    """Group words into short chunks of 3-4 words per subtitle line."""
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for idx, word in enumerate(words):
        current.append(word)
        is_last = idx == len(words) - 1
        if is_last:
            chunks.append(current)
            current = []
            continue

        next_word = words[idx + 1]
        gap = float(next_word["start"]) - float(word["end"])
        ends_sentence = str(word["word"]).endswith(SENTENCE_END_PUNCT)

        if len(current) >= max_words or (
            len(current) >= min_words_on_break and (ends_sentence or gap > pause_threshold)
        ):
            chunks.append(current)
            current = []

    if current:
        chunks.append(current)
    return chunks


def generate_ass_subtitles(
    transcript_path: Path,
    start_time: float,
    end_time: float,
    ass_output_path: Path,
) -> tuple[Path, int]:
    """Generate a UTF-8 .ass file with per-word highlighting and RTL support."""
    with Path(transcript_path).open("r", encoding="utf-8") as f:
        transcript_data = json.load(f)

    language = str(transcript_data.get("language", "")).strip().lower()
    is_rtl = language in RTL_LANGUAGES

    words = _extract_clip_words(transcript_data, start_time, end_time)
    chunks = _group_words_into_chunks(words)

    primary_ass = _hex_to_ass_color(config.SUBTITLE_PRIMARY_COLOR)
    highlight_ass = _hex_to_ass_color(config.SUBTITLE_HIGHLIGHT_COLOR)
    outline_ass = _hex_to_ass_color(config.SUBTITLE_OUTLINE_COLOR)

    header = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {config.TARGET_WIDTH}",
            f"PlayResY: {config.TARGET_HEIGHT}",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{config.SUBTITLE_FONT_NAME},{config.SUBTITLE_FONT_SIZE},"
            f"{primary_ass},{highlight_ass},{outline_ass},&H80000000,-1,0,0,0,100,100,0,0,"
            f"1,{config.SUBTITLE_OUTLINE_WIDTH},2,2,60,60,420,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )

    events: list[str] = []
    for chunk in chunks:
        for i, active_word in enumerate(chunk):
            ev_start = float(active_word["start"])
            if i + 1 < len(chunk):
                next_start = float(chunk[i + 1]["start"])
                ev_end = (
                    next_start
                    if 0.0 <= next_start - float(active_word["end"]) <= 0.35
                    else float(active_word["end"])
                )
            else:
                ev_end = float(active_word["end"])

            if ev_end <= ev_start:
                continue

            parts: list[str] = []
            for j, item in enumerate(chunk):
                token = _escape_ass_text(str(item["word"]))
                color = highlight_ass if j == i else primary_ass
                parts.append(f"{{\\c{color}&}}{token}{{\\c{primary_ass}&}}")

            line_text = " ".join(parts)
            if is_rtl:
                # Wrap in Unicode RLE/PDF so FriBidi keeps right-to-left word order.
                line_text = f"\u202b{line_text}\u202c"

            events.append(
                f"Dialogue: 0,{_format_ass_timestamp(ev_start)},"
                f"{_format_ass_timestamp(ev_end)},Default,,0,0,0,,{line_text}"
            )

    ass_file = Path(ass_output_path).expanduser().resolve()
    ass_file.parent.mkdir(parents=True, exist_ok=True)
    with ass_file.open("w", encoding="utf-8") as f:
        f.write(header + "\n" + "\n".join(events) + "\n")

    return ass_file, len(events)


def burn_subtitles(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_path: Path,
    transcript_path: Path | None = None,
    ass_path: Path | None = None,
) -> Path:
    """Generate .ass subtitles for [start_time, end_time] and burn them onto video_path."""
    source_video = Path(video_path).expanduser().resolve()
    if not source_video.is_file():
        raise FileNotFoundError(f"Vertical clip video not found: {source_video}")

    transcript_file = (
        Path(transcript_path).expanduser().resolve()
        if transcript_path is not None
        else (config.TEMP_DIR / "transcript.json").resolve()
    )
    if not transcript_file.is_file():
        raise FileNotFoundError(f"Transcript file not found: {transcript_file}")

    dest_file = Path(output_path).expanduser().resolve()
    dest_file.parent.mkdir(parents=True, exist_ok=True)

    subtitle_file = (
        Path(ass_path).expanduser().resolve()
        if ass_path is not None
        else (config.TEMP_DIR / f"{dest_file.stem}.ass").resolve()
    )

    generated_ass, event_count = generate_ass_subtitles(
        transcript_path=transcript_file,
        start_time=start_time,
        end_time=end_time,
        ass_output_path=subtitle_file,
    )

    if event_count == 0:
        shutil.copy2(source_video, dest_file)
        return dest_file

    escaped_ass = _escape_ffmpeg_filter_path(generated_ass)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_video),
        "-vf",
        f"subtitles={escaped_ass}",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(dest_file),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffmpeg executable not found. Ensure FFmpeg is installed and added to PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"ffmpeg failed while burning subtitles (exit code {exc.returncode}):\n{exc.stderr}"
        ) from exc

    return dest_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test subtitle burning on an existing vertical clip."
    )
    parser.add_argument(
        "video_path",
        nargs="?",
        default=str(config.OUTPUT_DIR / "test_clip_1.mp4"),
        help="Path to the vertical clip MP4 (defaults to output/test_clip_1.mp4).",
    )
    args = parser.parse_args()

    clips_file = config.TEMP_DIR / "clips.json"
    if not clips_file.is_file():
        raise FileNotFoundError(f"Clips file not found: {clips_file}")

    with clips_file.open("r", encoding="utf-8") as f:
        clips = json.load(f).get("clips", [])
    if not clips:
        raise ValueError(f"No clips found in {clips_file}")

    first_clip = clips[0]
    final_path = burn_subtitles(
        video_path=Path(args.video_path),
        start_time=float(first_clip["start_time"]),
        end_time=float(first_clip["end_time"]),
        output_path=config.OUTPUT_DIR / "test_clip_1_subtitled.mp4",
    )
    print(f"Subtitled clip saved to: {final_path}")
