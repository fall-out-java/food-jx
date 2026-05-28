"""Background worker — runs the full pipeline in a separate thread."""

import threading
from pathlib import Path

from src.config import Config
from src.core.downloader import (
    get_video_title,
    download_audio_ytdlp,
    download_audio_playwright,
    download_media_playwright,
)
from src.core.transcriber import transcribe
from src.core.llm_generator import generate_recipe, render_tutorial_md
from src.core.subtitle_extractor import extract_subtitles
from src.utils.helpers import sanitize_filename, build_recipe_markdown


class Worker:
    """Pipeline worker that processes URLs one by one in a background thread.

    Signals back to the GUI via callbacks (invoked via after() for thread-safety).
    """

    def __init__(self, config: Config, urls: list[str],
                 on_progress=None, on_log=None, on_done=None):
        self.config = config
        self.urls = urls
        self.on_progress = on_progress   # callback(index, total, title)
        self.on_log = on_log             # callback(message)
        self.on_done = on_done           # callback(ok, fail)
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        """Launch worker thread."""
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal cancellation (non-blocking)."""
        self._cancel.set()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── internal ──

    def _run(self):
        total = len(self.urls)
        ok = fail = 0

        for i, url in enumerate(self.urls, 1):
            if self._cancel.is_set():
                self._log("处理已取消")
                break

            title = ""
            self._progress(i, total, "处理中…")

            try:
                # 1. Extract title
                mode = self.config.get("download_mode", "playwright")
                if mode == "playwright":
                    title = ""
                else:
                    title = get_video_title(url)
                self._log(f"[{i}/{total}] {title or url}")

                stem = f"temp_{i:03d}"
                cookies = self.config.get("cookies_file") or None
                transcription_mode = self.config.get("transcription_mode", "audio")

                # ── 2. 先尝试字幕提取（yt-dlp --skip-download，无需下载）──
                text = None
                segments = []
                audio = None
                video = None

                if transcription_mode in ("auto", "subtitle"):
                    self._log(f"  尝试提取字幕…")
                    sub_text = extract_subtitles(url, None, cookies)
                    if sub_text:
                        self._log(f"  ✓ 字幕提取成功 ({len(sub_text)} 字符)")
                        text = sub_text
                    elif transcription_mode == "subtitle":
                        self._log(f"  ⚠ 未找到字幕，跳过（subtitle-only 模式）")
                        fail += 1
                        continue
                    else:
                        self._log(f"  未找到字幕，回退到语音识别")

                # ── 3. 字幕未成功 → 下载音频 → ASR ──
                if text is None:
                    if mode == "playwright":
                        audio = download_audio_playwright(url, stem, cookies)
                    else:
                        audio = download_audio_ytdlp(url, stem, cookies)

                    if audio is None:
                        self._log(f"  ✗ 下载失败，跳过")
                        fail += 1
                        self._progress(i, total, "下载失败")
                        continue

                    # Playwright may have saved the title
                    if mode == "playwright" and not title:
                        title_file = Path(self.config.output_dir).parent / "temp" / f"title_{i:03d}.txt"
                        if title_file.exists():
                            title = title_file.read_text(encoding="utf-8").strip()
                            title_file.unlink(missing_ok=True)

                    asr_engine = self.config.get("asr_engine", "whisper")
                    self._log(f"  转录中（引擎: {asr_engine}）…")
                    transcribe_kwargs = dict(audio_path=audio, backend=asr_engine)
                    if asr_engine == "whisper":
                        transcribe_kwargs["model_name"] = self.config.get("whisper_model", "small")
                    else:
                        transcribe_kwargs["app_key"] = self.config.get("aliyun_asr_app_key", "")
                        transcribe_kwargs["access_key_id"] = self.config.get("aliyun_asr_access_key_id", "")
                        transcribe_kwargs["access_key_secret"] = self.config.get("aliyun_asr_access_key_secret", "")
                        transcribe_kwargs["dialect"] = self.config.get("aliyun_asr_dialect", "")

                    result = transcribe(**transcribe_kwargs)
                    text = result.get("text", "").strip()
                    segments = result.get("segments", [])

                # ── 4. 生成并保存（字幕 / ASR 共用）──
                if not text:
                    self._log(f"  ⚠ 转录结果为空，跳过")
                    fail += 1
                    continue

                if self.config.get("use_llm", True) and self.config.api_key:
                    self._log(f"  生成教程（LLM）…")
                    recipe = generate_recipe(
                        text,
                        api_key=self.config.api_key,
                        model=self.config.get("llm_model", "qwen-plus"),
                        system_prompt=self.config.get("system_prompt") or None,
                        user_template=self.config.get("user_template") or None,
                    )
                    md = render_tutorial_md(recipe, title or "未命名", url, i, raw_text=text)
                    fname = sanitize_filename(recipe.get("dish_name") or title) or f"recipe_{i}"
                else:
                    md = build_recipe_markdown(title or "未命名", url, text, segments, i)
                    fname = sanitize_filename(title) or f"recipe_{i}"

                out_dir = self.config.output_dir
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{i:03d}_{fname}.md"
                out_path.write_text(md, encoding="utf-8")
                self._log(f"  ✓ 已保存 → {out_path.name}")
                self._progress(i, total, f"✓ {title or out_path.name}")
                ok += 1

            except Exception as e:
                self._log(f"  ✗ 处理异常: {e}")
                fail += 1
                self._progress(i, total, f"✗ 处理失败")

            finally:
                if not self.config.get("keep_audio", False) and audio:
                    try:
                        audio.unlink(missing_ok=True)
                    except PermissionError:
                        pass

        self._on_done(ok, fail)
        return ok, fail

    def _progress(self, index, total, text):
        if self.on_progress:
            self.on_progress(index, total, text)

    def _log(self, msg):
        if self.on_log:
            self.on_log(msg)

    def _on_done(self, ok, fail):
        if self.on_done:
            self.on_done(ok, fail)
