"""FFmpeg path management — Whisper needs ffmpeg on PATH."""

import os
import subprocess
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMP_DIR = PROJECT_ROOT / "temp"


def get_ffmpeg() -> str:
    """Return path to ffmpeg executable (bundled via imageio_ffmpeg)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def ensure_ffmpeg_on_path():
    """Copy bundled ffmpeg.exe to TEMP_DIR and add to PATH for Whisper."""
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_dir = os.path.dirname(ffmpeg_exe)
        if ffmpeg_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        ffmpeg_copy = str(TEMP_DIR / "ffmpeg.exe")
        if not os.path.isfile(ffmpeg_copy):
            shutil.copy2(ffmpeg_exe, ffmpeg_copy)
        if str(TEMP_DIR) not in os.environ.get("PATH", ""):
            os.environ["PATH"] = str(TEMP_DIR) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


def has_audio_stream(video_path: Path) -> bool:
    """Check if a video file contains an audio stream."""
    ffmpeg = get_ffmpeg()
    try:
        r = subprocess.run(
            [ffmpeg, "-i", str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        for line in r.stderr.split("\n"):
            if line.strip().startswith("Stream") and "Audio:" in line:
                return True
        return False
    except Exception:
        return True
