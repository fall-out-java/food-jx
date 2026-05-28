"""
Aliyun speech recognition backend via DashScope Paraformer API.

使用通义千问 API Key 即可，无需额外开通 NLS 服务。
流程：上传音频到 OSS → DashScope 异步转写 → 轮询结果
"""

import json
import os
import time
from pathlib import Path

import dashscope
from dashscope.audio.asr import Transcription


def transcribe(
    audio_path: str | Path,
    app_key: str = "",
    access_key_id: str = "",
    access_key_secret: str = "",
    dialect: str = "",
    region: str = "cn-shanghai",
) -> dict:
    """Transcribe audio using DashScope Paraformer.

    Uses the user's existing DashScope API key (set in config or DASHSCOPE_API_KEY env).
    app_key / access_key_id / access_key_secret are ignored (kept for API compatibility).

    Returns:
        Dict with keys: text, segments[{start, end, text}], language
    """
    # 0. Ensure DashScope API key is set
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        # Fall back to reading config.json directly
        cfg_path = Path(__file__).resolve().parent.parent.parent / "config" / "config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            api_key = cfg.get("api_key", "")
    if not api_key:
        raise RuntimeError("请设置 DASHSCOPE_API_KEY 环境变量，或在设置中填写 API Key")
    dashscope.api_key = api_key

    # 1. Upload audio to OSS to get a public URL
    print("  上传音频到 OSS …")
    file_url = _upload_to_oss(audio_path, access_key_id, access_key_secret, region)
    print(f"  ✓ OSS URL: {file_url}")

    # 2. Submit transcription task
    print("  提交 DashScope 转录任务 …")
    task_response = Transcription.async_call(
        model="paraformer-v2",
        file_urls=[file_url],
        language_hints=["zh"],
        channel_id=[0],
    )
    task_id = task_response.output.task_id
    print(f"  ✓ 任务 ID: {task_id}")

    max_wait = 600
    interval = 2
    # 3. Poll for result
    print("  等待识别结果 …")
    waited = 0
    while waited < max_wait:
        status = task_response.output.task_status
        if status == "SUCCEEDED":
            break
        elif status == "FAILED":
            raise RuntimeError(f"转录失败: {task_response.output.message}")
        # PENDING / RUNNING — keep waiting
        time.sleep(interval)
        waited += interval
        if waited % 10 == 0:
            print(f"    ... 已等待 {waited}s")
        task_response = Transcription.fetch(task=task_id)
    else:
        raise TimeoutError(f"转录超时（>{max_wait}s）")

    # 4. Parse result — fetch transcription JSON from result URL
    results = task_response.output.results or []
    all_text = ""
    segments = []

    import requests as req
    for res in results:
        trans_url = res.get("transcription_url")
        if not trans_url:
            continue
        resp = req.get(trans_url, timeout=30)
        if resp.status_code != 200:
            print(f"  ⚠ 无法获取转写结果: HTTP {resp.status_code}")
            continue
        trans_data = resp.json()

        # transcripts[] — one per channel
        for t in trans_data.get("transcripts", []):
            all_text += t.get("text", "")
            for s in t.get("sentences", []):
                segments.append({
                    "start": s.get("begin_time", 0) / 1000.0,
                    "end": s.get("end_time", 0) / 1000.0,
                    "text": s.get("text", ""),
                })

    return {
        "text": all_text,
        "segments": segments,
        "language": "zh",
    }


def _upload_to_oss(
    local_path: str | Path,
    ak_id: str,
    ak_secret: str,
    region: str,
) -> str:
    """Upload audio to OSS and return a publicly accessible signed URL."""
    import oss2

    bucket_name = "food-jx-audio"
    endpoint = f"https://oss-{region}.aliyuncs.com"

    auth = oss2.Auth(ak_id, ak_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)

    try:
        bucket.create_bucket(oss2.BUCKET_ACL_PRIVATE)
    except oss2.exceptions.BucketAlreadyExists:
        pass
    except oss2.exceptions.ServerError as e:
        if e.status != 409:
            raise

    key = f"audio/{Path(local_path).name}"
    bucket.put_object_from_file(key, str(local_path))

    # Signed URL valid for 1 hour — plenty for DashScope to download it
    return bucket.sign_url("GET", key, 3600)
