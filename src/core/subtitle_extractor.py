"""
Subtitle extraction from video sources — alternative to audio ASR.

Attempts multiple strategies in order:
  1. yt-dlp --write-auto-subs (works with many platforms)
  2. ffmpeg subtitle stream extraction from local mp4 (system ffmpeg required)
  3. Playwright page-scope subtitle data extraction

Returns plain text or None.  Caller decides fallback behaviour.
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from src.core.downloader import YT_DLP_CMD


def extract_subtitles(
    url: str,
    video_path: Path | None = None,
    cookies_file: str | None = None,
) -> str | None:
    """Try multiple subtitle strategies, return combined plain text or None."""
    # Strategy 1 — yt-dlp auto-subs (fast, platform-agnostic)
    text = _try_ytdlp_subs(url, cookies_file)
    if text:
        return text

    # Strategy 2 — mp4 embedded subtitle streams (system ffmpeg)
    if video_path and video_path.exists():
        text = _try_mp4_subs(video_path)
        if text:
            return text

    return None


# ── yt-dlp auto-subtitle strategy ──────────────────────────

def _try_ytdlp_subs(url: str, cookies_file: str | None = None) -> str | None:
    """Download auto-generated subtitles via yt-dlp."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_tpl = str(Path(tmpdir) / "subs")

        cmd = [
            *YT_DLP_CMD,
            "--write-auto-subs",
            "--sub-langs", "all",
            "--skip-download",
            "--sub-format", "srt/vtt/txt",
            "--convert-subs", "srt",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "--output", output_tpl,
            url,
        ]
        if cookies_file:
            cmd.extend(["--cookies", cookies_file])

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                return None
        except Exception:
            return None

        # Collect all subtitle files
        texts = []
        for f in sorted(Path(tmpdir).iterdir()):
            if f.suffix in (".srt", ".vtt", ".txt"):
                texts.append(_parse_subtitle_file(f))
        return texts[0] if texts else None


# ── mp4 embedded subtitle stream strategy ───────────────────

def _try_mp4_subs(video_path: Path) -> str | None:
    """Extract subtitle tracks from mp4 via system ffmpeg (supports decoders)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "subs.srt"

        # Try subtitle streams 0..3
        for stream_idx in range(4):
            try:
                r = subprocess.run(
                    [ffmpeg, "-i", str(video_path),
                     "-map", f"0:s:{stream_idx}",
                     "-y", str(out)],
                    capture_output=True, timeout=30,
                )
                if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                    text = _parse_subtitle_file(out)
                    if text:
                        return text
            except Exception:
                continue

    return None


# ── shared subtitle text parser ─────────────────────────────

def _parse_subtitle_file(path: Path) -> str:
    """Strip timing / index markup, return plain text lines."""
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = []
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        if "-->" in line:
            continue
        if line.isdigit():
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines)
