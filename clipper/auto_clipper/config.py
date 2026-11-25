"""Configuration defaults for the auto_clipper project."""

from pathlib import Path

# Base paths
BASE_DIR: Path = Path(__file__).resolve().parent
TEMP_DIR: Path = BASE_DIR / "temp"
OUTPUT_DIR: Path = BASE_DIR / "output"

# Whisper settings
WHISPER_MODEL: str = "small"
DEVICE: str = "auto"

# Video settings (9:16 vertical format)
TARGET_WIDTH: int = 1080
TARGET_HEIGHT: int = 1920

# Subtitle styling defaults
SUBTITLE_FONT_NAME: str = "Arial"
SUBTITLE_FONT_SIZE: int = 64
SUBTITLE_PRIMARY_COLOR: str = "#FFFFFF"
SUBTITLE_HIGHLIGHT_COLOR: str = "#FFD700"
SUBTITLE_OUTLINE_COLOR: str = "#000000"
SUBTITLE_OUTLINE_WIDTH: int = 4
