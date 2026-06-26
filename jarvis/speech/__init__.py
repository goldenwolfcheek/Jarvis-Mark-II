"""
Jarvis Mark II — Speech package.
Text-to-speech synthesis using edge-tts and speech-to-text using faster-whisper.
"""

from .tts import TTSEngine, get_tts_engine
from .stt import STTEngine, get_stt_engine

__all__ = ["TTSEngine", "get_tts_engine", "STTEngine", "get_stt_engine"]
