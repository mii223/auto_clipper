"""CLI orchestrator for the auto_clipper pipeline."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import config
from modules.analyzer import analyze_transcript
from modules.downloader import prepare_media
from modules.editor import create_vertical_clip
from modules.subtitler import burn_subtitles
from modules.transcriber import transcribe_audio


def _sanitize_filename(title: str, fallback: str) -> str:
    """Sanitize a clip title for Windows-safe output filenames."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = cleaned.strip("._")
    return cleaned[:50] if cleaned else fallback


def run_pipeline(source: str, max_clips: int = 3) -> list[Path]:
    """Run the full auto_clipper pipeline and return paths to final clips."""
    if max_clips < 1:
        raise ValueError("--max-clips must be at least 1.")

    print(f"[1/5] Preparing media from source: {source}")
    video_path, audio_path = prepare_media(source)
    print(f"      Video ready: {video_path}")
    print(f"      Audio ready: {audio_path}")

    print("[2/5] Transcribing audio with faster-whisper...")
    transcript_path = transcribe_audio(audio_path)
    print(f"      Transcript saved: {transcript_path}")

    print("[3/5] Analyzing transcript with Gemini to select viral clips...")
    clips = analyze_transcript(transcript_path)
    selected_clips = clips[:max_clips]
    if not selected_clips:
        raise RuntimeError("No clips were returned by the analyzer.")
    print(f"      Selected {len(selected_clips)} clip(s) (max_clips={max_clips}).")

    print(f"[4/5] Rendering {len(selected_clips)} vertical subtitled clip(s)...")
    final_outputs: list[Path] = []
    for idx, clip in enumerate(selected_clips, start=1):
        start_time = float(clip["start_time"])
        end_time = float(clip["end_time"])
        title = str(clip.get("title", f"clip_{idx}"))
        safe_title = _sanitize_filename(title, fallback=f"clip_{idx}")

        print(
            f"      -> Clip {idx}/{len(selected_clips)}: "
            f"{title} ({start_time:.2f}s - {end_time:.2f}s)"
        )
        raw_clip_path = config.TEMP_DIR / f"clip_{idx}_raw.mp4"
        vertical_clip = create_vertical_clip(
            video_path=video_path,
            start_time=start_time,
            end_time=end_time,
            output_path=raw_clip_path,
        )

        final_clip_path = config.OUTPUT_DIR / f"clip_{idx}_{safe_title}.mp4"
        subtitled_clip = burn_subtitles(
            video_path=vertical_clip,
            start_time=start_time,
            end_time=end_time,
            output_path=final_clip_path,
            transcript_path=transcript_path,
            ass_path=config.TEMP_DIR / f"clip_{idx}.ass",
        )
        final_outputs.append(subtitled_clip)
        print(f"         Saved: {subtitled_clip}")

    print("[5/5] Pipeline complete!")
    for out in final_outputs:
        print(f"      - {out}")

    return final_outputs


def main() -> None:
    """Parse CLI arguments and launch the auto_clipper pipeline."""
    parser = argparse.ArgumentParser(
        description="Convert a long horizontal video or YouTube URL into viral vertical clips."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Local MP4 file path or YouTube video URL.",
    )
    parser.add_argument(
        "--max-clips",
        type=int,
        default=3,
        help="Maximum number of clips to generate (default: 3).",
    )
    args = parser.parse_args()

    run_pipeline(source=args.source, max_clips=args.max_clips)


if __name__ == "__main__":
    main()
