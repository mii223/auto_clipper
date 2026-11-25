"""Audio transcription module using faster-whisper."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from faster_whisper import WhisperModel

try:
    import config
except ModuleNotFoundError:  # Allow direct execution via `python modules\transcriber.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config


def _resolve_device_and_compute_type(device_setting: str) -> tuple[str, str]:
    """Resolve runtime device ('cuda' or 'cpu') and optimal compute_type."""
    normalized = device_setting.strip().lower()
    if normalized == "auto":
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    else:
        device = normalized

    compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


def transcribe_audio(audio_path: Path) -> Path:
    """Transcribe audio_path with word timestamps and save to temp/transcript.json."""
    audio_file = Path(audio_path).expanduser().resolve()
    if not audio_file.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    output_path = (config.TEMP_DIR / "transcript.json").resolve()

    device, compute_type = _resolve_device_and_compute_type(config.DEVICE)
    model = WhisperModel(
        config.WHISPER_MODEL,
        device=device,
        compute_type=compute_type,
    )

    raw_segments, info = model.transcribe(
        str(audio_file),
        word_timestamps=True,
    )

    segments: list[dict[str, object]] = []
    for seg in raw_segments:
        words = [
            {
                "word": w.word.strip(),
                "start": round(float(w.start), 3),
                "end": round(float(w.end), 3),
            }
            for w in (seg.words or [])
            if w.word and w.word.strip()
        ]
        segments.append(
            {
                "start": round(float(seg.start), 3),
                "end": round(float(seg.end), 3),
                "text": seg.text.strip(),
                "words": words,
            }
        )

    transcript_data = {
        "language": info.language,
        "segments": segments,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(transcript_data, f, ensure_ascii=False, indent=2)

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Transcribe an audio file using faster-whisper."
    )
    parser.add_argument(
        "audio_path",
        nargs="?",
        default=str(config.TEMP_DIR / "audio.wav"),
        help="Path to input audio WAV file (defaults to temp/audio.wav).",
    )
    args = parser.parse_args()

    result_path = transcribe_audio(Path(args.audio_path))
    print(f"Transcript saved to: {result_path}")
