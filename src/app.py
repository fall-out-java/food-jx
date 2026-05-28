"""Graphical user interface for food-jx (customtkinter)."""

import os
import sys
import subprocess
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.config import Config, PROJECT_ROOT
from src.core.llm_generator import DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_TEMPLATE
from src.worker import Worker

# Try optional cookie3 for auto-detect
try:
    import browser_cookie3
    HAS_BROWSER_COOKIE = True
except ImportError:
    HAS_BROWSER_COOKIE = False


class App(ctk.CTk):
    """food-jx main GUI window."""

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    def __init__(self):
        super().__init__()

        self.config = Config()
        self.worker: Worker | None = None

        self.title("food-jx - 抖音美食视频食谱生成器")
        self.geometry("960x720")
        self.minsize(820, 620)

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self._build_ui()
        self._config_to_ui()
        self._update_url_count()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ═══════════════════════════════════════════════════════════
    #  UI Builders
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── Tabs ──
        self.tab = ctk.CTkTabview(self)
        self.tab.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        self.t_urls = self.tab.add("视频链接")
        self.t_settings = self.tab.add("设置")
        self.t_prompts = self.tab.add("提示词")
        self.t_process = self.tab.add("处理")

        self._build_urls_tab()
        self._build_settings_tab()
        self._build_prompts_tab()
        self._build_process_tab()

        # ── Status bar ──
        self.status_bar = ctk.CTkFrame(self)
        self.status_bar.pack(fill="x", padx=10, pady=(5, 10))

        self.status_label = ctk.CTkLabel(self.status_bar, text="就绪", anchor="w")
        self.status_label.pack(side="left", padx=8)

        self.bottom_progress = ctk.CTkProgressBar(self.status_bar, width=200)
        self.bottom_progress.pack(side="right", padx=8)
        self.bottom_progress.set(0)

    def _build_urls_tab(self):
        ctk.CTkLabel(
            self.t_urls,
            text="抖音视频链接（每行一个，支持 # 开头的注释行）",
            anchor="w",
        ).pack(fill="x", padx=5, pady=(8, 0))

        self.urls_text = ctk.CTkTextbox(self.t_urls, font=ctk.CTkFont(family="Consolas", size=13))
        self.urls_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.urls_text.bind("<KeyRelease>", lambda e: self._update_url_count())

        # load default urls.txt content
        default_path = PROJECT_ROOT / "urls.txt"
        if default_path.exists():
            self.urls_text.insert("1.0", default_path.read_text(encoding="utf-8"))

        btn_frame = ctk.CTkFrame(self.t_urls)
        btn_frame.pack(fill="x", padx=5, pady=(0, 5))

        ctk.CTkButton(btn_frame, text="导入文件", width=100, command=self._import_urls).pack(
            side="left", padx=3
        )
        ctk.CTkButton(btn_frame, text="保存到文件", width=100, command=self._save_urls).pack(
            side="left", padx=3
        )
        ctk.CTkButton(btn_frame, text="清空", width=80, command=self._clear_urls).pack(
            side="left", padx=3
        )

        self.url_count_label = ctk.CTkLabel(btn_frame, text="共 0 条链接", anchor="e")
        self.url_count_label.pack(side="right", padx=8)

    def _build_settings_tab(self):
        scroll = ctk.CTkScrollableFrame(self.t_settings)
        scroll.pack(fill="both", expand=True, padx=5, pady=5)

        # ── API section ──
        sec1 = ctk.CTkFrame(scroll)
        sec1.pack(fill="x", padx=5, pady=(5, 0))
        ctk.CTkLabel(sec1, text="通义千问 API", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=8, pady=(6, 0)
        )

        f1 = ctk.CTkFrame(sec1)
        f1.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(f1, text="API Key", width=90, anchor="w").pack(side="left")
        self.api_key_entry = ctk.CTkEntry(f1, placeholder_text="sk-...", show="*")
        self.api_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        f2 = ctk.CTkFrame(sec1)
        f2.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(f2, text="LLM 模型", width=90, anchor="w").pack(side="left")
        self.llm_model_var = ctk.StringVar(value="qwen-plus")
        ctk.CTkOptionMenu(f2, variable=self.llm_model_var, values=[
            "qwen-plus", "qwen-max", "qwen-turbo",
        ]).pack(side="left")

        # ── ASR section ──
        sec2 = ctk.CTkFrame(scroll)
        sec2.pack(fill="x", padx=5, pady=(10, 0))
        ctk.CTkLabel(sec2, text="语音识别", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=8, pady=(6, 0)
        )

        f_asr = ctk.CTkFrame(sec2)
        f_asr.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(f_asr, text="识别引擎", width=90, anchor="w").pack(side="left")
        self.asr_engine_var = ctk.StringVar(value="whisper")
        ctk.CTkOptionMenu(f_asr, variable=self.asr_engine_var, values=[
            "whisper", "aliyun",
        ], command=self._toggle_asr_engine).pack(side="left")
        ctk.CTkLabel(
            f_asr, text="阿里云需额外配置 AccessKey",
            text_color="gray", anchor="w",
        ).pack(side="left", padx=8)

        # ── Whisper sub-settings ──
        self.asr_whisper_frame = ctk.CTkFrame(sec2)
        self.asr_whisper_frame.pack(fill="x", padx=0, pady=0)

        f3 = ctk.CTkFrame(self.asr_whisper_frame)
        f3.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(f3, text="Whisper 模型", width=90, anchor="w").pack(side="left")
        self.whisper_model_var = ctk.StringVar(value="small")
        ctk.CTkOptionMenu(f3, variable=self.whisper_model_var, values=[
            "tiny", "base", "small", "medium", "large-v3",
        ]).pack(side="left")
        ctk.CTkLabel(
            f3, text="small 推荐（速度与准确度均衡）",
            text_color="gray", anchor="w",
        ).pack(side="left", padx=8)

        # ── Aliyun ASR sub-settings ──
        self.asr_aliyun_frame = ctk.CTkFrame(sec2)
        # 不 pack 父框架，通过 _toggle_asr_engine 控制显隐

        fa1 = ctk.CTkFrame(self.asr_aliyun_frame)
        fa1.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(fa1, text="AppKey", width=90, anchor="w").pack(side="left")
        self.aliyun_app_key_entry = ctk.CTkEntry(fa1, placeholder_text="NLS 项目 AppKey")
        self.aliyun_app_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        fa2 = ctk.CTkFrame(self.asr_aliyun_frame)
        fa2.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(fa2, text="AccessKey ID", width=90, anchor="w").pack(side="left")
        self.aliyun_ak_id_entry = ctk.CTkEntry(fa2, placeholder_text="阿里云 RAM AccessKey ID")
        self.aliyun_ak_id_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        fa3 = ctk.CTkFrame(self.asr_aliyun_frame)
        fa3.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(fa3, text="AccessKey Secret", width=90, anchor="w").pack(side="left")
        self.aliyun_ak_secret_entry = ctk.CTkEntry(fa3, placeholder_text="阿里云 RAM AccessKey Secret", show="*")
        self.aliyun_ak_secret_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        fa4 = ctk.CTkFrame(self.asr_aliyun_frame)
        fa4.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(fa4, text="方言", width=90, anchor="w").pack(side="left")
        self.aliyun_dialect_var = ctk.StringVar(value="")
        ctk.CTkOptionMenu(fa4, variable=self.aliyun_dialect_var, values=[
            "", "sichuan", "cantonese",
        ]).pack(side="left")
        ctk.CTkLabel(
            fa4, text="空=普通话 sichuan=四川话 cantonese=粤语",
            text_color="gray", anchor="w",
        ).pack(side="left", padx=8)

        # ── Download mode ──
        f4 = ctk.CTkFrame(sec2)
        f4.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(f4, text="下载方式", width=90, anchor="w").pack(side="left")
        self.dl_mode_var = ctk.StringVar(value="playwright")
        ctk.CTkOptionMenu(f4, variable=self.dl_mode_var, values=[
            "playwright", "yt-dlp",
        ]).pack(side="left")
        ctk.CTkLabel(
            f4, text="Playwright 更稳定，yt-dlp 更轻量",
            text_color="gray", anchor="w",
        ).pack(side="left", padx=8)

        # ── Transcription mode ──
        f_sub = ctk.CTkFrame(sec2)
        f_sub.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(f_sub, text="转录来源", width=90, anchor="w").pack(side="left")
        self.transcription_mode_var = ctk.StringVar(value="audio")
        ctk.CTkOptionMenu(f_sub, variable=self.transcription_mode_var, values=[
            "audio", "auto", "subtitle",
        ]).pack(side="left")
        ctk.CTkLabel(
            f_sub, text="audio=语音识别  auto=字幕优先  subtitle=仅字幕",
            text_color="gray", anchor="w",
        ).pack(side="left", padx=8)

        # ── Options section ──
        sec3 = ctk.CTkFrame(scroll)
        sec3.pack(fill="x", padx=5, pady=(10, 0))
        ctk.CTkLabel(sec3, text="选项", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=8, pady=(6, 0)
        )

        self.use_llm_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(sec3, text="启用 LLM 生成详细教程（需要 API Key）",
                        variable=self.use_llm_var).pack(anchor="w", padx=8, pady=3)
        self.keep_audio_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(sec3, text="保留临时音频文件（调试用）",
                        variable=self.keep_audio_var).pack(anchor="w", padx=8, pady=3)

        # ── Paths section ──
        sec4 = ctk.CTkFrame(scroll)
        sec4.pack(fill="x", padx=5, pady=(10, 0))
        ctk.CTkLabel(sec4, text="目录与文件", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=8, pady=(6, 0)
        )

        f5 = ctk.CTkFrame(sec4)
        f5.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(f5, text="输出目录", width=90, anchor="w").pack(side="left")
        self.output_dir_entry = ctk.CTkEntry(f5)
        self.output_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(f5, text="浏览", width=60, command=self._browse_output_dir).pack(side="right")

        f6 = ctk.CTkFrame(sec4)
        f6.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(f6, text="Cookies", width=90, anchor="w").pack(side="left")
        self.cookies_entry = ctk.CTkEntry(f6)
        self.cookies_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(f6, text="浏览", width=60, command=self._browse_cookies).pack(side="right")

        # auto-detect button
        if HAS_BROWSER_COOKIE:
            ctk.CTkButton(
                scroll, text="自动检测 Firefox Cookie",
                command=self._detect_cookies,
            ).pack(anchor="w", padx=13, pady=4)

        # ── Save button ──
        ctk.CTkButton(scroll, text="保存设置", height=32,
                       command=self._save_config).pack(pady=(12, 8))

    def _build_prompts_tab(self):
        scroll = ctk.CTkScrollableFrame(self.t_prompts)
        scroll.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(
            scroll,
            text="System Prompt（系统提示词 — 控制 LLM 的角色和行为）",
            anchor="w",
        ).pack(fill="x", padx=5, pady=(5, 0))

        self.sys_prompt_text = ctk.CTkTextbox(scroll, height=220,
                                              font=ctk.CTkFont(family="Consolas", size=12))
        self.sys_prompt_text.pack(fill="x", padx=5, pady=5)

        ctk.CTkLabel(
            scroll,
            text="User Prompt Template（用户提示词模板 — 用 {text} 代表转录文字）",
            anchor="w",
        ).pack(fill="x", padx=5, pady=(10, 0))

        self.user_prompt_text = ctk.CTkTextbox(scroll, height=100,
                                                font=ctk.CTkFont(family="Consolas", size=12))
        self.user_prompt_text.pack(fill="x", padx=5, pady=5)

        btn_f = ctk.CTkFrame(scroll)
        btn_f.pack(fill="x", padx=5, pady=8)
        ctk.CTkButton(btn_f, text="保存提示词", command=self._save_prompts).pack(side="left", padx=3)
        ctk.CTkButton(btn_f, text="恢复默认", command=self._reset_prompts).pack(side="left", padx=3)

    def _build_process_tab(self):
        # ── Progress ──
        pf = ctk.CTkFrame(self.t_process)
        pf.pack(fill="x", padx=5, pady=(8, 0))

        self.progress_label = ctk.CTkLabel(pf, text="就绪", anchor="w")
        self.progress_label.pack(fill="x", padx=8, pady=(4, 0))

        self.process_progress = ctk.CTkProgressBar(pf)
        self.process_progress.pack(fill="x", padx=8, pady=6)
        self.process_progress.set(0)

        # ── Log ──
        ctk.CTkLabel(self.t_process, text="处理日志", anchor="w").pack(
            fill="x", padx=5, pady=(5, 0)
        )
        self.log_text = ctk.CTkTextbox(self.t_process, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_text.configure(state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

        # ── Controls ──
        cf = ctk.CTkFrame(self.t_process)
        cf.pack(fill="x", padx=5, pady=(0, 5))

        self.start_btn = ctk.CTkButton(cf, text="开始处理", command=self._start_processing)
        self.start_btn.pack(side="left", padx=3)

        self.stop_btn = ctk.CTkButton(cf, text="停止", state="disabled",
                                       command=self._stop_processing)
        self.stop_btn.pack(side="left", padx=3)

        ctk.CTkButton(cf, text="打开输出目录", command=self._open_output_dir).pack(
            side="right", padx=3
        )

    # ═══════════════════════════════════════════════════════════
    #  Config ↔ UI
    # ═══════════════════════════════════════════════════════════

    def _config_to_ui(self):
        c = self.config.data
        self.api_key_entry.insert(0, c.get("api_key", ""))
        self.llm_model_var.set(c.get("llm_model", "qwen-plus"))
        self.asr_engine_var.set(c.get("asr_engine", "whisper"))
        self.whisper_model_var.set(c.get("whisper_model", "small"))
        self.aliyun_app_key_entry.insert(0, c.get("aliyun_asr_app_key", ""))
        self.aliyun_ak_id_entry.insert(0, c.get("aliyun_asr_access_key_id", ""))
        self.aliyun_ak_secret_entry.insert(0, c.get("aliyun_asr_access_key_secret", ""))
        self.aliyun_dialect_var.set(c.get("aliyun_asr_dialect", ""))
        self.dl_mode_var.set(c.get("download_mode", "playwright"))
        self.transcription_mode_var.set(c.get("transcription_mode", "audio"))
        self.use_llm_var.set(c.get("use_llm", True))
        self.keep_audio_var.set(c.get("keep_audio", False))
        self.output_dir_entry.insert(0, c.get("output_dir", str(PROJECT_ROOT / "output")))
        self.cookies_entry.insert(0, c.get("cookies_file", ""))
        self._toggle_asr_engine(self.asr_engine_var.get())

        sp = c.get("system_prompt", "")
        self.sys_prompt_text.insert("1.0", sp or DEFAULT_SYSTEM_PROMPT)

        ut = c.get("user_template", "")
        self.user_prompt_text.insert("1.0", ut or DEFAULT_USER_TEMPLATE)

    def _ui_to_config(self):
        self.config.set("api_key", self.api_key_entry.get())
        self.config.set("llm_model", self.llm_model_var.get())
        self.config.set("asr_engine", self.asr_engine_var.get())
        self.config.set("whisper_model", self.whisper_model_var.get())
        self.config.set("aliyun_asr_app_key", self.aliyun_app_key_entry.get())
        self.config.set("aliyun_asr_access_key_id", self.aliyun_ak_id_entry.get())
        self.config.set("aliyun_asr_access_key_secret", self.aliyun_ak_secret_entry.get())
        self.config.set("aliyun_asr_dialect", self.aliyun_dialect_var.get())
        self.config.set("download_mode", self.dl_mode_var.get())
        self.config.set("transcription_mode", self.transcription_mode_var.get())
        self.config.set("use_llm", self.use_llm_var.get())
        self.config.set("keep_audio", self.keep_audio_var.get())
        self.config.set("output_dir", self.output_dir_entry.get())
        self.config.set("cookies_file", self.cookies_entry.get())
        self.config.save()

    # ═══════════════════════════════════════════════════════════
    #  ASR engine toggle
    # ═══════════════════════════════════════════════════════════

    def _toggle_asr_engine(self, engine: str):
        """Show/hide Whisper vs Aliyun sub-settings based on selected engine."""
        if engine == "aliyun":
            self.asr_whisper_frame.pack_forget()
            self.asr_aliyun_frame.pack(fill="x", padx=0, pady=0)
        else:
            self.asr_aliyun_frame.pack_forget()
            self.asr_whisper_frame.pack(fill="x", padx=0, pady=0)

    # ═══════════════════════════════════════════════════════════
    #  URL tab actions
    # ═══════════════════════════════════════════════════════════

    def _get_urls(self) -> list[str]:
        raw = self.urls_text.get("1.0", "end").strip()
        return [
            line.strip() for line in raw.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

    def _update_url_count(self):
        count = len(self._get_urls())
        self.url_count_label.configure(text=f"共 {count} 条链接")

    def _import_urls(self):
        path = filedialog.askopenfilename(
            title="导入链接文件",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
            self.urls_text.delete("1.0", "end")
            self.urls_text.insert("1.0", content)
            self._update_url_count()
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _save_urls(self):
        path = filedialog.asksaveasfilename(
            title="保存链接文件",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            content = self.urls_text.get("1.0", "end").strip()
            Path(path).write_text(content, encoding="utf-8")
            messagebox.showinfo("保存成功", f"已保存到 {path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _clear_urls(self):
        self.urls_text.delete("1.0", "end")
        self._update_url_count()

    # ═══════════════════════════════════════════════════════════
    #  Settings tab actions
    # ═══════════════════════════════════════════════════════════

    def _browse_output_dir(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_dir_entry.delete(0, "end")
            self.output_dir_entry.insert(0, path)

    def _browse_cookies(self):
        path = filedialog.askopenfilename(
            title="选择 Cookies 文件",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.cookies_entry.delete(0, "end")
            self.cookies_entry.insert(0, path)

    def _detect_cookies(self):
        """Auto-detect Firefox cookies for douyin.com."""
        try:
            ff_cookies = list(browser_cookie3.firefox(domain_name="douyin.com"))
            if not ff_cookies:
                ff_cookies = list(browser_cookie3.firefox())
                # filter for douyin
                ff_cookies = [c for c in ff_cookies if "douyin" in c.domain]
        except Exception as e:
            messagebox.showerror("检测失败", f"无法读取 Firefox cookie: {e}")
            return

        if not ff_cookies:
            messagebox.showwarning("未找到", "Firefox 中未找到抖音相关 cookie，请先登录抖音")
            return

        output = PROJECT_ROOT / "cookies_ff.txt"
        with open(output, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n\n")
            for c in ff_cookies:
                domain = c.domain if c.domain.startswith(".") else "." + c.domain
                f.write(
                    f"{domain}\tTRUE\t{c.path or '/'}\t"
                    f"{'TRUE' if c.secure else 'FALSE'}\t"
                    f"{int(c.expires) if c.expires else 0}\t"
                    f"{c.name}\t{c.value}\n"
                )

        self.cookies_entry.delete(0, "end")
        self.cookies_entry.insert(0, str(output))
        messagebox.showinfo("成功", f"已导出 {len(ff_cookies)} 个 cookie")

    def _save_config(self):
        self._ui_to_config()
        messagebox.showinfo("设置", "设置已保存")

    # ═══════════════════════════════════════════════════════════
    #  Prompts tab actions
    # ═══════════════════════════════════════════════════════════

    def _save_prompts(self):
        self.config.set("system_prompt", self.sys_prompt_text.get("1.0", "end").strip())
        self.config.set("user_template", self.user_prompt_text.get("1.0", "end").strip())
        self.config.save()
        messagebox.showinfo("提示词", "提示词已保存")

    def _reset_prompts(self):
        self.sys_prompt_text.delete("1.0", "end")
        self.sys_prompt_text.insert("1.0", DEFAULT_SYSTEM_PROMPT)
        self.user_prompt_text.delete("1.0", "end")
        self.user_prompt_text.insert("1.0", DEFAULT_USER_TEMPLATE)

    # ═══════════════════════════════════════════════════════════
    #  Process tab actions
    # ═══════════════════════════════════════════════════════════

    def _start_processing(self):
        urls = self._get_urls()
        if not urls:
            messagebox.showwarning("提示", "请先在「视频链接」标签页添加链接")
            self.tab.set("视频链接")
            return

        # Save config first
        self._ui_to_config()

        # Validate LLM settings if enabled
        if self.use_llm_var.get() and not self.config.api_key:
            ret = messagebox.askyesno(
                "未设置 API Key",
                "已启用 LLM 但未设置 API Key，将使用基础转录模式（不含 LLM 结构化）。是否继续？"
            )
            if not ret:
                return
            self.use_llm_var.set(False)
            self.config.set("use_llm", False)

        # UI state
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text="处理中…")
        self._clear_log()
        self.process_progress.set(0)
        self.tab.set("处理")

        asr_engine = self.config.get("asr_engine", "whisper")
        self._log(f"开始处理 {len(urls)} 条链接")
        self._log(f"下载模式: {self.config.get('download_mode')}")
        self._log(f"识别引擎: {asr_engine}")
        if asr_engine == "whisper":
            self._log(f"Whisper 模型: {self.config.get('whisper_model')}")
        else:
            dialect = self.config.get("aliyun_asr_dialect", "") or "普通话"
            self._log(f"阿里云 ASR（方言: {dialect}）")
        self._log(f"LLM 生成: {'开启' if self.config.get('use_llm') else '关闭'}")
        self._log("")

        self.worker = Worker(
            config=self.config,
            urls=urls,
            on_progress=self._on_worker_progress,
            on_log=self._on_worker_log,
            on_done=self._on_worker_done,
        )
        self.worker.start()

    def _stop_processing(self):
        if self.worker:
            self.worker.stop()
            self._log("收到停止信号，等待当前任务完成…")
        self.stop_btn.configure(state="disabled")

    def _open_output_dir(self):
        path = self.config.output_dir
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))
        except AttributeError:
            subprocess.run(["explorer", str(path)], check=False)

    # ── Worker callbacks (thread-safe via after) ──

    def _on_worker_progress(self, index, total, text):
        self.after(0, self._update_progress, index, total, text)

    def _on_worker_log(self, msg):
        self.after(0, self._append_log, msg)

    def _on_worker_done(self, ok, fail):
        self.after(0, self._processing_done, ok, fail)

    def _log(self, msg):
        """Append a message to the log textbox (main thread only)."""
        self._append_log(msg)

    def _update_progress(self, index, total, text):
        pct = index / total if total > 0 else 0
        self.process_progress.set(pct)
        self.bottom_progress.set(pct)
        self.progress_label.configure(text=f"[{index}/{total}] {text}")
        self.status_label.configure(text=f"[{index}/{total}] {text}")

    def _append_log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _processing_done(self, ok, fail):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        total = ok + fail

        if self.worker and self.worker._cancel.is_set():
            self.status_label.configure(text="已取消")
            self._log("处理已取消")
        else:
            self.status_label.configure(text=f"完成: 成功 {ok} / 失败 {fail}")
            self._log(f"\n{'─' * 40}")
            self._log(f"完成: 成功 {ok} / 失败 {fail} / 总计 {total}")

        self.process_progress.set(1 if ok > 0 and fail == 0 else 0)
        self.bottom_progress.set(0)
        self.worker = None

        # Open output dir on success
        if ok > 0:
            self._open_output_dir()

    # ═══════════════════════════════════════════════════════════
    #  Misc
    # ═══════════════════════════════════════════════════════════

    def _on_close(self):
        if self.worker and self.worker.is_running:
            if not messagebox.askyesno("确认退出", "正在处理中，确定要退出吗？"):
                return
            self.worker.stop()
        self.destroy()
