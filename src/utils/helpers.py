"""Utility helpers"""

import re
from pathlib import Path


def sanitize_filename(name: str) -> str:
    """Remove illegal filename characters, trim to 80 chars."""
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80]


def format_timestamp(seconds: float) -> str:
    """seconds -> mm:ss"""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def read_urls(filepath: str | Path) -> list[str]:
    """Read URLs file, skip blanks and comments."""
    path = Path(filepath)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        urls = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]
    return urls


def build_recipe_markdown(title: str, url: str, full_text: str, segments: list[dict], index: int) -> str:
    """Assemble transcription into a basic recipe markdown (fallback when LLM is off/fails)."""
    lines = [f"# {title}", "", f"> 来源：{url}", ""]

    lines.append("## 分段时间轴")
    lines.append("")
    for seg in segments:
        start = format_timestamp(seg["start"])
        end = format_timestamp(seg["end"])
        text = seg["text"].strip()
        if text:
            lines.append(f"- **[{start} - {end}]** {text}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 完整转录")
    lines.append("")
    lines.append(full_text.strip())
    lines.append("")

    lines.append("---")
    lines.append(f"*由 food-jx 自动生成 | 索引 #{index}*")
    lines.append("")

    return "\n".join(lines)
