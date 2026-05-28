"""
Audio download engine: supports yt-dlp and Playwright + Firefox modes.

yt-dlp: lightweight, often blocked by Douyin.
Playwright: browser-based, bypasses JS anti-bot checks.
"""

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from src.utils.ffmpeg import get_ffmpeg, has_audio_stream

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMP_DIR = PROJECT_ROOT / "temp"
# Try to find yt-dlp on PATH, fall back to python -m yt_dlp
_YT_DLP_BIN = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
if _YT_DLP_BIN:
    YT_DLP_CMD = [_YT_DLP_BIN]
else:
    YT_DLP_CMD = [sys.executable, "-m", "yt_dlp"]


# ═══════════════════════════════════════════════════════════
#  Shared
# ═══════════════════════════════════════════════════════════

def get_video_title(url: str) -> str:
    """Extract video title via yt-dlp."""
    try:
        result = subprocess.run(
            [*YT_DLP_CMD, "--get-title", "--no-playlist", "--quiet", url],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"  获取标题失败: {e}")
    return "未命名视频"


# ═══════════════════════════════════════════════════════════
#  yt-dlp mode
# ═══════════════════════════════════════════════════════════

def download_audio_ytdlp(
    url: str,
    output_stem: str,
    cookies_from_browser: str | None = None,
    cookies: str | None = None,
) -> Path | None:
    """Download audio via yt-dlp, return path to mp3 or None."""
    output_path = TEMP_DIR / output_stem
    print("  下载音频 (yt-dlp) …")

    cmd = [
        *YT_DLP_CMD, "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "-o", f"{output_path}.%(ext)s", "--no-playlist", "--quiet",
        "--no-warnings",
        "--user-agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        url,
    ]
    if cookies_from_browser:
        cmd.insert(cmd.index(url), "--cookies-from-browser")
        cmd.insert(cmd.index(url), cookies_from_browser)
    if cookies:
        cmd.insert(cmd.index(url), "--cookies")
        cmd.insert(cmd.index(url), cookies)

    try:
        subprocess.run(cmd, check=True, timeout=180)
    except subprocess.TimeoutExpired:
        print("  下载超时（>180s）")
        return None
    except subprocess.CalledProcessError as e:
        print(f"  下载失败: {e.stderr.strip() if e.stderr else e}")
        return None

    for f in TEMP_DIR.glob(f"{output_stem}.*"):
        if f.suffix in (".mp3", ".m4a", ".wav", ".opus"):
            return f
    print("  找不到下载的音频文件")
    return None


# ═══════════════════════════════════════════════════════════
#  Playwright mode
# ═══════════════════════════════════════════════════════════

def _select_video_url(urls: list[str]) -> str | None:
    """Pick best video URL: prefer douyinvod.com, skip uuu_265 placeholders."""
    for u in urls:
        if "douyinvod.com" in u and "uuu_265" not in u:
            return u
    for u in urls:
        if "uuu_265" not in u:
            return u
    return urls[0] if urls else None


async def _load_cookies(context, cookies_file: str | None):
    """Load Netscape-format cookies into Playwright context."""
    if not cookies_file or not os.path.isfile(cookies_file):
        return
    with open(cookies_file, "r", encoding="utf-8") as f:
        all_cookies = []
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7 and parts[5] and parts[6]:
                all_cookies.append({
                    "name": parts[5], "value": parts[6],
                    "domain": parts[0], "path": parts[2],
                    "secure": parts[3].upper() == "TRUE",
                    "httpOnly": False, "sameSite": "Lax",
                })
    if not all_cookies:
        return
    success = 0
    for c in all_cookies:
        try:
            await context.add_cookies([c])
            success += 1
        except Exception:
            pass
    print(f"  ✓ 已加载 {success}/{len(all_cookies)} 个 cookie")


DownloadResult = tuple[Path, Path | None]  # (audio_path, video_path_or_none)


