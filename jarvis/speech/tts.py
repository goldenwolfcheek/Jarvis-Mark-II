"""
Jarvis Mark II — Text-to-speech engine.
Uses edge-tts (free, offline-capable, Microsoft Edge TTS under the hood)
to synthesise speech from text.  Falls back gracefully if edge-tts is
not installed.
"""

import asyncio
import hashlib
import os
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from ..constants import AUDIO_DIR
from ..config import get_config

logger = logging.getLogger(__name__)

# Optional dependency
try:
    import edge_tts

    EDGE_AVAILABLE = True
except ImportError:
    EDGE_AVAILABLE = False

# Default voice map
_VOICE_MAP = {
    "en-US": "en-US-JennyNeural",
    "en-GB": "en-GB-SoniaNeural",
    "en-AU": "en-AU-NatashaNeural",
    "en-IN": "en-IN-NeerjaNeural",
    "ja-JP": "ja-JP-NanamiNeural",
    "fr-FR": "fr-FR-DeniseNeural",
    "de-DE": "de-DE-KatjaNeural",
    "es-ES": "es-ES-ElviraNeural",
    "zh-CN": "zh-CN-XiaoxiaoNeural",
    "ko-KR": "ko-KR-SunHiNeural",
}

_DEFAULT_VOICE = "en-US-JennyNeural"


class TTSEngine:
    """Text-to-speech engine wrapping edge-tts.

    Features:
      - Async speech synthesis (run in thread pool for sync callers)
      - Configurable voice, rate, volume, pitch
      - Content-hash-based caching (same text → instant hit from disk)
      - Volume normalisation (simple gain)
      - Enforceable maximum text length
    """

    def __init__(
        self,
        voice: Optional[str] = None,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        output_dir: Path = AUDIO_DIR,
        max_text_length: int = 2000,
    ):
        self._voice = voice or self._resolve_voice()
        self._cached_voice = self._voice
        self._rate = rate
        self._volume = volume
        self._pitch = pitch
        self._output_dir = output_dir
        self._max_text_length = max_text_length
        self._lock = threading.Lock()
        self._ensure_dir()

    # ── Initialisation ────────────────────────────────────────────────────

    def _ensure_dir(self):
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_voice(self) -> str:
        """Resolve voice from config or locale, falling back to default."""
        config = get_config()
        configured = config.get("tts_voice")
        if configured:
            return configured
        lang = config.get("tts_lang", "en-US")
        return _VOICE_MAP.get(lang, _DEFAULT_VOICE)

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """Check if edge-tts is installed and usable."""
        return EDGE_AVAILABLE

    @property
    def voice(self) -> str:
        return self._voice

    @voice.setter
    def voice(self, v: str):
        self._voice = v
        self._cached_voice = v

    def refresh_voice(self):
        """Re-read voice from config in case SettingsPanel changed it."""
        v = self._resolve_voice()
        if v != self._cached_voice:
            self._voice = v
            self._cached_voice = v

    # ── Synthesise ────────────────────────────────────────────────────────

    async def _synthesise_async(self, text: str, filename: str = "") -> Optional[Path]:
        """Internal async TTS call.

        Uses content-hash caching: the same cleaned text always maps to the
        same filename, so identical phrases skip edge-tts entirely.

        Args:
            text: The text to speak.
            filename: Optional output filename stem (without extension).

        Returns:
            Path to the generated .mp3 file, or None on failure.
        """
        if not EDGE_AVAILABLE:
            return None

        text = text.strip()
        if not text:
            return None

        # Truncate if needed
        if len(text) > self._max_text_length:
            text = text[: self._max_text_length] + "…"

        # Content-hash-based filename: same text → same file → instant cache hit
        # Use MD5 (fast, not security-critical) of the UTF-8 text
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:16]
        # Include voice in the hash key so different voices produce different files
        self.refresh_voice()
        hash_key = f"{text_hash}_{self._voice.replace('-', '_')}"
        output_path = self._output_dir / f"{filename or hash_key}.mp3"

        # Return cached file immediately if it exists on disk
        if output_path.exists():
            return output_path

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self._voice,
                rate=self._rate,
                volume=self._volume,
                pitch=self._pitch,
            )
            await communicate.save(str(output_path))
            return output_path
        except Exception as exc:
            logger.error("[Jarvis] TTS synthesis error: %s", exc)
            return None

    def speak(self, text: str, filename: str = "") -> Optional[Path]:
        """Synthesise text to speech synchronously.

        Args:
            text: Text to speak.
            filename: Optional custom filename stem.

        Returns:
            Path to the audio file, or None on failure.
        """
        if not EDGE_AVAILABLE:
            return None
        # Run the async method in a new event loop in a thread
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._synthesise_async(text, filename))
        finally:
            loop.close()

    async def speak_async(self, text: str, filename: str = "") -> Optional[Path]:
        """Synthesise text to speech asynchronously.

        This is the coroutine-based entry point used by the server.
        """
        return await self._synthesise_async(text, filename)

    # ── Utility ───────────────────────────────────────────────────────────

    def clear_cache(self, max_age_seconds: int = 3600):
        """Remove cached audio files older than *max_age_seconds*."""
        now = time.time()
        removed = 0
        for f in self._output_dir.iterdir():
            if f.suffix == ".mp3" and (now - f.stat().st_mtime) > max_age_seconds:
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
        if removed:
            logger.info("[Jarvis] TTS cache: cleaned %d old file(s)", removed)

    async def list_voices(self) -> list[dict]:
        """Return available edge-tts voices (if edge_tts is importable)."""
        if not EDGE_AVAILABLE:
            return []
        try:
            voices = await edge_tts.list_voices()
            return [
                {"name": v["ShortName"], "locale": v["Locale"], "gender": v["Gender"]}
                for v in voices
            ]
        except Exception:
            return []


# ── Singleton ─────────────────────────────────────────────────────────────
_tts_instance: Optional[TTSEngine] = None
_tts_lock = threading.Lock()


def get_tts_engine() -> TTSEngine:
    """Return the global TTSEngine singleton (pre-warmed on first call)."""
    global _tts_instance
    if _tts_instance is None:
        with _tts_lock:
            if _tts_instance is None:
                config = get_config()
                _tts_instance = TTSEngine(
                    voice=config.get("tts_voice"),
                    rate=config.get("tts_rate", "+0%"),
                    volume=config.get("tts_volume", "+0%"),
                    pitch=config.get("tts_pitch", "+0Hz"),
                )
    return _tts_instance


# Pre-warm the engine on import so the first TTS request doesn't pay
# singleton-construction overhead.
get_tts_engine()
