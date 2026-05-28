"""
food-jx — 抖音美食视频食谱生成器
==================================
Entry point. By default launches the GUI.
Use --cli to run in command-line mode.
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="food-jx - 抖音美食视频食谱生成器")
    parser.add_argument("--cli", action="store_true", help="命令行模式（不启动 GUI）")
    parser.add_argument("--file", help="链接文件（CLI 模式，默认 urls.txt）")
    parser.add_argument("--llm", action="store_true", help="CLI 模式：启用 LLM 生成教程")
    parser.add_argument("--playwright", action="store_true", help="CLI 模式：使用 Playwright 下载")
    parser.add_argument("--keep-audio", action="store_true", help="CLI 模式：保留临时音频")
    parser.add_argument("--whisper-model", default="small", help="Whisper 模型（默认 small）")
    parser.add_argument("--llm-model", default="qwen-plus", help="LLM 模型（默认 qwen-plus）")
    parser.add_argument("--asr-engine", default="whisper", choices=["whisper", "aliyun"],
                        help="语音识别引擎（默认 whisper）")
    parser.add_argument("--transcription-mode", default="audio", choices=["audio", "subtitle", "auto"],
                        help="转录来源: audio=语音识别, subtitle=字幕, auto=字幕优先回退语音（默认 audio）")
    parser.add_argument("--dialect", default="", help="阿里云 ASR 方言参数（sichuan/cantonese）")
    parser.add_argument("--aliyun-app-key", default="", help="阿里云 NLS AppKey")
    parser.add_argument("--aliyun-ak-id", default="", help="阿里云 AccessKey ID")
    parser.add_argument("--aliyun-ak-secret", default="", help="阿里云 AccessKey Secret")
    args = parser.parse_args()

    if args.cli:
        _run_cli(args)
    else:
        _run_gui()


def _run_gui():
    """Launch the graphical interface."""
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        print("请安装依赖: pip install -r requirements.txt")
        print("缺少 customtkinter 包")
        sys.exit(1)

    from src.app import App
    app = App()
    app.mainloop()


def _run_cli(args):
    """Command-line mode — processes URLs file synchronously."""
    from src.config import Config, PROJECT_ROOT
    from src.core.downloader import get_video_title, download_audio_ytdlp, download_audio_playwright, download_media_playwright
    from src.core.transcriber import transcribe
    from src.core.llm_generator import generate_recipe, render_tutorial_md
    from src.core.subtitle_extractor import extract_subtitles
    from src.utils.helpers import read_urls, sanitize_filename, build_recipe_markdown
    from pathlib import Path

    config = Config()

    # Apply CLI overrides
    config.set("whisper_model", args.whisper_model)
    config.set("llm_model", args.llm_model)
    if args.asr_engine:
        config.set("asr_engine", args.asr_engine)
    if args.dialect:
        config.set("aliyun_asr_dialect", args.dialect)
    if args.aliyun_app_key:
        config.set("aliyun_asr_app_key", args.aliyun_app_key)
    if args.aliyun_ak_id:
        config.set("aliyun_asr_access_key_id", args.aliyun_ak_id)
    if args.aliyun_ak_secret:
        config.set("aliyun_asr_access_key_secret", args.aliyun_ak_secret)
    if args.llm:
        config.set("use_llm", True)
    if args.playwright:
        config.set("download_mode", "playwright")
    if args.keep_audio:
        config.set("keep_audio", True)
    if args.transcription_mode:
        config.set("transcription_mode", args.transcription_mode)

    # Read URLs
    urls_file = args.file or str(PROJECT_ROOT / "urls.txt")
    urls = read_urls(urls_file)
    if not urls:
        print(f"没有链接需要处理（{urls_file} 为空或不存在）")
        sys.exit(1)

    print(f"共 {len(urls)} 条待处理")
    print(f"下载模式: {config.get('download_mode')}")
    asr_engine = config.get("asr_engine", "whisper")
    print(f"识别引擎: {asr_engine}")
    if asr_engine == "aliyun":
        dialect = config.get("aliyun_asr_dialect", "") or "普通话"
        print(f"阿里云 ASR 方言: {dialect}")
    else:
        print(f"Whisper 模型: {config.get('whisper_model')}")
    transcription_mode = config.get("transcription_mode", "audio")
    print(f"转录来源: {'语音识别' if transcription_mode == 'audio' else '字幕优先' if transcription_mode == 'auto' else '仅字幕'}")
    print(f"LLM 生成: {'开启' if config.get('use_llm') else '关闭'}")

    ok = fail = 0

    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] {url}")
        print(f"  获取标题 …")
        title = get_video_title(url)
        print(f"  标题: {title[:70] if title else '(未知)'}")

        stem = f"temp_{i:03d}"
        cookies = config.get("cookies_file") or None
        transcription_mode = config.get("transcription_mode", "audio")

        # ── 先尝试字幕提取（yt-dlp --skip-download，无需下载视频）──
        text = None
        segments = []

        if transcription_mode in ("auto", "subtitle"):
            print(f"  尝试提取字幕…")
            sub_text = extract_subtitles(url, None, cookies)  # 无需视频文件
            if sub_text:
                print(f"  ✓ 字幕提取成功 ({len(sub_text)} 字符)")
                text = sub_text
            elif transcription_mode == "subtitle":
                print(f"  ⚠ 未找到字幕，跳过（subtitle-only 模式）")
                fail += 1
                continue
            else:
                print(f"  未找到字幕，回退到语音识别")

        # ── 字幕未成功 → 下载音视频 → ASR ──
        audio = None
        video = None

        if text is None:
            need_video = transcription_mode == "auto"  # auto 模式若后续需要 ffmpeg 提字幕可保留
            if config.get("download_mode") == "playwright":
                if need_video:
                    media = download_media_playwright(url, stem, cookies)
                    if media:
                        audio, video = media
                else:
                    audio = download_audio_playwright(url, stem, cookies)
            else:
                audio = download_audio_ytdlp(url, stem, cookies)

            if audio is None:
                print(f"  ✗ 下载失败")
                fail += 1
                continue

        try:
            # ASR fallback
            if text is None:
                asr_engine = config.get("asr_engine", "whisper")
                print(f"  转录中（引擎: {asr_engine}）…")
                transcribe_kwargs = dict(
                    audio_path=audio,
                    backend=asr_engine,
                )
                if asr_engine == "aliyun":
                    transcribe_kwargs["app_key"] = config.get("aliyun_asr_app_key", "")
                    transcribe_kwargs["access_key_id"] = config.get("aliyun_asr_access_key_id", "")
                    transcribe_kwargs["access_key_secret"] = config.get("aliyun_asr_access_key_secret", "")
                    transcribe_kwargs["dialect"] = config.get("aliyun_asr_dialect", "")
                else:
                    transcribe_kwargs["model_name"] = config.get("whisper_model")
                result = transcribe(**transcribe_kwargs)
                text = result.get("text", "").strip()
                segments = result.get("segments", [])

            if not text:
                print(f"  ⚠ 转录结果为空")
                fail += 1
                continue

            # Generate output
            use_llm = config.get("use_llm", True) and config.api_key
            if use_llm:
                print(f"  生成教程（LLM）…")
                recipe = generate_recipe(
                    text, api_key=config.api_key,
                    model=config.get("llm_model"),
                    system_prompt=config.get("system_prompt") or None,
                    user_template=config.get("user_template") or None,
                )
                md = render_tutorial_md(recipe, title or "未命名", url, i, raw_text=text)
                fname = sanitize_filename(recipe.get("dish_name") or title) or f"recipe_{i}"
                fname = f"{fname}.md"
            else:
                md = build_recipe_markdown(title or "未命名", url, text, segments, i)
                fname = sanitize_filename(title) or f"recipe_{i}"
                fname = f"{fname}.md"

            out_dir = config.output_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{i:03d}_{fname}"
            out_path.write_text(md, encoding="utf-8")
            print(f"  ✓ 已保存 → {out_path.name}")
            ok += 1

        finally:
            if not config.get("keep_audio", False):
                if audio:
                    try:
                        audio.unlink(missing_ok=True)
                    except PermissionError:
                        pass
                if video:
                    try:
                        video.unlink(missing_ok=True)
                    except PermissionError:
                        pass

    print(f"\n{'─' * 40}")
    print(f"完成: 成功 {ok} / 失败 {fail} / 总计 {ok + fail}")


if __name__ == "__main__":
    main()
