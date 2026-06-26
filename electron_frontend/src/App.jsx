import React, { memo, useState, useCallback, useEffect, useRef } from 'react';
import useWebSocket from './hooks/useWebSocket';
import TopBar from './components/TopBar';
import SphereScene from './components/SphereScene';
import ChatModule from './components/ChatModule';
import SettingsPanel from './components/SettingsPanel';
import LeftDrawer from './components/LeftDrawer';
import InfoBar from './components/InfoBar';
import { APP_VERSION, API_URL } from './utils/constants';
import { fetchConfig, fetchTools, fetchSkills, fetchSessions, createSession, fetchSessionHistory, fetchLastSession, fetchAllModels, fetchProviders, touchSession } from './utils/api';

const MemoSphere = memo(SphereScene);

// ── Clean TTS text: strip emojis, markdown, and format numbers for speech ──
function cleanTtsText(text) {
  if (!text) return '';
  let t = text;
  // Remove markdown bold/italic: **text** → text, *text* → text
  t = t.replace(/\*\*(.+?)\*\*/g, '$1');
  t = t.replace(/\*(.+?)\*/g, '$1');
  // Remove markdown headers: ### Title → Title
  t = t.replace(/^#+\s*/gm, '');
  // Remove markdown links: [text](url) → text
  t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  // Remove inline code: `code` → code
  t = t.replace(/`([^`]+)`/g, '$1');
  // Remove code blocks
  t = t.replace(/```[\s\S]*?```/g, '');
  // Remove horizontal rules
  t = t.replace(/^---+$/gm, '');
  // Remove blockquotes
  t = t.replace(/^>\s*/gm, '');
  // Remove list markers
  t = t.replace(/^[-*+]\s+/gm, '');
  t = t.replace(/^\d+\.\s+/gm, '');
  // Remove HTML tags
  t = t.replace(/<[^>]*>/g, '');
  // Remove emojis and common unicode symbols
  t = t.replace(/[\u{1F300}-\u{1F9FF}]/gu, '');   // Misc symbols, emoticons, etc.
  t = t.replace(/[\u{2600}-\u{26FF}]/gu, '');       // Misc symbols (sun, cloud, etc.)
  t = t.replace(/[\u{2700}-\u{27BF}]/gu, '');       // Dingbats
  t = t.replace(/[\u{FE00}-\u{FE0F}]/gu, '');       // Variation selectors
  t = t.replace(/[\u{200D}]/gu, '');                // Zero-width joiner
  t = t.replace(/[\u{231A}-\u{23FF}]/gu, '');       // Misc technical (watch, etc.)
  // Remove thousands separators from numbers so edge-tts doesn't pause at commas
  t = t.replace(/(\d),(\d{3})/g, '$1$2');
  // Collapse whitespace
  t = t.replace(/\s+/g, ' ').trim();
  return t;
}

// ── Chunk text into ~2-sentence blocks for smooth subtitle transitions ──
const WORDS_PER_CHUNK = 30; // ≈2 sentences

function chunkText(text) {
  if (!text) return [];
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 0) return [];
  const chunks = [];
  let i = 0;
  while (i < words.length) {
    const end = Math.min(i + WORDS_PER_CHUNK, words.length);
    chunks.push(words.slice(i, end).join(' '));
    i = end;
  }
  return chunks;
}

export default function App() {
  // ── State ──
  const [messages, setMessages] = useState([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [activeTools, setActiveTools] = useState([]);
  const [toolLog, setToolLog] = useState([]);
  const [infoProvider, setInfoProvider] = useState('—');
  const [infoModel, setInfoModel] = useState('—');
  const [toolCount, setToolCount] = useState(0);
  const [groupedModels, setGroupedModels] = useState({});
  const [providerEnabled, setProviderEnabled] = useState(() => {
    try { return JSON.parse(localStorage.getItem('jarvis_provider_toggles') || '{}'); }
    catch { return {}; }
  });
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [ttsEnabled, setTtsEnabled] = useState(() => {
    // Initialize from localStorage to avoid race on first message
    try { return localStorage.getItem('jarvis_tts_enabled') === 'true'; }
    catch { return false; }
  });
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [leftDrawerOpen, setLeftDrawerOpen] = useState(false);
  const [providerProfiles, setProviderProfiles] = useState({});
  const [reasoningEffort, setReasoningEffort] = useState('');
  const [sttAutoSend, setSttAutoSend] = useState(() => {
    try { return localStorage.getItem('jarvis_stt_auto_send') === 'true'; }
    catch { return false; }
  });
  const [responseStartTime, setResponseStartTime] = useState(null);
  const [showChatHistory, setShowChatHistory] = useState(() => {
    try { return localStorage.getItem('jarvis_show_chat_history') !== 'false'; }
    catch { return true; }
  });
  const [showSubtitles, setShowSubtitles] = useState(() => {
    try { return localStorage.getItem('jarvis_show_subtitles') === 'true'; }
    catch { return false; }
  });
  const [currentSubtitle, setCurrentSubtitle] = useState('');
  const [isTtsPlaying, setIsTtsPlaying] = useState(false);
  const [subtitleChunks, setSubtitleChunks] = useState([]);
  const [activeChunk, setActiveChunk] = useState(-1);
  const [prevChunk, setPrevChunk] = useState(-1);
  const [animTick, setAnimTick] = useState(0);
  const sessionLabelRef = useRef('Session');
  const responseStartRef = useRef(null);
  const audioCtxRef = useRef(null);
  const audioRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceNodeRef = useRef(null);
  const smoothLevelRef = useRef(0);
  const chunksRef = useRef([]);
  const activeChunkRef = useRef(-1);
  const hasAttemptedLastSessionRef = useRef(false);
  const sendMessageRef = useRef(null);
  const activeSessionIdRef = useRef(null);

  // ── Load sessions ──
  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const list = await fetchSessions();
      setSessions(Array.isArray(list) ? list : []);
    } catch { setSessions([]); }
    finally { setLoadingSessions(false); }
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  // ── Select session ──
  const handleSelectSession = useCallback(async (sessionId) => {
    setActiveSessionId(sessionId);
    activeSessionIdRef.current = sessionId;
    // Tell the server to switch to this session for message processing
    // (sendMessageRef is populated below after useWebSocket is called)
    if (sendMessageRef.current) {
      sendMessageRef.current({ type: 'set_session', session_id: sessionId });
    }
    // Touch the session so it becomes the 'last session' on next launch
    touchSession(sessionId).catch(() => {});
    try {
      const history = await fetchSessionHistory(sessionId);
      // Transform history messages: flag as non-streaming, and filter out
      // intermediate tool results (role: "tool") that are normally hidden
      // behind tool pills during live chat.
      setMessages(Array.isArray(history) ? history
        .filter((m) => m.role !== 'tool')
        // Also filter out assistant messages with empty content
        // (tool-only calls like web search produce empty assistant bubbles)
        .filter((m) => !(m.role === 'assistant' && (!m.content || !m.content.trim())))
        .map((m) => ({ ...m, _streaming: false }))
        : []);
    } catch {
      setMessages([{ role: 'assistant', content: '⚠️ Failed to load session history.', _streaming: false }]);
    }
  }, []);

  // ── New session ──
  const handleNewSession = useCallback(async () => {
    try {
      const s = await createSession();
      setSessions((prev) => [s, ...(Array.isArray(prev) ? prev : [])]);
      setActiveSessionId(s?.id || s?._id);
      setMessages([]);
    } catch {}
  }, []);

  // ── Model selection from InfoBar dropdown ──
  const handleModelSelect = useCallback(async (modelName, providerName) => {
    // Update local state
    setInfoModel(modelName);
    if (providerName) setInfoProvider(providerName);
    // Save to backend config
    try {
      await fetch(`${API_URL}/api/config/model`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: modelName }),
      });
      if (providerName) {
        await fetch(`${API_URL}/api/config/provider`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ value: providerName }),
        });
      }
    } catch (e) {
      console.warn('[App] Failed to save model selection:', e);
    }
  }, []);

  // ── Provider selection from InfoBar dropdown ──
  const handleProviderSelect = useCallback(async (providerName) => {
    setInfoProvider(providerName);
    // Auto-select first model from this provider if available
    const models = groupedModels[providerName];
    if (Array.isArray(models) && models.length > 0) {
      const firstModel = models[0].id || models[0].name || models[0];
      setInfoModel(firstModel);
      try {
        await fetch(`${API_URL}/api/config/model`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ value: firstModel }),
        });
      } catch (e) {
        console.warn('[App] Failed to save model:', e);
      }
    }
    // Save provider to backend
    try {
      await fetch(`${API_URL}/api/config/provider`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: providerName }),
      });
    } catch (e) {
      console.warn('[App] Failed to save provider:', e);
    }
  }, [groupedModels]);

  // ── Play TTS audio (uses Web Audio AnalyserNode for real, smooth levels) ──
  const playTts = useCallback(async (rawText) => {
    if (!rawText) return;
    // Clean text: strip emojis, markdown, formatting before sending to TTS
    // (edge-tts reads '***' and emojis aloud — sounds awful)
    const text = cleanTtsText(rawText);
    if (!text.trim()) return;

    // Split into chunks (~2 sentences each) for animated subtitle transitions
    const chunks = chunkText(text);
    const totalWords = chunks.join(' ').split(/\s+/).filter(Boolean).length;

    // Stop any previous TTS playback
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    // Set subtitle states so the overlay appears immediately
    // (no setCurrentSubtitle — TTS mode uses chunks only to avoid pre-audio flash)
    setSubtitleChunks(chunks);
    setActiveChunk(0);
    setPrevChunk(-1);
    setAnimTick(t => t + 1);
    chunksRef.current = chunks;
    activeChunkRef.current = 0;
    setIsTtsPlaying(true);

    try {
      const res = await fetch(`${API_URL}/api/tts/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        console.warn('[TTS] speak endpoint returned', res.status);
        setIsTtsPlaying(false);
        setSubtitleChunks([]);
        setActiveChunk(-1);
        setPrevChunk(-1);
        return;
      }
      const data = await res.json();
      if (data.status !== 'ok' || !data.path) {
        console.warn('[TTS] speak response missing path:', data);
        setIsTtsPlaying(false);
        setSubtitleChunks([]);
        setActiveChunk(-1);
        setPrevChunk(-1);
        return;
      }
      // Extract filename from path
      const parts = data.path.replace(/\\/g, '/').split('/');
      const filename = parts[parts.length - 1];
      const audioUrl = `${API_URL}/api/tts/audio/${filename}`;

      // Use direct server URL (fastest path — browser streams the audio
      // instead of downloading the whole file into a blob first).
      const audio = new Audio(audioUrl);
      audioRef.current = audio;

      // AudioContext was pre-warmed on mount — resume if still suspended
      let ctx = audioCtxRef.current;
      if (!ctx) {
        ctx = new (window.AudioContext || window.webkitAudioContext)();
        audioCtxRef.current = ctx;
      }
      if (ctx.state === 'suspended') {
        await ctx.resume();
      }

      // Wire up MediaElementSource when metadata is available (fires fast,
      // long before the audio finishes loading). This avoids the old approach
      // of either: (a) fetching the entire blob first, or (b) setTimeout hack
      // that broke the analyser.
      audio.addEventListener('loadedmetadata', async () => {
        try {
          // Disconnect previous source if any
          if (sourceNodeRef.current) {
            sourceNodeRef.current.disconnect();
            sourceNodeRef.current = null;
          }

          const source = ctx.createMediaElementSource(audio);
          sourceNodeRef.current = source;
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 128;
          analyserRef.current = analyser;
          source.connect(analyser);
          analyser.connect(ctx.destination);

          const dataArray = new Uint8Array(analyser.frequencyBinCount);

          // Smooth audio level tracking using RMS from AnalyserNode
          let animId;
          let lastTime = 0;
          const SMOOTHING = 0.35;
          const MIN_LEVEL = 0.04;

          // Chunk tracking: estimate current chunk from audio progress
          let trackingIntervalId;
          if (chunksRef.current.length > 1 && totalWords > 1) {
            let lastChunkIdx = 0; // already showing chunk 0 — no first-tick refresh
            trackingIntervalId = setInterval(() => {
              if (audio.paused || audio.ended || !audio.duration) return;
              // Use currentTime + 400ms lookahead to stay in sync with audio output
              const adjustedTime = Math.min(audio.currentTime + 0.4, audio.duration);
              const progress = adjustedTime / audio.duration;
              if (progress >= 1) return;
              const wordIdx = Math.min(Math.floor(progress * totalWords), totalWords - 1);
              const chunkIdx = Math.min(Math.floor(wordIdx / WORDS_PER_CHUNK), chunksRef.current.length - 1);
              if (chunkIdx !== lastChunkIdx) {
                lastChunkIdx = chunkIdx;
                const prev = activeChunkRef.current;
                activeChunkRef.current = chunkIdx;
                setPrevChunk(prev);
                setActiveChunk(chunkIdx);
                setAnimTick(t => t + 1);
              }
            }, 100);
          }

          const readLevel = (timestamp) => {
            if (audio.paused || audio.ended) {
              setAudioLevel(0);
              smoothLevelRef.current = 0;
              return;
            }
            if (timestamp - lastTime < 33) {
              animId = requestAnimationFrame(readLevel);
              return;
            }
            lastTime = timestamp;
            analyser.getByteTimeDomainData(dataArray);
            let sumSquares = 0;
            for (let i = 0; i < dataArray.length; i++) {
              const normalized = (dataArray[i] - 128) / 128;
              sumSquares += normalized * normalized;
            }
            const rms = Math.sqrt(sumSquares / dataArray.length);
            const clamped = Math.min(rms * 1.8, 1.0);
            smoothLevelRef.current += (clamped - smoothLevelRef.current) * SMOOTHING;
            setAudioLevel(smoothLevelRef.current < MIN_LEVEL ? 0 : smoothLevelRef.current);
            animId = requestAnimationFrame(readLevel);
          };

          audio.onplay = () => {
            smoothLevelRef.current = 0;
            animId = requestAnimationFrame(readLevel);
          };
          audio.onended = () => {
            clearInterval(trackingIntervalId);
            cancelAnimationFrame(animId);
            setAudioLevel(0);
            smoothLevelRef.current = 0;
            audioRef.current = null;
            setIsTtsPlaying(false);
            setSubtitleChunks([]);
            setActiveChunk(-1);
            setPrevChunk(-1);
            setCurrentSubtitle('');
          };
          audio.onerror = () => {
            clearInterval(trackingIntervalId);
            cancelAnimationFrame(animId);
            setAudioLevel(0);
            smoothLevelRef.current = 0;
            audioRef.current = null;
            setIsTtsPlaying(false);
            setSubtitleChunks([]);
            setActiveChunk(-1);
            setPrevChunk(-1);
            setCurrentSubtitle('');
          };

          await audio.play();
        } catch (e) {
          // Analyser setup failed — play natively so audio still works
          console.warn('[TTS] Analyser wiring failed, playing natively:', e);
          audio.play().catch(() => {});
        }
      });
    } catch (err) {
      console.warn('[TTS] Playback failed:', err);
      setAudioLevel(0);
      setIsTtsPlaying(false);
      setSubtitleChunks([]);
      setActiveChunk(-1);
      setPrevChunk(-1);
    }
  }, []);

  // ── WebSocket message handler ──
  const handleWsMessage = useCallback((data) => {
    switch (data.type) {

      // ── Streaming delta from LLM ────────────────────────────────────
      case 'delta':
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === 'assistant' && last._streaming) {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...last,
              content: last.content + (data.content || ''),
              _streaming: data.finish_reason !== 'stop',
            };
            setIsStreaming(data.finish_reason !== 'stop');
            return updated;
          }
          // Start new streaming message
          setIsStreaming(true);
          return [...prev, {
            role: 'assistant',
            content: data.content || '',
            _streaming: data.finish_reason !== 'stop',
          }];
        });
        break;

      // ── Turn complete ───────────────────────────────────────────────
      case 'turn_end': {
        const turnContent = data.content || '';
        setActiveTools([]);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          let content = data.content || (last && last.content) || '';
          if (last && last.role === 'assistant' && last._streaming) {
            const updated = [...prev];
            const duration = responseStartRef.current ? Date.now() - responseStartRef.current : null;
            responseStartRef.current = null;
            setResponseStartTime(null);
            updated[updated.length - 1] = {
              ...last,
              content: data.content || last.content,
              _streaming: false,
              _duration: duration,
            };
            setIsStreaming(false);
            return updated;
          }
          setIsStreaming(false);
          const duration = responseStartRef.current ? Date.now() - responseStartRef.current : null;
          responseStartRef.current = null;
          setResponseStartTime(null);
          return [...prev, {
            role: 'assistant',
            content: data.content || '',
            _streaming: false,
            _duration: duration,
          }];
        });
        // Trigger TTS outside state updater (side effect in pure function is bad)
        if (ttsEnabled && turnContent) {
          console.log('[TTS] Triggered, text length:', turnContent.length);
          playTts(turnContent);
        } else {
          if (!ttsEnabled) console.log('[TTS] Skipped — disabled');
          else if (!turnContent) console.log('[TTS] Skipped — empty content');
        }
        break;
      }

      // ── Processing complete ─────────────────────────────────────────
      case 'done':
        setIsStreaming(false);
        setActiveTools([]);
        setResponseStartTime(null);
        break;

      // ── Tool call / result ──────────────────────────────────────────
      case 'tool_call':
        console.log('[Tool]', data.name, data.arguments);
        setActiveTools((prev) => [...prev, { name: data.name, time: Date.now(), status: 'running' }]);
        setToolLog((prev) => [...prev.slice(-49), { type: 'call', name: data.name, args: data.arguments, time: Date.now() }]);
        break;
      case 'tool_result':
        console.log('[Tool Result]', data.name, String(data.result).slice(0, 100));
        setToolLog((prev) => [...prev.slice(-49), { type: 'result', name: data.name, result: String(data.result).slice(0, 200), time: Date.now() }]);
        // Remove completed tool from active display so only running tools show
        // Use a short timeout so the result animation has time to play
        setActiveTools((prev) => prev.filter((t) => t.name !== data.name));
        break;

      // ── Initial connection ──────────────────────────────────────────
      case 'connected':
        console.log(`[App] Connected: session ${data.session_id}`);
        // Clear any stale tools from a previous session
        setActiveTools([]);
        // Clear subtitle — don't show old history on relaunch
        setCurrentSubtitle('');
        // Clear TTS state on reconnect
        setIsTtsPlaying(false);
        setSubtitleChunks([]);
        setActiveChunk(-1);
        setPrevChunk(-1);
        fetchConfig().then((cfg) => {
          // Config stores provider/model at root keys, not active_* prefixed.
          if (cfg.provider && cfg.model) {
            setInfoProvider(cfg.provider);
            setInfoModel(cfg.model);
          }
          // Load TTS config on startup — remember last enabled state and voice
          if (cfg.hasOwnProperty('tts_enabled')) {
            setTtsEnabled(Boolean(cfg.tts_enabled));
          }
          // Load last TTS voice if configured
          if (cfg.tts_voice) {
            // Voice is loaded from backend config, no local state needed
            console.log('[TTS] Voice loaded from config:', cfg.tts_voice);
          }
          // Load STT auto-send setting
          if (cfg.hasOwnProperty('stt_auto_send')) {
            setSttAutoSend(Boolean(cfg.stt_auto_send));
            try { localStorage.setItem('jarvis_stt_auto_send', cfg.stt_auto_send ? 'true' : 'false'); }
            catch {}
          }
        }).catch(() => {});
        // Re-send session selection on reconnect — server's session_id resets
        // to a random UUID on each new WebSocket connection
        if (activeSessionIdRef.current && sendMessageRef.current) {
          sendMessageRef.current({ type: 'set_session', session_id: activeSessionIdRef.current });
          console.log('[App] Re-sent session selection after reconnect:', activeSessionIdRef.current);
        }
        break;

      // ── Server-side error ──────────────────────────────────────────
      case 'error':
        console.warn('[App] Server error:', data.message || data.error);
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `⚠️ ${data.message || data.error}`, _streaming: false },
        ]);
        setIsStreaming(false);
        break;

      // ── Legacy / unknown types ─────────────────────────────────────
      default:
        console.log('[App] Unhandled event type:', data.type);
    }
  }, [playTts, ttsEnabled]);

  // ── WebSocket hook ──
  const { status: wsStatus, sendMessage } = useWebSocket(handleWsMessage);
  sendMessageRef.current = sendMessage;

  // Reload sessions when WebSocket connects (in case new sessions were created server-side)
  useEffect(() => {
    if (wsStatus === 'connected') {
      loadSessions();
    }
  }, [wsStatus, loadSessions]);

  // ── Track current subtitle from latest assistant message ──
  useEffect(() => {
    if (!showSubtitles) {
      setCurrentSubtitle('');
      setSubtitleChunks([]);
      setActiveChunk(-1);
      setPrevChunk(-1);
      setIsTtsPlaying(false);
      return;
    }

    // When TTS is enabled, subtitle lifecycle is managed by playTts
    // (shows on TTS start, slides through sentence blocks, fades 3s after TTS ends)
    if (ttsEnabled) return;

    // Fallback for non-TTS mode: sync subtitles with streaming
    if (isStreaming) {
      const last = messages[messages.length - 1];
      if (last && last.role === 'assistant') {
        setCurrentSubtitle(last.content || '');
      }
    } else if (currentSubtitle) {
      // When streaming stops, fade out after a delay
      const timer = setTimeout(() => setCurrentSubtitle(''), 3000);
      return () => clearTimeout(timer);
    }
  }, [messages, showSubtitles, isStreaming, ttsEnabled]);

  // ── Send chat message ──
  const handleSendMessage = useCallback((text, fileIds = []) => {
    const now = Date.now();
    setResponseStartTime(now);
    responseStartRef.current = now;
    // Add user message to UI immediately
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text, _streaming: false, _file_ids: fileIds },
    ]);
    // Clear subtitle when user sends a new message
    setCurrentSubtitle('');
    // Stop any current TTS playback
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setIsTtsPlaying(false);
    setSubtitleChunks([]);
    setActiveChunk(-1);
    setPrevChunk(-1);

    const payload = {
      type: 'message',
      content: text,
      session_id: activeSessionId,
    };
    if (reasoningEffort) {
      payload.reasoning_effort = reasoningEffort;
    }
    if (fileIds && fileIds.length > 0) {
      payload.file_ids = fileIds;
    }

    const sent = sendMessage(payload);

    if (!sent) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '⚠️ Not connected to server. Check backend.', _streaming: false },
      ]);
    }
  }, [sendMessage, activeSessionId, reasoningEffort]);

  // ── Stop current response ──
  const handleStop = useCallback(() => {
    sendMessage({ type: 'stop' });
    setIsStreaming(false);
    setActiveTools([]);
  }, [sendMessage]);

  // ── Load all available models (grouped by provider) ──
  const loadAllModels = useCallback(async () => {
    try {
      const models = await fetchAllModels();
      if (models && typeof models === 'object') {
        setGroupedModels(models);
      }
    } catch {}
  }, []);

  // ── Refresh provider profiles from server ──
  const refreshProviderProfiles = useCallback(async () => {
    try {
      const data = await fetchProviders();
      const rawProfiles = data.profiles || data.providers || [];
      const pmap = {};
      for (const p of rawProfiles) {
        if (p.name) pmap[p.name] = p;
      }
      setProviderProfiles(pmap);
    } catch {}
  }, []);

  // ── Called when SettingsPanel adds a provider key — refresh models and toggles ──
  const handleKeyAdded = useCallback(async () => {
    await loadAllModels();
    // Sync provider toggles from localStorage (SettingsPanel stores them there when adding a key)
    try {
      const toggles = JSON.parse(localStorage.getItem('jarvis_provider_toggles') || '{}');
      setProviderEnabled(toggles);
    } catch {}
    // Refresh provider profiles so InfoBar knows about the new provider's has_api_key status
    await refreshProviderProfiles();
  }, [loadAllModels, refreshProviderProfiles]);

  // ── Settings change handler ──
  const handleSettingsChange = useCallback((updates) => {
    if (updates.active_provider || updates.active_model) {
      const prov = updates.active_provider || '';
      const mod = updates.active_model || '';
      setInfoProvider(prov);
      setInfoModel(mod);
    }
    if (updates.hasOwnProperty('tts_enabled')) {
      setTtsEnabled(updates.tts_enabled);
      // Persist to localStorage for instant availability on next launch
      try { localStorage.setItem('jarvis_tts_enabled', updates.tts_enabled ? 'true' : 'false'); }
      catch {}
      // If disabling, stop any playing audio
      if (!updates.tts_enabled && audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
        setAudioLevel(0);
      }
    }
    if (updates.hasOwnProperty('stt_auto_send')) {
      setSttAutoSend(updates.stt_auto_send);
      try { localStorage.setItem('jarvis_stt_auto_send', updates.stt_auto_send ? 'true' : 'false'); }
      catch {}
    }
    if (updates.hasOwnProperty('show_chat_history')) {
      setShowChatHistory(updates.show_chat_history);
      try { localStorage.setItem('jarvis_show_chat_history', updates.show_chat_history ? 'true' : 'false'); }
      catch {}
    }
    if (updates.hasOwnProperty('show_subtitles')) {
      setShowSubtitles(updates.show_subtitles);
      try { localStorage.setItem('jarvis_show_subtitles', updates.show_subtitles ? 'true' : 'false'); }
      catch {}
      if (!updates.show_subtitles) {
        setCurrentSubtitle('');
        setSubtitleChunks([]);
        setActiveChunk(-1);
        setPrevChunk(-1);
        setIsTtsPlaying(false);
      }
    }
    if (updates.reset) {
      loadAllModels();
    }
    // Always refresh model list after settings save (keys may have changed)
    loadAllModels();
    // Refresh provider profiles so InfoBar has up-to-date has_api_key info
    refreshProviderProfiles();
    // Sync provider toggles from localStorage
    try {
      const toggles = JSON.parse(localStorage.getItem('jarvis_provider_toggles') || '{}');
      setProviderEnabled(toggles);
    } catch {}
  }, [loadAllModels, refreshProviderProfiles]);

  // ── Called when SettingsPanel closes — refresh data so InfoBar is up to date ──
  const handleSettingsClose = useCallback(() => {
    setSettingsOpen(false);
    // Refresh models and profiles after settings close to catch any async
    // key-save operations that may not have propagated yet
    loadAllModels();
    refreshProviderProfiles();
  }, [loadAllModels, refreshProviderProfiles]);

  useEffect(() => {
    if (wsStatus === 'connected') {
      loadAllModels();
      // Refresh combined tool + skill count on connect
      Promise.all([
        fetchTools(),
        fetchSkills(),
      ]).then(([toolsList, skillsList]) => {
        const tCount = Array.isArray(toolsList) ? toolsList.length : 0;
        const sCount = Array.isArray(skillsList) ? skillsList.length : 0;
        setToolCount(tCount + sCount);
      }).catch(() => {});
      // Load provider profiles for InfoBar filtering
      fetchProviders().then((data) => {
        const rawProfiles = data.profiles || data.providers || [];
        const pmap = {};
        for (const p of rawProfiles) {
          if (p.name) pmap[p.name] = p;
        }
        setProviderProfiles(pmap);
      }).catch(() => {});
    }
  }, [wsStatus, loadAllModels]);

  // ── Load last session on startup (if config `load_last_session` is true) ──
  // Only runs once — the ref prevents re-loading on WebSocket reconnect
  useEffect(() => {
    if (wsStatus !== 'connected') return;
    if (hasAttemptedLastSessionRef.current) return;
    hasAttemptedLastSessionRef.current = true;

    fetchConfig().then((cfg) => {
      if (cfg.load_last_session) {
        fetchLastSession().then((lastSession) => {
          if (lastSession && lastSession.id) {
            handleSelectSession(lastSession.id);
            // Keep session list in sync
            setSessions((prev) => {
              if (prev.some((s) => s.id === lastSession.id)) return prev;
              return [lastSession, ...(Array.isArray(prev) ? prev : [])];
            });
          }
        }).catch(() => {});
      }
    }).catch(() => {});
  }, [wsStatus, handleSelectSession]);

  // ── Pre-warm AudioContext on mount so TTS doesn't block on ctx.resume() ──
  useEffect(() => {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    audioCtxRef.current = ctx;
    if (ctx.state === 'suspended') {
      ctx.resume();
    }
    return () => ctx.close();
  }, []);

  // ── Sync Electron-side settings (tray, dev console) to main process on mount ──
  useEffect(() => {
    if (!window.electronAPI) return;
    const devConsole = localStorage.getItem('jarvis_dev_console') !== 'false';
    window.electronAPI.setDevConsole(devConsole);
    const minimizeToTray = localStorage.getItem('jarvis_minimize_to_tray') === 'true';
    window.electronAPI.setMinimizeToTray(minimizeToTray);
  }, []);

  // ── Render ──
  return (
    <>
      {/* 3D Background */}
      <MemoSphere audioLevel={audioLevel} />

      {/* Subtitles (below sphere) — smooth sentence-block animation during TTS */}
      {showSubtitles && isTtsPlaying && subtitleChunks.length > 0 && activeChunk >= 0 && (
        <div id="subtitle-overlay">
          <div className="subtitle-stage">
            {prevChunk >= 0 && prevChunk !== activeChunk && prevChunk < subtitleChunks.length && (
              <div key={"sub-exit-" + animTick} className="subtitle-block subtitle-exit">
                {subtitleChunks[prevChunk]}
              </div>
            )}
            <div key={"sub-enter-" + animTick} className="subtitle-block subtitle-enter">
              {subtitleChunks[activeChunk]}
            </div>
          </div>
        </div>
      )}
      {/* Subtitles (non-TTS mode: streaming text, no animation) */}
      {showSubtitles && currentSubtitle && !isTtsPlaying && (
        <div id="subtitle-overlay">
          <span className="subtitle-text">{currentSubtitle}</span>
        </div>
      )}

      {/* HUD Overlay */}
      <div id="hud">
        {/* Top Bar */}
        <TopBar
          status={wsStatus}
          settingsOpen={settingsOpen}
          onToggleSettings={() => setSettingsOpen((v) => !v)}
        />

        {/* Left Drawer (Sessions, Memory, Skills) — hover left edge to open */}
        <LeftDrawer
          open={leftDrawerOpen}
          onOpen={() => setLeftDrawerOpen(true)}
          onClose={() => setLeftDrawerOpen(false)}
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
          onRefreshSessions={loadSessions}
          loadingSessions={loadingSessions}
        />

        {/* Chat Panel (bottom-right) */}
        <ChatModule
          messages={messages}
          onSendMessage={handleSendMessage}
          onStop={handleStop}
          isStreaming={isStreaming}
          activeTools={activeTools}
          reasoningEffort={reasoningEffort}
          onReasoningEffortChange={setReasoningEffort}
          infoModel={infoModel}
          sttAutoSend={sttAutoSend}
          responseStartTime={responseStartTime}
          showChatHistory={showChatHistory}
        />

        {/* Info Bar (bottom strip) */}
        <InfoBar
          provider={infoProvider}
          model={infoModel}
          toolCount={toolCount}
          version={APP_VERSION}
          groupedModels={groupedModels}
          onSelectModel={handleModelSelect}
          onSelectProvider={handleProviderSelect}
          providerEnabled={providerEnabled}
          providerProfiles={providerProfiles}
        />

        {/* Connection Badge */}
        <div id="connection-badge">
          <span className={`status-dot ${wsStatus}`} />
          <span id="status-text">
            {wsStatus === 'connected' ? 'CONNECTED' :
             wsStatus === 'connecting' ? 'CONNECTING...' :
             'DISCONNECTED'}
          </span>
        </div>
      </div>

      {/* Settings Panel (slide-in from right) */}
      <SettingsPanel
        open={settingsOpen}
        onClose={handleSettingsClose}
        onChange={handleSettingsChange}
        onKeyAdded={handleKeyAdded}
      />
    </>
  );
}
