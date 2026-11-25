"""Media downloader and audio extraction utilities for auto_clipper."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

try:
    import config
except ModuleNotFoundError:  # Allow direct execution via `python modules\downloader.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config


def _is_url(value: str) -> bool:
    """Return True if the given string looks like an HTTP(S) URL."""
    parsed = urlparse(value)
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def _download_youtube_mp4(url: str, output_dir: Path) -> Path:
    """Download the best MP4 video+audio stream from a URL into output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "restrictfilenames": True,
        "noplaylist": True,
        "overwrites": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        requested = info.get("requested_downloads")
        if requested:
            video_path = Path(requested[0]["filepath"])
        else:
            video_path = Path(ydl.prepare_filename(info))

    if not video_path.exists():
        mp4_fallback = video_path.with_suffix(".mp4")
        if mp4_fallback.exists():
            video_path = mp4_fallback

    if not video_path.is_file():
        raise FileNotFoundError(f"Downloaded video file not found: {video_path}")

    return video_path.resolve()


def _extract_audio_wav(video_path: Path, audio_path: Path) -> Path:
    """Extract mono 16kHz PCM WAV audio from video_path using ffmpeg."""
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_path),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffmpeg executable not found. Ensure FFmpeg is installed and added to PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"ffmpeg failed while extracting audio (exit code {exc.returncode}):\n{exc.stderr}"
        ) from exc

    return audio_path.resolve()


def prepare_media(source: str) -> tuple[Path, Path]:
    """Prepare video and 16kHz mono PCM WAV audio from a local MP4 path or YouTube URL."""
    cleaned_source = source.strip().strip('"')
    if not cleaned_source:
        raise ValueError("Media source cannot be empty.")

    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)

    if _is_url(cleaned_source):
        video_path = _download_youtube_mp4(cleaned_source, config.TEMP_DIR)
    else:
        video_path = Path(cleaned_source).expanduser().resolve()
        if not video_path.is_file():
            raise FileNotFoundError(f"Local video file not found: {video_path}")

    audio_path = _extract_audio_wav(video_path, config.TEMP_DIR / "audio.wav")
    return video_path, audio_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test media download and 16kHz mono WAV extraction."
    )
    parser.add_argument(
        "source",
        help="Path to a local MP4 file or a YouTube video URL.",
    )
    args = parser.parse_args()

    vid_path, wav_path = prepare_media(args.source)
    print(f"Video path: {vid_path}")
    print(f"Audio path: {wav_path}")
