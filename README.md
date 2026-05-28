# food-jx — 抖音美食视频食谱生成器

从抖音美食视频中自动提取文字 → 生成结构化食谱教程。

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 安装依赖
.venv\Scripts\pip install -r requirements.txt

# 3. 安装 Playwright 浏览器
.venv\Scripts\python -m playwright install chromium

# 4. 复制配置并填入你的 API Key
copy config.example.json config\config.json
# 然后用文本编辑器打开 config\config.json 填好各项凭证

# 5. 运行
.venv\Scripts\python main.py
```

> 也可双击 `setup.bat` 一键完成步骤 1~3。

## 配置详解

复制 `config.example.json` 为 `config\config.json` 后，逐项填写：

### LLM（通义千问）

| 字段 | 说明 |
|------|------|
| `api_key` | **必填**。DashScope API Key，[点此获取](https://help.aliyun.com/zh/dashscope/developer-reference/activate-dashscope-and-create-an-api-key) |
| `llm_model` | 模型名，默认 `qwen-plus`。可选：`qwen-max`、`qwen-turbo` 等 |
| `use_llm` | `true` = LLM 生成结构化食谱；`false` = 仅转录音频+原始文本 |

### 语音识别引擎

| 字段 | 说明 |
|------|------|
| `asr_engine` | `whisper`（本地，免费）或 `aliyun`（云端，需阿里云凭证） |
| `whisper_model` | whisper 模型大小：`tiny`/`base`/`small`/`medium`/`large`。越小越快但精度越低 |
| `transcription_mode` | `audio`=语音识别；`subtitle`=仅提取字幕；`auto`=字幕优先，无字幕回退语音 |

#### 选择阿里云 ASR 时需要填：

| 字段 | 说明 |
|------|------|
| `aliyun_asr_app_key` | 阿里云 NLS AppKey，[开通语音识别](https://nls.console.aliyun.com/) 后获取 |
| `aliyun_asr_access_key_id` | 阿里云 AccessKey ID |
| `aliyun_asr_access_key_secret` | 阿里云 AccessKey Secret |
| `aliyun_asr_dialect` | 方言参数，如 `sichuan`、`cantonese`，空值 = 普通话 |

> 阿里云 ASR 是付费服务，有免费额度。如果不需要，保留 `asr_engine: "whisper"` 即可，whisper 完全本地运行。

### 下载模式

| 字段 | 说明 |
|------|------|
| `download_mode` | `playwright`（模拟浏览器，更稳定）或 `yt-dlp`（直接下载） |

### 浏览器 Cookie（重要）

部分抖音视频需要登录后才能下载，需要提供 Cookie。

| 字段 | 说明 |
|------|------|
| `cookies_file` | 填入 Cookie 文件路径，如 `D:/cookies.txt`。留空则不使用 Cookie |

**获取 Cookie 的方法：**
1. 浏览器安装 [Get cookies.txt](https://chrome.google.com/webstore/detail/get-cookiestxt/bgaddhkoddajcdgocldbbfleckgcbcid) 扩展（或 EditThisCookie）
2. 登录抖音网页版后导出 Cookie
3. 将文件路径填入 `cookies_file`

> ⚠ Cookie 文件包含你的登录信息，请勿提交到 Git（已在 `.gitignore` 中排除 `cookies*.txt`）。

### 其他

| 字段 | 说明 |
|------|------|
| `keep_audio` | `true` 保留下载的音频（调试用），`false` 自动删除 |
| `output_dir` | 食谱输出目录，留空则自动创建 `output/` |
| `system_prompt` | 自定义 LLM 系统提示词（高级），留空使用内置模板 |
| `user_template` | 自定义 LLM 用户提示模板（高级），留空使用内置模板 |

## 使用方式

### GUI 模式

直接双击 `main.py` 或运行：

```bash
.venv\Scripts\python main.py
```

### CLI 模式

```bash
.venv\Scripts\python main.py --cli --llm
```

可用参数：

| 参数 | 作用 |
|------|------|
| `--cli` | 命令行模式 |
| `--file 路径` | 指定 URL 文件（默认 `urls.txt`） |
| `--llm` | 启用 LLM 生成教程 |
| `--whisper-model` | 指定 whisper 模型 |
| `--llm-model` | 指定 LLM 模型 |
| `--asr-engine` | 指定识别引擎 |
| `--playwright` | 使用 Playwright 下载 |
| `--keep-audio` | 保留临时音频 |

## 输入格式

在 `urls.txt` 中写入抖音视频链接，每行一个：

```
https://www.douyin.com/video/xxxxx
https://www.douyin.com/video/yyyyy
```
