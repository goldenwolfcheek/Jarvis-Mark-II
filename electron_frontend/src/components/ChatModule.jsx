import React, { useState, useRef, useEffect, useCallback } from 'react';
import TypingIndicator from './TypingIndicator';
import { supportsReasoningEffort, API_URL } from '../utils/constants';

// ── MediaRecorder STT (backed by faster-whisper on backend) ──
// Replaces browser SpeechRecognition API which breaks in Electron.
const sttSupported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

export default function ChatModule({ messages, onSendMessage, isStreaming, activeTools, reasoningEffort, onReasoningEffortChange, infoModel, sttAutoSend, responseStartTime, onStop, showChatHistory = true }) {
  const [input, setInput] = useState('');
  const [exitingTools, setExitingTools] = useState([]);
  const [sttRecording, setSttRecording] = useState(false);
  const [sttStatus, setSttStatus] = useState(''); // '', 'listening', 'processing', 'error'
  const [elapsedMs, setElapsedMs] = useState(0);
  // ── File upload state ──
  const [attachedFiles, setAttachedFiles] = useState([]); // [{id: string, name: string, size: number, uploading: bool}]
  const [dragover, setDragover] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const chatMessagesRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const mediaChunksRef = useRef([]);
  const streamRef = useRef(null);
  const fileInputRef = useRef(null);
  // ── Tracks whether we've done the initial history scroll ──
  const hasScrolledRef = useRef(false);
  // ── Silence detection refs ──
  const silenceRafRef = useRef(null);
  const lastSoundTimeRef = useRef(Date.now());
  const silenceCtxRef = useRef(null);
  const showEffort = supportsReasoningEffort(infoModel);

  // ── Track tool transitions for exit animation ──
  const prevToolNamesRef = useRef([]);
  const exitTimersRef = useRef({});
  useEffect(() => {
    const currentNames = (activeTools || []).map(t => t.name);
    const prevNames = prevToolNamesRef.current;
    // Tools that were present but now gone — animate exit
    const removed = prevNames.filter(n => !currentNames.includes(n));
    if (removed.length > 0) {
      // Add to exiting set immediately
      setExitingTools(prev => [...prev, ...removed.map(name => ({ name, exitKey: `${name}_${Date.now()}_${Math.random()}` }))]);
      // Schedule removal from the exit set after animation (300ms)
      for (const name of removed) {
        if (exitTimersRef.current[name]) clearTimeout(exitTimersRef.current[name]);
        exitTimersRef.current[name] = setTimeout(() => {
          setExitingTools(prev => prev.filter(t => t.name !== name));
          delete exitTimersRef.current[name];
        }, 350);
      }
    }
    prevToolNamesRef.current = currentNames;
  }, [activeTools]);

  // Cleanup exitingTimers on unmount
  useEffect(() => {
    return () => {
      for (const t of Object.values(exitTimersRef.current)) clearTimeout(t);
    };
  }, []);

  // Auto-scroll on new messages — instant on initial history load,
  // smooth for subsequent messages during live chat.
  useEffect(() => {
    if (messagesEndRef.current && messages.length > 0) {
      if (!hasScrolledRef.current) {
        messagesEndRef.current.scrollIntoView(); // instant, no animation
        hasScrolledRef.current = true;
      } else {
        messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
      }
    }
  }, [messages]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Cleanup media resources on unmount
  useEffect(() => {
    return () => {
      stopMediaRecorder();
      stopSilenceDetection();
      stopMediaStream();
    };
  }, []);

  const stopMediaRecorder = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try { mediaRecorderRef.current.stop(); } catch {}
    }
    mediaRecorderRef.current = null;
  };

  const stopMediaStream = () => {
    // Stop silence detection first
    stopSilenceDetection();
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        try { track.stop(); } catch {}
      }
      streamRef.current = null;
    }
  };

  // ── Silence detection (auto-stop after 4s of silence) ──
  const stopSilenceDetection = () => {
    if (silenceRafRef.current) {
      cancelAnimationFrame(silenceRafRef.current);
      silenceRafRef.current = null;
    }
    if (silenceCtxRef.current) {
      silenceCtxRef.current.close().catch(() => {});
      silenceCtxRef.current = null;
    }
  };

  const startSilenceDetection = (stream) => {
    const SILENCE_TIMEOUT = 4000; // 4 seconds of silence → auto-stop
    const SILENCE_THRESHOLD = 0.15; // Normalized RMS — below this is silence

    stopSilenceDetection(); // Clean any previous detector
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      silenceCtxRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      lastSoundTimeRef.current = Date.now();

      const check = () => {
        if (!mediaRecorderRef.current || mediaRecorderRef.current.state !== 'recording') return;

        analyser.getByteTimeDomainData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          const val = (dataArray[i] - 128) / 128;
          sum += val * val;
        }
        const rms = Math.sqrt(sum / dataArray.length);

        if (rms > SILENCE_THRESHOLD) {
          lastSoundTimeRef.current = Date.now();
        } else if (Date.now() - lastSoundTimeRef.current > SILENCE_TIMEOUT) {
          console.log('[STT] Silence timeout — auto-stopping');
          setSttStatus('processing');
          if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
            try { mediaRecorderRef.current.stop(); } catch {}
          }
          mediaRecorderRef.current = null;
          return;
        }
        silenceRafRef.current = requestAnimationFrame(check);
      };
      silenceRafRef.current = requestAnimationFrame(check);
      console.log('[STT] Silence detector started (timeout: ' + SILENCE_TIMEOUT + 'ms)');
    } catch (err) {
      console.warn('[STT] Silence detection setup failed:', err);
    }
  };

  // ── Upload a single file to backend, return file_id ──
  const uploadFileToBackend = async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_URL}/api/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Upload failed (${res.status}): ${text.slice(0, 200)}`);
    }
    return await res.json();
  };

  // ── Handle files picked from file dialog or dragged ──
  const handleFiles = async (fileList) => {
    setUploadError('');
    const files = Array.from(fileList);
    const newAttachments = [];

    for (const file of files) {
      if (file.size > MAX_FILE_SIZE) {
        setUploadError(`"${file.name}" is too large (max 10 MB)`);
        continue;
      }

      // Add a placeholder while uploading
      const placeholder = { id: null, name: file.name, size: file.size, uploading: true, file };
      newAttachments.push(placeholder);
    }

    if (newAttachments.length === 0) return;

    setAttachedFiles(prev => [...prev, ...newAttachments]);

    // Upload each file in sequence
    for (let i = 0; i < newAttachments.length; i++) {
      const entry = newAttachments[i];
      try {
        const result = await uploadFileToBackend(entry.file);
        // Update the entry with the real file_id
        setAttachedFiles(prev => prev.map(a =>
          a.name === entry.name && a.uploading === true && a.file === entry.file
            ? { id: result.file_id, name: result.filename, size: result.size, uploading: false, file: undefined }
            : a
        ));
      } catch (err) {
        console.warn('[File] Upload error:', err);
        setUploadError(`Failed to upload "${entry.name}"`);
        setAttachedFiles(prev => prev.filter(a => a !== entry));
      }
    }
  };

  // ── File dialog ──
  const handleFileButtonClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelect = (e) => {
    if (e.target.files?.length > 0) {
      handleFiles(e.target.files);
    }
    e.target.value = ''; // Reset so same file can be re-picked
  };

  // ── Drag-and-drop ──
  const handleDragover = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragover(true);
  };

  const handleDragleave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    // Only hide overlay when genuinely leaving the wrapper,
    // not when entering a child element (which causes flicker)
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setDragover(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragover(false);
    if (e.dataTransfer?.files?.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  // ── Remove an attached file ──
  const handleRemoveFile = (index) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleSend = async () => {
    const text = input.trim();
    if ((!text && attachedFiles.length === 0) || isStreaming) return;

    // Collect file IDs for files that finished uploading
    const fileIds = attachedFiles
      .filter(f => f.id !== null && !f.uploading)
      .map(f => f.id);

    onSendMessage(text, fileIds);
    setInput('');
    setAttachedFiles([]);
    inputRef.current?.focus();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Auto-resize textarea
  const handleInput = (e) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 100) + 'px';
  };

  // ── STT logic (MediaRecorder → POST /api/stt/transcribe) ──
  const toggleStt = useCallback(async () => {
    if (!sttSupported) return;

    if (sttRecording) {
      // Stop recording
      setSttStatus('processing');
      stopMediaRecorder();
      // Don't reset state here — ondataavailable/onstop will fire
      return;
    }

    // Clear previous status
    setSttStatus('listening');
    mediaChunksRef.current = [];

    try {
      // Request microphone access
      console.log('[STT] Requesting mic...');
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: { ideal: 16000 },
          channelCount: { ideal: 1 },
          echoCancellation: true,
          noiseSuppression: true,
        }
      });
      streamRef.current = stream;
      console.log('[STT] Mic granted, tracks:', stream.getAudioTracks().length);

      // Determine best supported mime type
      const mimeTypes = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/mp4',
      ];
      let mimeType = '';
      for (const mt of mimeTypes) {
        if (MediaRecorder.isTypeSupported(mt)) {
          mimeType = mt;
          break;
        }
      }
      console.log('[STT] Using mime:', mimeType || 'browser-default');

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          mediaChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        // Stop the media tracks
        stopMediaStream();

        const chunks = mediaChunksRef.current;
        mediaChunksRef.current = [];
        console.log('[STT] Stopped, chunks:', chunks.length);

        if (chunks.length === 0) {
          setSttStatus('error');
          setSttRecording(false);
          setTimeout(() => setSttStatus(''), 2000);
          return;
        }

        // Assemble blob with the mime type we used
        const blob = new Blob(chunks, { type: mimeType || 'audio/webm' });

        // Send to backend
        try {
          const formData = new FormData();
          formData.append('file', blob, 'recording.' + (mimeType.includes('webm') ? 'webm' : mimeType.includes('ogg') ? 'ogg' : 'mp4'));

          console.log('[STT] Sending', blob.size, 'bytes to backend');
          const response = await fetch(`${API_URL}/api/stt/transcribe`, {
            method: 'POST',
            body: formData,
          });

          if (!response.ok) {
            const errText = await response.text();
            console.warn('[STT] Backend error:', response.status, errText);
            setSttStatus('error');
            setSttRecording(false);
            setTimeout(() => setSttStatus(''), 2000);
            return;
          }

          const data = await response.json();
          console.log('[STT] Result:', data);

          if (data.status === 'ok' && data.text) {
            if (sttAutoSend) {
              onSendMessage(data.text);
            } else {
              setInput((prev) => {
                const newVal = prev ? prev + ' ' + data.text : data.text;
                return newVal;
              });
              // Auto-resize textarea
              setTimeout(() => {
                if (inputRef.current) {
                  inputRef.current.style.height = 'auto';
                  inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 100) + 'px';
                }
              }, 0);
            }
          }

          setSttStatus('');
          setSttRecording(false);

        } catch (err) {
          console.warn('[STT] Network error:', err);
          setSttStatus('error');
          setSttRecording(false);
          setTimeout(() => setSttStatus(''), 2000);
        }
      };

      recorder.onerror = (event) => {
        console.warn('[STT] Recorder error:', event.error);
        stopMediaStream();
        setSttStatus('error');
        setSttRecording(false);
        setTimeout(() => setSttStatus(''), 2000);
      };

      recorder.start(250); // Collect data every 250ms for low latency
      setSttRecording(true);
      // Start silence monitoring — auto-stops after 4s of no speech
      startSilenceDetection(stream);

    } catch (err) {
      console.warn('[STT] Mic access denied:', err);
      setSttStatus('error');
      setSttRecording(false);
      setTimeout(() => setSttStatus(''), 2000);
    }
  }, [sttRecording]);

  // Clear status after timeout
  useEffect(() => {
    if (sttStatus === 'error') {
      const timer = setTimeout(() => setSttStatus(''), 3000);
      return () => clearTimeout(timer);
    }
  }, [sttStatus]);

  // ── Timer for response duration ──
  useEffect(() => {
    if (!isStreaming || !responseStartTime) {
      setElapsedMs(0);
      return;
    }
    const interval = setInterval(() => {
      setElapsedMs(Date.now() - responseStartTime);
    }, 100);
    return () => clearInterval(interval);
  }, [isStreaming, responseStartTime]);

  // Format milliseconds to display string
  const formatDuration = (ms) => {
    if (!ms && ms !== 0) return null;
    const totalSeconds = ms / 1000;
    if (totalSeconds < 1) return `${ms}ms`;
    if (totalSeconds < 60) return `${totalSeconds.toFixed(1)}s`;
    const mins = Math.floor(totalSeconds / 60);
    const secs = Math.floor(totalSeconds % 60);
    return `${mins}m ${secs}s`;
  };

  // ── Determine which pills to show (tools + attached files) ──
  const runningTools = (activeTools || []).filter(t => t.status === 'running');
  const hasPills = runningTools.length > 0 || exitingTools.length > 0 || attachedFiles.length > 0;

  return (
    <div
      className="chat-wrapper"
      onDragOver={handleDragover}
      onDragLeave={handleDragleave}
      onDrop={handleDrop}
    >
      {/* Drag-over overlay */}
      {dragover && (
        <div className="drag-overlay">
          <div className="drag-overlay-content">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <span>Drop files here</span>
          </div>
        </div>
      )}

      {/* Active tool pills + file pills — above the chat panel */}
      {hasPills && (
        <div id="tool-bar">
          {/* Exiting tools (animate out) */}
          {exitingTools.map((et) => (
            <span key={et.exitKey} className="tool-pill tool-pill-exit" style={{ color: 'rgba(0,212,255,0.3)', borderColor: 'rgba(0,212,255,0.08)' }}>
              {et.name}
            </span>
          ))}
          {/* Currently running tools (animate in) */}
          {runningTools.map((t, i) => (
            <span key={t.name + t.time} className="tool-pill">
              <span className="dot" />
              {t.name}
            </span>
          ))}
          {/* Attached file pills */}
          {attachedFiles.map((f, i) => (
            <span key={`file-${i}`} className="tool-pill tool-pill-file">
              <span className="file-pill-icon">📎</span>
              {f.uploading ? (
                <span className="file-pill-uploading">{f.name} <span className="file-pill-spinner" /></span>
              ) : (
                <>
                  <span className="file-pill-name">{f.name}</span>
                  <button
                    className="file-pill-remove"
                    onClick={() => handleRemoveFile(i)}
                    title="Remove file"
                  >
                    ✕
                  </button>
                </>
              )}
            </span>
          ))}
        </div>
      )}

      <div id="chat-panel" className="glass-panel">
        {/* Header */}
      <div id="chat-header">
        <span id="chat-session-label">Session</span>
        {showEffort && (
          <span className="chat-header-effort-wrap">
            <select
              value={reasoningEffort || ''}
              onChange={(e) => onReasoningEffortChange(e.target.value)}
              className="chat-header-effort-select"
            >
              <option value="">—</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </span>
        )}
        <span id="chat-msg-count" className="dim">{messages.length > 0 ? `${messages.length} msg` : ''}</span>
      </div>

      {/* Messages */}
      {showChatHistory && (
      <div id="chat-messages" ref={chatMessagesRef}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', color: '#4a6a80', fontSize: 12, paddingTop: 40 }}>
            Type a message to start chatting with Jarvis.
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`message message-${msg.role} ${msg._streaming ? 'msg-streaming' : ''}`}
          >
            <span className="msg-label">
              {msg.role === 'user' ? 'YOU' : msg.role === 'assistant' ? 'JARVIS' : msg.role.toUpperCase()}
            </span>
            <span className="msg-bubble">{msg.content}</span>
            {/* File indicators on user messages */}
            {msg.role === 'user' && msg._file_ids && msg._file_ids.length > 0 && (
              <span className="msg-file-indicator">📎 {msg._file_ids.length} file{msg._file_ids.length > 1 ? 's' : ''}</span>
            )}
            {/* Response timer for assistant messages */}
            {msg.role === 'assistant' && (
              <span className="msg-timer">
                {msg._duration
                  ? `⏱ ${formatDuration(msg._duration)}`
                  : (i === messages.length - 1 && isStreaming && elapsedMs > 0)
                    ? `⏱ ${formatDuration(elapsedMs)}`
                    : null}
              </span>
            )}
            <button
              className="msg-copy-btn"
              onClick={() => {
                const text = msg.content || '';
                // Try modern clipboard API first, fallback to execCommand
                if (navigator.clipboard && navigator.clipboard.writeText) {
                  navigator.clipboard.writeText(text).catch(() => {
                    // Fallback: create a temporary textarea
                    const ta = document.createElement('textarea');
                    ta.value = text;
                    ta.style.position = 'fixed';
                    ta.style.opacity = '0';
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                  });
                } else {
                  const ta = document.createElement('textarea');
                  ta.value = text;
                  ta.style.position = 'fixed';
                  ta.style.opacity = '0';
                  document.body.appendChild(ta);
                  ta.select();
                  document.execCommand('copy');
                  document.body.removeChild(ta);
                }
              }}
              title="Copy text"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
            </button>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      )}

      {/* Typing indicator */}
      {isStreaming && <TypingIndicator />}

      {/* Upload error toast */}
      {uploadError && (
        <div className="upload-error-toast" onClick={() => setUploadError('')}>
          {uploadError}
        </div>
      )}

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        style={{ display: 'none' }}
        onChange={handleFileSelect}
        accept=".txt,.md,.py,.js,.jsx,.ts,.tsx,.html,.css,.json,.xml,.yaml,.yml,.csv,.log,.sh,.bat,.ps1,.sql,.go,.rs,.java,.cpp,.c,.h,.rb,.php,.pl,.lua,.swift,.kt,.dart,.tex,.rst,.env,.gitignore,.pdf,.png,.jpg,.jpeg,.gif,.webp,.bmp,.svg,.toml,.ini,.cfg,.conf,.dockerfile,.gradle,.makefile"
      />

      {/* Input area */}
      <div id="chat-input-area">
        <button
          id="btn-file"
          onClick={handleFileButtonClick}
          disabled={isStreaming}
          title="Attach file"
          className={attachedFiles.length > 0 ? 'has-files' : ''}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </button>
        <textarea
          ref={inputRef}
          id="chat-input"
          rows={1}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={sttStatus === 'listening' ? 'Listening...' : sttStatus === 'processing' ? 'Processing...' : 'Type a message...'}
          enterKeyHint="send"
          disabled={isStreaming}
        />
        <button
          id="btn-send"
          onClick={isStreaming ? () => onStop?.() : handleSend}
          disabled={!isStreaming && !input.trim() && attachedFiles.length === 0}
          title={isStreaming ? 'Stop' : 'Send'}
          className={isStreaming ? 'btn-stop' : ''}
        >
          {isStreaming ? '⏹' : '➤'}
        </button>
        {sttSupported && (
          <button
            id="btn-stt"
            onClick={toggleStt}
            disabled={isStreaming}
            title={
              sttRecording ? 'Stop recording' :
              sttStatus === 'error' ? 'Voice input unavailable' :
              sttStatus === 'processing' ? 'Transcribing...' :
              'Voice input'
            }
            className={
              sttRecording ? 'recording' :
              sttStatus === 'processing' ? 'processing' :
              sttStatus === 'error' ? 'error' : ''
            }
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="23" />
              <line x1="8" y1="23" x2="16" y2="23" />
            </svg>
          </button>
        )}
      </div>
    </div>
    </div>
  );
}
