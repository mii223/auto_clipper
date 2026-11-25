"""Video cutting and 9:16 vertical formatting module using FFmpeg."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    import config
except ModuleNotFoundError:  # Allow direct execution via `python modules\editor.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config


def build_vertical_crop_filter(
    target_width: int = config.TARGET_WIDTH,
    target_height: int = config.TARGET_HEIGHT,
) -> str:
    """Build the FFmpeg video filter string for 9:16 vertical cropping.

    Kept isolated so dynamic face-tracking coordinates can replace the static
    center crop in a future iteration.
    """
    return f"crop=ih*9/16:ih,scale={target_width}:{target_height}"


def create_vertical_clip(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_path: Path,
) -> Path:
    """Cut [start_time, end_time] from video_path and export a 1080x1920 MP4."""
    source_file = Path(video_path).expanduser().resolve()
    if not source_file.is_file():
        raise FileNotFoundError(f"Source video file not found: {source_file}")

    duration = float(end_time) - float(start_time)
    if start_time < 0 or duration <= 0:
        raise ValueError(
            f"Invalid clip timestamps: start_time={start_time}, end_time={end_time}"
        )

    dest_file = Path(output_path).expanduser().resolve()
    dest_file.parent.mkdir(parents=True, exist_ok=True)

    vf_filter = build_vertical_crop_filter(
        target_width=config.TARGET_WIDTH,
        target_height=config.TARGET_HEIGHT,
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{float(start_time):.3f}",
        "-i",
        str(source_file),
        "-t",
        f"{duration:.3f}",
        "-vf",
        vf_filter,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
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
            f"ffmpeg failed while creating clip (exit code {exc.returncode}):\n{exc.stderr}"
        ) from exc

    return dest_file


def _find_default_temp_video() -> Path:
    """Return the first MP4 file in temp/ for standalone testing."""
    mp4_files = sorted(config.TEMP_DIR.glob("*.mp4"))
    if not mp4_files:
        raise FileNotFoundError(
            f"No .mp4 files found in {config.TEMP_DIR}. Pass a video path explicitly."
        )
    return mp4_files[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test vertical clip creation using the first clip from temp/clips.json."
    )
    parser.add_argument(
        "video_path",
        nargs="?",
        default=None,
        help="Optional path to source MP4 (defaults to first .mp4 in temp/).",
    )
    args = parser.parse_args()

    clips_file = config.TEMP_DIR / "clips.json"
    if not clips_file.is_file():
        raise FileNotFoundError(f"Clips file not found: {clips_file}")

    with clips_file.open("r", encoding="utf-8") as f:
        clips_data = json.load(f)

    clips = clips_data.get("clips", [])
    if not clips:
        raise ValueError(f"No clips found in {clips_file}")

    first_clip = clips[0]
    source_video = (
        Path(args.video_path) if args.video_path else _find_default_temp_video()
    )
    out_clip = config.OUTPUT_DIR / "test_clip_1.mp4"

    created_path = create_vertical_clip(
        video_path=source_video,
        start_time=float(first_clip["start_time"]),
        end_time=float(first_clip["end_time"]),
        output_path=out_clip,
    )
    print(f"Created vertical clip: {created_path}")