async def _try_url_download(context, video_url: str, output_stem: str, index: int,
                            keep_video: bool = False) -> DownloadResult | None:
    """Try downloading a single video URL and extracting its audio.

    Returns (audio_path, video_path_or_None) or None on failure.
    When *keep_video* is True the source mp4 is left on disk for subtitle extraction.
    """
    video_path = TEMP_DIR / f"{output_stem}_source.mp4"
    print(f"  尝试 #{index}…")

    resp = await context.request.get(video_url, headers={
        "Referer": "https://www.douyin.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }, timeout=180000)  # 3 分钟（大视频需要更长下载时间）
    if resp.status != 200:
        print(f"  HTTP {resp.status}，跳过")
        return None

    data = await resp.body()
    with open(video_path, "wb") as f:
        f.write(data)
    print(f"  ✓ 已下载 ({len(data)} bytes)")

    if not has_audio_stream(video_path):
        print(f"  无音频流，跳过")
        video_path.unlink(missing_ok=True)
        return None

    print(f"  提取音频 …")
    audio_path = TEMP_DIR / f"{output_stem}.mp3"
    ffmpeg = get_ffmpeg()
    r = subprocess.run(
        [ffmpeg, "-i", str(video_path), "-map", "0:a:0",
         "-c:a", "libmp3lame", "-b:a", "192k", "-y", str(audio_path)],
        capture_output=True, timeout=120,
    )
    if r.returncode != 0:
        print(f"  音频提取失败")
        video_path.unlink(missing_ok=True)
        return None

    if not keep_video:
        video_path.unlink(missing_ok=True)
        return (audio_path, None)
    return (audio_path, video_path)


async def _download_playwright_async(
    url: str,
    output_stem: str,
    cookies_file: str | None = None,
    keep_video: bool = False,
) -> DownloadResult | None:
    """Async implementation of Playwright download.

    Returns (audio_path, video_path_or_None) or None on failure.
    """
    from playwright.async_api import async_playwright

    # Step 1: gather video URLs via page visit
    video_urls = []
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        await _load_cookies(context, cookies_file)
        page = await context.new_page()

        async def handle_response(response):
            ct = response.headers.get("content-type", "")
            if "video/mp4" in ct:
                video_urls.append(response.url)
        page.on("response", handle_response)

        try:
            await page.goto("https://www.douyin.com/",
                            wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            print("  ▶ 打开视频页 …")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Poll for real video URL
            for i in range(30):
                await page.wait_for_timeout(1000)
                valid = [u for u in video_urls
                         if "douyinvod.com" in u and "uuu_265" not in u]
                if valid:
                    print(f"  ✓ 捕获到视频（等待 {i+1}s）")
                    break
                if i == 4:
                    await page.evaluate("window.scrollTo(0, 500)")
                if i == 8:
                    try:
                        await page.click("video", timeout=1000)
                    except Exception:
                        pass

            # Extract title
            page_data = await page.evaluate("""() => ({
                title: document.title,
            })""")
            title = page_data.get("title", "").strip()
            if title:
                (TEMP_DIR / f"title_{output_stem.replace('temp_', '')}.txt").write_text(
                    title, encoding="utf-8"
                )

        except Exception as e:
            print(f"  页面访问异常: {e}")
            return None
        finally:
            await browser.close()

    # Step 2: try each URL until one yields audio
    if not video_urls:
        print("  未捕获到任何视频 URL")
        return None

    candidates = sorted(set(video_urls), key=lambda u: (
        0 if "douyinvod.com" in u and "uuu_265" not in u else 1
    ))

    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        await _load_cookies(context, cookies_file)

        for idx, vu in enumerate(candidates, 1):
            result = await _try_url_download(context, vu, output_stem, idx, keep_video)
            if result:
                await browser.close()
                return result

        await browser.close()
        return None


def download_audio_playwright(
    url: str,
    output_stem: str,
    cookies_file: str | None = None,
) -> Path | None:
    """Download audio via Playwright (Firefox). Returns audio path or None."""
    print("  用 Playwright 提取音频 …")
    result = asyncio.run(_download_playwright_async(url, output_stem, cookies_file, keep_video=False))
    return result[0] if result else None


def download_media_playwright(
    url: str,
    output_stem: str,
    cookies_file: str | None = None,
) -> tuple[Path, Path | None] | None:
    """Download video + extract audio via Playwright.  Returns (audio_path, video_path_or_None) or None."""
    print("  用 Playwright 提取音视频 …")
    return asyncio.run(_download_playwright_async(url, output_stem, cookies_file, keep_video=True))
