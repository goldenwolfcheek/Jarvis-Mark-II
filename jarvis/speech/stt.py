"""
Jarvis Mark II — Speech-to-text engine.
Uses faster-whisper (CTranslate2-accelerated Whisper) for on-device,
multilingual STT with near-instant latency on CPU (tiny/base model).
"""

import io
import logging
import os
import threading
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Optional dependency ────────────────────────────────────────────────
_FASTER_WHISPER_AVAILABLE = False
try:
    from faster_whisper import WhisperModel

    _FASTER_WHISPER_AVAILABLE = True
except ImportError:
    pass

# ── Model size presets ─────────────────────────────────────────────────
_MODEL_PRESETS = {
    "tiny": "tiny",
    "base": "base",
    "small": "small",
    "medium": "medium",
    "large": "large-v3",
    "turbo": "turbo",
}


class STTEngine:
    """Speech-to-text engine wrapping faster-whisper.

    Features:
      - Runs entirely on-device (CPU, INT8 quantized)
      - Multilingual (87 languages via Whisper model)
      - Tiny/base models for ~1s latency on CPU
      - Configurable model size, language, compute type
    """

    def __init__(
        self,
        model_size: str = "tiny",
        device: str = "cpu",
        compute_type: str = "int8",
        language: Optional[str] = None,
        model_dir: Optional[Path] = None,
    ):
        self._model_size = _MODEL_PRESETS.get(model_size, model_size)
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._model_dir = model_dir
        self._lock = threading.Lock()
        self._model = None
        self._loaded = False

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """Check if faster-whisper is installed."""
        return _FASTER_WHISPER_AVAILABLE

    @property
    def model_size(self) -> str:
        return self._model_size

    @property
    def language(self) -> Optional[str]:
        return self._language

    # ── Model lifecycle ─────────────────────────────────────────────────

    def _ensure_model(self):
        """Lazy-load the Whisper model on first use."""
        if not self._loaded:
            with self._lock:
                if not self._loaded:
                    self._load_model()

    def _load_model(self):
        """Load the Whisper model via faster-whisper."""
        if not _FASTER_WHISPER_AVAILABLE:
            logger.warning(
                "faster-whisper is not installed. "
                "Install with: pip install faster-whisper"
            )
            return

        try:
            logger.info(
                "[STT] Loading faster-whisper model '%s' on %s (%s) ...",
                self._model_size, self._device, self._compute_type,
            )
            self._model = WhisperModel(
                model_size_or_path=self._model_size,
                device=self._device,
                compute_type=self._compute_type,
                download_root=str(self._model_dir) if self._model_dir else None,
                cpu_threads=os.cpu_count() or 4,
                num_workers=1,
            )
            self._loaded = True
            logger.info("[STT] Model '%s' loaded successfully.", self._model_size)
        except Exception as exc:
            logger.error("[STT] Failed to load model '%s': %s", self._model_size, exc)
            self._model = None

    # ── Transcription ──────────────────────────────────────────────────

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language: Optional[str] = None,
        beam_size: int = 5,
        best_of: int = 5,
        vad_filter: bool = True,
    ) -> dict:
        """Transcribe raw PCM audio bytes (16-bit mono, given sample_rate).

        Args:
            audio_bytes: Raw PCM 16-bit mono audio data.
            sample_rate: Sample rate of the input audio (Hz).
            language: Optional language code (e.g. 'en', 'ja', 'fr').
                      If None, faster-whisper auto-detects.
            beam_size: Beam search size (higher = more accurate but slower).
            best_of: Number of candidates for non-beam search.
            vad_filter: Apply voice activity detection to skip silence.

        Returns:
            dict with keys:
              - "text": The transcribed text (or "" on failure).
              - "language": Detected/used language code.
              - "segments": List of segment dicts (start, end, text).
              - "duration_s": Audio duration in seconds.
        """
        self._ensure_model()
        if not self._model:
            return {"text": "", "language": "", "segments": [], "duration_s": 0}

        lang = language or self._language

        try:
            import numpy as np

            # Convert bytes to numpy float32 array (normalized to [-1, 1])
            raw = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            duration_s = len(raw) / sample_rate

            segments, info = self._model.transcribe(
                raw,
                language=lang,
                beam_size=beam_size,
                best_of=best_of,
                vad_filter=vad_filter,
                condition_on_previous_text=True,
            )

            detected_lang = info.language if info else (lang or "en")
            detected_prob = info.language_probability if info else 1.0

            text_parts = []
            segment_list = []
            for seg in segments:
                text_parts.append(seg.text.strip())
                segment_list.append({
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip(),
                })

            full_text = " ".join(text_parts)

            logger.info(
                "[STT] Transcribed %.1fs audio (%s, p=%.2f): %r",
                duration_s, detected_lang, detected_prob, full_text[:60],
            )

            return {
                "text": full_text,
                "language": detected_lang,
                "language_probability": round(detected_prob, 3),
                "segments": segment_list,
                "duration_s": round(duration_s, 2),
            }

        except Exception as exc:
            logger.error("[STT] Transcription error: %s", exc)
            return {"text": "", "language": "", "segments": [], "duration_s": 0, "error": str(exc)}

    def transcribe_wav(
        self,
        wav_bytes: bytes,
        language: Optional[str] = None,
    ) -> dict:
        """Transcribe a WAV file (bytes).

        Handles WAV header parsing (supports different sample rates and
        channel counts — auto-mixes to 16-bit mono 16kHz).

        Args:
            wav_bytes: Complete WAV file as bytes (with RIFF header).
            language: Optional language code.

        Returns:
            Same dict shape as transcribe_bytes().
        """
        try:
            with io.BytesIO(wav_bytes) as buf:
                with wave.open(buf, "rb") as wf:
                    n_channels = wf.getnchannels()
                    sampwidth = wf.getsampwidth()
                    framerate = wf.getframerate()
                    frames = wf.readframes(wf.getnframes())

            import numpy as np

            # Convert to 16-bit mono
            raw = np.frombuffer(frames, dtype=np.int16)

            if n_channels > 1:
                # Mix down to mono (average channels)
                raw = raw.reshape(-1, n_channels).mean(axis=1).astype(np.int16)

            return self.transcribe_bytes(
                raw.tobytes(),
                sample_rate=framerate,
                language=language,
            )

        except Exception as exc:
            logger.error("[STT] WAV transcription error: %s", exc)
            return {"text": "", "language": "", "segments": [], "duration_s": 0, "error": str(exc)}

    def transcribe_webm(
        self,
        webm_bytes: bytes,
        language: Optional[str] = None,
    ) -> dict:
        """Transcribe WebM/Opus audio by converting via pydub (if available).

        Falls back to raw PCM if pydub is not installed.

        Args:
            webm_bytes: WebM audio as bytes.
            language: Optional language code.

        Returns:
            Same dict shape as transcribe_bytes().
        """
        try:
            from pydub import AudioSegment
            import io as _io

            seg = AudioSegment.from_file(_io.BytesIO(webm_bytes), format="webm")
            # Convert to 16kHz mono PCM WAV
            seg = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)
            raw = seg.raw_data
            return self.transcribe_bytes(raw, sample_rate=16000, language=language)

        except ImportError:
            logger.warning(
                "[STT] pydub not installed for WebM conversion. "
                "Install: pip install pydub"
            )
            # Fallback: try raw PCM
            return self.transcribe_bytes(webm_bytes, sample_rate=16000, language=language)

        except Exception as exc:
            logger.error("[STT] WebM transcription error: %s", exc)
            return {"text": "", "language": "", "segments": [], "duration_s": 0, "error": str(exc)}


# ── Singleton ─────────────────────────────────────────────────────────────
_stt_instance: Optional[STTEngine] = None
_stt_lock = threading.Lock()


def get_stt_engine(
    model_size: str = "tiny",
    device: str = "cpu",
    compute_type: str = "int8",
    language: Optional[str] = None,
) -> STTEngine:
    """Return the global STTEngine singleton.

    Args:
        model_size: Whisper model size (tiny, base, small, medium, large, turbo).
        device: 'cpu' or 'cuda'.
        compute_type: 'int8', 'int8_float16', 'float16', 'float32'.
        language: Default language code (auto-detect if None).

    Note:
        The singleton is created with the **first** set of parameters.
        Subsequent calls return the same instance regardless of new params.
    """
    global _stt_instance
    if _stt_instance is None:
        with _stt_lock:
            if _stt_instance is None:
                _stt_instance = STTEngine(
                    model_size=model_size,
                    device=device,
                    compute_type=compute_type,
                    language=language,
                )
    return _stt_instance
