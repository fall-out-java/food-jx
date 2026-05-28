"""
Speech-to-text engine selector.

Supports multiple backends:
  - whisper  (default, local, no API cost)
  - aliyun   (阿里云 NLS, better dialect support, requires cloud setup)
"""

import os

from src.utils.ffmpeg import ensure_ffmpeg_on_path

LANG = "zh"
INITIAL_PROMPT = "以下是中文美食教学视频，包含食材和步骤介绍。"

# Model cache
_whisper_model = None
_whisper_current_name = None


def transcribe(
    audio_path,
    backend: str = "whisper",
    model_name: str | None = None,
    on_progress=None,
    **kwargs,
) -> dict:
    """Transcribe audio file using the selected backend.

    Args:
        audio_path: Path to audio file.
        backend: "whisper" (default) or "aliyun".
        model_name: Whisper model size (tiny/base/small/medium/large-v3).
                    Ignored for aliyun backend.
        on_progress: Optional callback for real-time updates.
        **kwargs: Backend-specific options forwarded to the backend.

    Returns:
        Dict with keys: text, segments, language
    """
    if backend == "aliyun":
        return _transcribe_aliyun(audio_path, **kwargs)
    else:
        return _transcribe_whisper(audio_path, model_name, on_progress)


def _transcribe_whisper(audio_path, model_name=None, on_progress=None) -> dict:
    """Whisper speech-to-text."""
    global _whisper_model, _whisper_current_name

    ensure_ffmpeg_on_path()

    if model_name is None:
        model_name = os.getenv("WHISPER_MODEL", "small")

    if _whisper_model is None or _whisper_current_name != model_name:
        import whisper
        _whisper_model = whisper.load_model(model_name)
        _whisper_current_name = model_name

    result = _whisper_model.transcribe(
        str(audio_path),
        language=LANG,
        verbose=False,
        initial_prompt=INITIAL_PROMPT,
    )
    return result


def _transcribe_aliyun(audio_path, **kwargs) -> dict:
    """Aliyun NLS speech-to-text."""
    from src.core.aliyun_asr import transcribe as aliyun_transcribe

    return aliyun_transcribe(
        audio_path,
        app_key=kwargs.get("app_key", ""),
        access_key_id=kwargs.get("access_key_id", ""),
        access_key_secret=kwargs.get("access_key_secret", ""),
        dialect=kwargs.get("dialect", ""),
    )
