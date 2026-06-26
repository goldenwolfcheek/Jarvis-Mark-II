import React, { useState, useEffect, useCallback, useRef } from 'react';
import { fetchConfig, fetchProviders, fetchModels, fetchVoiceList, fetchSystemInfo, updateConfig, saveProviderKey, deleteProviderKey, testProviderKey, checkForUpdate, applyUpdate, getUpdateStatus } from '../utils/api';

export default function SettingsPanel({ open, onClose, onChange, onKeyAdded }) {
  // ── State ──
  const [providers, setProviders] = useState([]);
  const [providerProfiles, setProviderProfiles] = useState({});
  const [connectedProviders, setConnectedProviders] = useState([]);
  const [editingProvider, setEditingProvider] = useState(null);
  const [editApiKey, setEditApiKey] = useState('');
  const [providerEnabled, setProviderEnabled] = useState(() => {
    try { return JSON.parse(localStorage.getItem('jarvis_provider_toggles') || '{}'); }
    catch { return {}; }
  });
  const [models, setModels] = useState([]);
  const [voices, setVoices] = useState([]);
  const [config, setConfig] = useState({});
  const [systemInfo, setSystemInfo] = useState({});
  const [loadingModels, setLoadingModels] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingKey, setTestingKey] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [addingKey, setAddingKey] = useState(false);

  // ── Form state ──
  const [activeProvider, setActiveProvider] = useState('');
  const [activeModel, setActiveModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [temperature, setTemperature] = useState(0.7);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [volume, setVolume] = useState(80);
  const [voice, setVoice] = useState('');

  const [theme, setTheme] = useState('dark');
  const [autoboot, setAutoboot] = useState(false);
  const [sttAutoSend, setSttAutoSend] = useState(false);
  const [showChatHistory, setShowChatHistory] = useState(() => {
    try { return localStorage.getItem('jarvis_show_chat_history') !== 'false'; }
    catch { return true; }
  });
  const [showSubtitles, setShowSubtitles] = useState(() => {
    try { return localStorage.getItem('jarvis_show_subtitles') === 'true'; }
    catch { return false; }
  });
  const [devConsole, setDevConsole] = useState(() => {
    try { return localStorage.getItem('jarvis_dev_console') !== 'false'; }
    catch { return true; }
  });
  const [minimizeToTray, setMinimizeToTray] = useState(() => {
    try { return localStorage.getItem('jarvis_minimize_to_tray') === 'true'; }
    catch { return false; }
  });

  // ── Update state ──
  const [updateStatus, setUpdateStatus] = useState(null);  // result from checkForUpdate()
  const [updateState, setUpdateState] = useState({});       // info from getUpdateStatus()
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [applyingUpdate, setApplyingUpdate] = useState(false);
  const [updateResult, setUpdateResult] = useState(null);   // result from applyUpdate()

  // ── Live uptime ──
  const serverStartRef = useRef(null); // Date.now() approximation of server start
  const [liveUptime, setLiveUptime] = useState(0);

  // ── Debounce helpers ──
  const autoSaveTimerRef = useRef({});

  // ── Auto-save a single config key with debounce ──
  const autoSave = useCallback(async (key, value) => {
    // Clear any pending save for this key
    if (autoSaveTimerRef.current[key]) {
      clearTimeout(autoSaveTimerRef.current[key]);
    }
    // Debounce by 150ms to avoid rapid saves on sliders
    autoSaveTimerRef.current[key] = setTimeout(async () => {
      try {
        await updateConfig(key, value);
      } catch (e) {
        console.warn(`[Settings] Auto-save ${key} failed:`, e);
      }
    }, 150);
  }, []);

  // ── Load data when opened ──
  const loadAll = useCallback(async () => {
    try {
      const [configData, providersData, voicesData, sysData, updateData] = await Promise.all([
        fetchConfig().catch(() => ({})),
        fetchProviders().catch(() => ({ profiles: [] })),
        fetchVoiceList(),
        fetchSystemInfo(),
        getUpdateStatus(),
      ]);

      setConfig(configData);
      setSystemInfo(sysData);
      setUpdateState(updateData || {});

      // Process providers
      const rawProfiles = providersData.profiles || providersData.providers || [];
      const profilesMap = {};
      const providersList = [];
      if (Array.isArray(rawProfiles)) {
        for (const p of rawProfiles) {
          if (p.name) {
            providersList.push(p.name);
            profilesMap[p.name] = p;
          }
        }
      } else {
        Object.assign(profilesMap, rawProfiles);
        providersList.push(...(providersData.providers || Object.keys(rawProfiles)));
      }
      setProviderProfiles(profilesMap);
      setProviders(providersList);

      // Don't pre-select provider — user should choose
      setActiveProvider('');

      // Set form values from config (API key stays blank for security)
      setConfig(configData);
      setActiveModel(configData.active_model || configData.model || '');
      setApiKey('');  // Never pre-fill API key
      setTemperature(configData.temperature ?? 0.7);
      setTtsEnabled(configData.tts_enabled ?? true);
      setVolume(configData.volume ?? 80);
      setTheme(configData.theme || 'dark');
      setAutoboot(configData.autoboot ?? false);
      setSttAutoSend(configData.stt_auto_send ?? false);
      setShowChatHistory(configData.show_chat_history ?? true);
      setShowSubtitles(configData.show_subtitles ?? false);

      // Voices
      setVoices(voicesData);
      if (voicesData.length > 0) {
        const defaultVoice = voicesData[0]?.id || voicesData[0]?.name || '';
        setVoice(configData.tts_voice || defaultVoice);
      }

      // ── Initialise live uptime ──
      const uptimeSec = sysData.uptime_seconds ?? sysData.uptime ?? 0;
      if (uptimeSec > 0) {
        serverStartRef.current = Date.now() - uptimeSec * 1000;
        setLiveUptime(uptimeSec);
      } else {
        serverStartRef.current = null;
        setLiveUptime(0);
      }

      // Don't load models until user picks a provider
    } catch (e) {
      console.error('[Settings] Load error:', e);
    }
  }, []);

  useEffect(() => {
    if (open) {
      loadAll();
    }
  }, [open, loadAll]);

  // ── Live uptime tick ──
  useEffect(() => {
    if (!open) return;
    if (!serverStartRef.current) return;
    const interval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - serverStartRef.current) / 1000);
      setLiveUptime(elapsed);
    }, 1000);
    return () => clearInterval(interval);
  }, [open]);

  // Clear sensitive state when panel closes
  useEffect(() => {
    if (!open) {
      setApiKey('');
      setTestResult(null);
      setEditingProvider(null);
      setEditApiKey('');
    }
  }, [open]);

  // ── Load models ──
  const loadModels = async (provider, forceRefresh = false, selectModel = '') => {
    setLoadingModels(true);
    try {
      const data = await fetchModels(provider, forceRefresh);
      const modelList = data.models || [];
      setModels(modelList);
      if (selectModel && modelList.some(m => (m.id || m.name || m) === selectModel)) {
        setActiveModel(selectModel);
      } else if (modelList.length > 0) {
        setActiveModel(modelList[0]?.id || modelList[0]?.name || modelList[0]);
      } else {
        setActiveModel('');
      }
    } catch (e) {
      console.error('[Settings] Model load error:', e);
      setModels([]);
      setActiveModel('');
    } finally {
      setLoadingModels(false);
    }
  };

  // ── Provider change ──
  const handleProviderChange = (provider) => {
    setActiveProvider(provider);
    loadModels(provider, false);
  };

  // ── Auto-save theme with immediate DOM update ──
  const handleThemeChange = (newTheme) => {
    setTheme(newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
    autoSave('theme', newTheme);
  };

  // ── Auto-save TTS toggle ──
  const handleTtsToggle = (enabled) => {
    setTtsEnabled(enabled);
    autoSave('tts_enabled', enabled);
    // Notify parent so App can sync
    if (onChange) onChange({ tts_enabled: enabled });
  };

  // ── Auto-save volume ──
  const handleVolumeChange = (newVolume) => {
    setVolume(newVolume);
    autoSave('volume', newVolume);
  };

  // ── Auto-save temperature ──
  const handleTemperatureChange = (newTemp) => {
    setTemperature(newTemp);
    autoSave('temperature', newTemp);
  };

  // ── Auto-save voice ──
  const handleVoiceChange = useCallback(async (newVoice) => {
    setVoice(newVoice);
    try {
      await updateConfig('tts_voice', newVoice);
    } catch (e) {
      console.warn('[Settings] Failed to save voice:', e);
    }
  }, []);

  // ── Auto-save autoboot ──
  const handleAutobootChange = (enabled) => {
    setAutoboot(enabled);
    autoSave('autoboot', enabled);
    // Register/unregister with OS auto-start (Electron)
    if (window.electronAPI?.setAutoboot) {
      window.electronAPI.setAutoboot(enabled);
    }
  };

  // ── Developer Console toggle ──
  const handleDevConsoleChange = (enabled) => {
    setDevConsole(enabled);
    try { localStorage.setItem('jarvis_dev_console', enabled ? 'true' : 'false'); } catch {}
    if (window.electronAPI?.setDevConsole) {
      window.electronAPI.setDevConsole(enabled);
    }
  };

  // ── Minimize to Tray toggle ──
  const handleMinimizeToTrayChange = (enabled) => {
    setMinimizeToTray(enabled);
    try { localStorage.setItem('jarvis_minimize_to_tray', enabled ? 'true' : 'false'); } catch {}
    if (window.electronAPI?.setMinimizeToTray) {
      window.electronAPI.setMinimizeToTray(enabled);
    }
  };

  // ── Auto-save STT auto-send ──
  const handleSttAutoSendToggle = (enabled) => {
    setSttAutoSend(enabled);
    autoSave('stt_auto_send', enabled);
    if (onChange) onChange({ stt_auto_send: enabled });
  };

  // ── Chat history toggle ──
  const handleChatHistoryToggle = (enabled) => {
    setShowChatHistory(enabled);
    autoSave('show_chat_history', enabled);
    try { localStorage.setItem('jarvis_show_chat_history', enabled ? 'true' : 'false'); } catch {}
    if (onChange) onChange({ show_chat_history: enabled });
  };

  // ── Subtitles toggle ──
  const handleSubtitlesToggle = (enabled) => {
    setShowSubtitles(enabled);
    autoSave('show_subtitles', enabled);
    try { localStorage.setItem('jarvis_show_subtitles', enabled ? 'true' : 'false'); } catch {}
    if (onChange) onChange({ show_subtitles: enabled });
  };

  // ── Export config (save to file, excludes API keys) ──
  const handleExportConfig = async () => {
    setSaving(true);
    try {
      // Gather all current settings into a portable config object
      const exportable = {
        temperature,
        tts_enabled: ttsEnabled,
        volume,
        theme,
        autoboot,
        tts_voice: voice,
        active_provider: activeProvider || undefined,
        active_model: activeModel || undefined,
        version: 1,
        exported_at: new Date().toISOString(),
      };

      // Create a downloadable blob
      const blob = new Blob([JSON.stringify(exportable, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `jarvis-config-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('[Settings] Export failed:', e);
    } finally {
      setSaving(false);
    }
  };

  // ── Reset ──
  const handleReset = async () => {
    try {
      const res = await fetch('http://127.0.0.1:11711/api/config/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      if (res.ok) {
        if (onChange) onChange({ reset: true });
        await loadAll();
      }
    } catch (e) {
      console.error('[Settings] Reset error:', e);
    }
  };

  // ── Provider profile ──
  const currentProfile = providerProfiles[activeProvider] || {};

  // ── Format uptime for display ──
  const formatUptime = (seconds) => {
    if (!seconds && seconds !== 0) return '—';
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    const parts = [];
    if (d > 0) parts.push(`${d}d`);
    if (h > 0) parts.push(`${h}h`);
    if (m > 0) parts.push(`${m}m`);
    parts.push(`${s}s`);
    return parts.join(' ');
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 animate-fade-in">
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Panel */}
      <div className="absolute right-0 top-0 bottom-0 w-full max-w-md bg-jarvis-surface/95 backdrop-blur-xl border-l border-jarvis-border animate-slide-in overflow-y-auto">
        <div className="p-5">
          {/* Header */}
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-lg font-bold tracking-wider text-jarvis-accent">Settings</h2>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/5 text-jarvis-muted hover:text-jarvis-text transition-colors">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* ── Updates ── */}
          <Section title="Updates">
            <div className="text-xs space-y-2 text-jarvis-muted p-3 rounded-lg border-2 border-jarvis-accent/30 bg-jarvis-accent/5">
              {/* Current version info at the top of settings for quick access */}
              <p className="text-jarvis-accent font-medium text-sm mb-1">
                ⚡ Auto-Updates
              </p>
              <p>
                <span className="text-jarvis-text/60">Current Version:</span>{' '}
                <span className="text-jarvis-text font-mono">{updateState.current_version || systemInfo.version || '—'}</span>
                {updateState.last_checked_at && (
                  <span className="block text-[10px] mt-0.5">Last checked: {updateState.last_checked_at}</span>
                )}
              </p>

              {updateStatus && !updateStatus.error && (
                <div className={`p-2 rounded-lg ${updateStatus.has_update ? 'bg-yellow-500/10 border border-yellow-500/20' : 'bg-green-500/10 border border-green-500/20'}`}>
                  {updateStatus.has_update ? (
                    <div>
                      <p className="text-yellow-400 font-medium">Update Available</p>
                      <p className="text-[10px] mt-1 text-jarvis-muted">{updateStatus.commit_message}</p>
                      <p className="text-[10px] text-jarvis-muted/60">{updateStatus.commit_date}</p>
                    </div>
                  ) : (
                    <p className="text-green-400">You're up to date!</p>
                  )}
                </div>
              )}

              {updateStatus && updateStatus.error && (
                <p className="text-red-400 text-[10px]">{updateStatus.error}</p>
              )}

              {updateResult && (
                <div className={`p-2 rounded-lg ${updateResult.success ? 'bg-green-500/10 border border-green-500/20' : 'bg-red-500/10 border border-red-500/20'}`}>
                  <p className={`text-xs ${updateResult.success ? 'text-green-400' : 'text-red-400'}`}>
                    {updateResult.success ? '✅ Update applied!' : '❌ Update failed'}
                  </p>
                  <p className="text-[10px] mt-1 text-jarvis-muted whitespace-pre-line">{updateResult.message}</p>
                  {updateResult.success && (
                    <p className="text-[10px] mt-1 text-yellow-400">Please restart Jarvis for changes to take effect.</p>
                  )}
                </div>
              )}

              <div className="flex gap-2 pt-1">
                <button
                  onClick={async () => {
                    setCheckingUpdate(true);
                    setUpdateResult(null);
                    const result = await checkForUpdate();
                    setUpdateStatus(result);
                    setCheckingUpdate(false);
                  }}
                  disabled={checkingUpdate}
                  className="flex-1 py-1.5 rounded-lg text-xs bg-jarvis-accent/20 border border-jarvis-accent/30 hover:bg-jarvis-accent/30 text-jarvis-accent font-medium transition-all disabled:opacity-40"
                >
                  {checkingUpdate ? 'Checking...' : 'Check for Updates'}
                </button>
                <button
                  onClick={async () => {
                    setApplyingUpdate(true);
                    setUpdateResult(null);
                    const result = await applyUpdate();
                    setUpdateResult(result);
                    setApplyingUpdate(false);
                  }}
                  disabled={applyingUpdate || !(updateStatus?.has_update)}
                  className="flex-1 py-1.5 rounded-lg text-xs bg-green-500/20 border border-green-500/30 hover:bg-green-500/30 text-green-400 font-medium transition-all disabled:opacity-40"
                >
                  {applyingUpdate ? 'Applying...' : 'Apply Update'}
                </button>
              </div>
            </div>
          </Section>

          {/* ── Provider Selector ── */}
          <Section title="Provider Selector">
            <select
              value={activeProvider}
              onChange={(e) => handleProviderChange(e.target.value)}
              className="w-full bg-jarvis-bg border border-jarvis-border rounded-lg px-3 py-2 text-sm text-jarvis-text focus:border-jarvis-accent/50"
            >
              <option value="">-- Select Provider --</option>
              {providers.map((p) => (
                <option key={p} value={p}>
                  {providerProfiles[p]?.display_name || p.charAt(0).toUpperCase() + p.slice(1)}
                </option>
              ))}
            </select>

            {/* Provider details */}
            {currentProfile.name && (
              <div className="mt-2 p-2.5 rounded-lg bg-jarvis-bg/50 text-xs space-y-1 text-jarvis-muted">
                {currentProfile.description && <p>{currentProfile.description}</p>}
                <p><span className="text-jarvis-text/60">Base URL:</span> {currentProfile.base_url || currentProfile.baseUrl || '—'}</p>
                <p><span className="text-jarvis-text/60">Vision:</span> {currentProfile.supports_vision ? '✅ Yes' : '—'}</p>
              </div>
            )}
          </Section>

          {/* ── Model Selector (moved to InfoBar — code preserved) ── */}
          {/* <Section title="Model">...</Section> */}

          {/* ── API Key ── */}
          <Section title="API Key">
            <div className="flex gap-2">
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                onFocus={() => setTestResult(null)}
                placeholder="Enter API key..."
                className="flex-1 bg-jarvis-bg border border-jarvis-border rounded-lg px-3 py-2 text-sm text-jarvis-text placeholder-jarvis-muted focus:border-jarvis-accent/50"
              />
            </div>
            <div className="flex gap-2 mt-2">
              <button
                onClick={async () => {
                  if (!apiKey.trim() || testingKey) return;
                  setTestingKey(true);
                  setTestResult(null);
                  const result = await testProviderKey(activeProvider, apiKey.trim());
                  setTestResult(result);
                  setTestingKey(false);
                }}
                disabled={!apiKey.trim() || testingKey}
                className="flex-1 py-1.5 rounded-lg text-xs bg-jarvis-accent/10 border border-jarvis-accent/20 hover:bg-jarvis-accent/20 text-jarvis-accent transition-all disabled:opacity-40"
              >
                {testingKey ? 'Testing...' : 'Test'}
              </button>
              <button
                onClick={async () => {
                  const profile = providerProfiles[activeProvider];
                  const isLocal = profile?.auth_type === "none";
                  // Local providers don't need an API key; auth providers do
                  if (!apiKey.trim() && !isLocal) return;
                  if (addingKey) return;
                  setAddingKey(true);
                  setTestResult(null);

                  if (isLocal) {
                    // Local provider: just enable the toggle, no key needed
                    const toggles = JSON.parse(localStorage.getItem('jarvis_provider_toggles') || '{}');
                    toggles[activeProvider] = true;
                    localStorage.setItem('jarvis_provider_toggles', JSON.stringify(toggles));
                    setProviderEnabled({ ...providerEnabled, [activeProvider]: true });
                    setTestResult({ ok: true, message: 'Local provider enabled' });
                    if (onKeyAdded) onKeyAdded();
                  } else {
                    // Auth provider: save the API key
                    const ok = await saveProviderKey(activeProvider, apiKey.trim());
                    if (ok) {
                      // Enable the newly added provider in localStorage FIRST,
                      // before onKeyAdded reads it (race condition fix)
                      const toggles = JSON.parse(localStorage.getItem('jarvis_provider_toggles') || '{}');
                      toggles[activeProvider] = true;
                      localStorage.setItem('jarvis_provider_toggles', JSON.stringify(toggles));
                      setProviderEnabled({ ...providerEnabled, [activeProvider]: true });

                      setTestResult({ ok: true, message: 'Provider key saved successfully' });
                      if (onKeyAdded) onKeyAdded();
                      // Refresh provider profiles to reflect new key
                      const res = await fetchProviders();
                      const pmap = {};
                      if (Array.isArray(res.profiles)) {
                        for (const p of res.profiles) {
                          if (p.name) pmap[p.name] = p;
                        }
                      }
                      setProviderProfiles(pmap);
                      // Rebuild providers list from updated profiles
                      const newList = Object.keys(pmap).sort();
                      setProviders(newList);
                    } else {
                      setTestResult({ ok: false, message: 'Failed to save API key' });
                    }
                  }
                  setAddingKey(false);
                }}
                disabled={!apiKey.trim() && providerProfiles[activeProvider]?.auth_type !== "none" || addingKey || !activeProvider}
                className="flex-1 py-1.5 rounded-lg text-xs bg-green-500/20 border border-green-500/30 hover:bg-green-500/30 text-green-400 transition-all disabled:opacity-40"
              >
                {addingKey ? 'Adding...' : 'Add'}
              </button>
            </div>
            {testResult && (
              <div className={`mt-1 text-xs ${testResult.ok ? 'text-green-400' : 'text-red-400'}`}>
                {testResult.message}
              </div>
            )}
          </Section>

          {/* ── Temperature ── */}
          <Section title="Temperature">
            <div className="flex justify-between text-[10px] text-jarvis-muted mb-1">
              <span>Precise (0)</span>
              <span>Balanced (1)</span>
              <span>Creative (2)</span>
            </div>
            <input
              type="range"
              min="0"
              max="2"
              step="0.05"
              value={temperature}
              onChange={(e) => handleTemperatureChange(parseFloat(e.target.value))}
              className="w-full accent-jarvis-accent"
            />
            <div className="text-center text-xs text-jarvis-accent mt-1 font-mono">
              {temperature.toFixed(2)}
            </div>
          </Section>

          {/* ── Providers ── */}
          <Section title="Providers">
            {providers.length === 0 ? (
              <p className="text-xs text-jarvis-muted">No providers loaded</p>
            ) : (
              <div className="space-y-2">
                {[...providers]
                  .filter((name) => {
                    const p = providerProfiles[name];
                    return p?.has_api_key || p?.auth_type === "none";
                  })
                  .sort((a, b) => {
                    const na = providerProfiles[a]?.display_name || a;
                    const nb = providerProfiles[b]?.display_name || b;
                    return na.localeCompare(nb);
                  }).map((name) => {
                  const profile = providerProfiles[name] || {};
                  const hasKey = profile.has_api_key;
                  const isEditing = editingProvider === name;
                  return (
                    <div key={name} className="p-2.5 rounded-lg bg-jarvis-bg/50 border border-jarvis-border/50">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${hasKey ? 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]' : 'bg-jarvis-muted/40'}`} />
                          <span className="text-sm text-jarvis-text truncate">
                            {profile.display_name || name.charAt(0).toUpperCase() + name.slice(1)}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          {hasKey && (
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input
                                type="checkbox"
                                checked={providerEnabled[name] !== false}
                                onChange={(e) => {
                                  const updated = { ...providerEnabled, [name]: e.target.checked };
                                  setProviderEnabled(updated);
                                  localStorage.setItem('jarvis_provider_toggles', JSON.stringify(updated));
                                }}
                                className="sr-only peer"
                              />
                              <div className="w-7 h-4 rounded-full bg-jarvis-muted/30 peer-checked:bg-green-500/30 peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-jarvis-muted/60 after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:after:bg-green-400" />
                            </label>
                          )}
                          <button
                            onClick={() => {
                              if (isEditing) {
                                setEditingProvider(null);
                                setEditApiKey('');
                              } else {
                                setEditingProvider(name);
                                setEditApiKey('');
                              }
                            }}
                            className="px-2 py-1 rounded text-xs bg-jarvis-accent/10 border border-jarvis-accent/20 hover:bg-jarvis-accent/20 text-jarvis-accent transition-all"
                          >
                            {isEditing ? 'Cancel' : 'Edit'}
                          </button>
                        </div>
                      </div>
                      {isEditing && (
                        <div className="mt-2 flex gap-2">
                          <input
                            type="password"
                            value={editApiKey}
                            onChange={(e) => setEditApiKey(e.target.value)}
                            placeholder={hasKey ? 'Enter new API key...' : 'Enter API key...'}
                            className="flex-1 bg-jarvis-bg border border-jarvis-border rounded px-2 py-1 text-xs text-jarvis-text placeholder-jarvis-muted focus:border-jarvis-accent/50"
                          />
                          <button
                            onClick={async () => {
                              if (!editApiKey.trim()) return;
                              const ok = await saveProviderKey(name, editApiKey.trim());
                              if (ok) {
                                setEditingProvider(null);
                                setEditApiKey('');
                                // Refresh profiles to update has_api_key status
                                const res = await fetchProviders();
                                const pmap = { ...providerProfiles };
                                if (Array.isArray(res.profiles)) {
                                  for (const p of res.profiles) {
                                    if (p.name) pmap[p.name] = p;
                                  }
                                }
                                setProviderProfiles(pmap);
                              }
                            }}
                            disabled={!editApiKey.trim()}
                            className="px-2 py-1 rounded text-xs bg-green-500/20 border border-green-500/30 hover:bg-green-500/30 text-green-400 transition-all disabled:opacity-40"
                          >
                            Save
                          </button>
                          {hasKey && (
                            <button
                              onClick={async () => {
                                await deleteProviderKey(name);
                                setEditingProvider(null);
                                setEditApiKey('');
                                const res = await fetchProviders();
                                const pmap = { ...providerProfiles };
                                if (Array.isArray(res.profiles)) {
                                  for (const p of res.profiles) {
                                    if (p.name) pmap[p.name] = p;
                                  }
                                }
                                setProviderProfiles(pmap);
                              }}
                              className="px-2 py-1 rounded text-xs bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 text-red-400 transition-all"
                            >
                              Remove
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </Section>

          {/* ── TTS ── */}
          <Section title="Text-to-Speech">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={ttsEnabled}
                onChange={(e) => handleTtsToggle(e.target.checked)}
                className="accent-jarvis-accent"
              />
              <span className="text-sm">Enable TTS</span>
            </label>
            {ttsEnabled && (
              <div className="mt-2 space-y-2">
                <div>
                  <label className="text-xs text-jarvis-muted block mb-1">Voice</label>
                  <select
                    value={voice}
                    onChange={(e) => handleVoiceChange(e.target.value)}
                    className="w-full bg-jarvis-bg border border-jarvis-border rounded-lg px-3 py-1.5 text-sm text-jarvis-text"
                  >
                    {voices.length === 0 ? (
                      <option value="">Default</option>
                    ) : (
                      voices.map((v) => {
                        const id = v.id || v.name || v;
                        const rawName = v.name || v.id || v;
                        // Parse "en-US-JennyNeural" → "Jenny - (en-US)"
                        let label = rawName;
                        if (v.locale && v.name) {
                          const voiceName = v.name.replace(v.locale + '-', '').replace(/Neural$/i, '');
                          label = `${voiceName || rawName} - (${v.locale})`;
                        }
                        return <option key={id} value={id}>{label}</option>;
                      })
                    )}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-jarvis-muted block mb-1">Volume: {volume}%</label>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={volume}
                    onChange={(e) => handleVolumeChange(parseInt(e.target.value))}
                    className="w-full accent-jarvis-accent"
                  />
                </div>
              </div>
            )}
          </Section>

          {/* ── Speech-to-Text ── */}
          <Section title="Speech-to-Text">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={sttAutoSend}
                onChange={(e) => handleSttAutoSendToggle(e.target.checked)}
                className="accent-jarvis-accent"
              />
              <span className="text-sm">Auto-send voice input</span>
            </label>
            <p className="text-[10px] text-jarvis-muted mt-1 ml-1">Transcribes and sends automatically — no need to press send</p>
          </Section>

          {/* ── Theme ── */}
          <Section title="Theme">
            <select
              value={theme}
              onChange={(e) => handleThemeChange(e.target.value)}
              className="w-full bg-jarvis-bg border border-jarvis-border rounded-lg px-3 py-2 text-sm text-jarvis-text focus:border-jarvis-accent/50"
            >
              <option value="dark">Dark</option>
              <option value="midnight">Midnight</option>
              <option value="cyber">Cyber</option>
            </select>
          </Section>

          {/* ── Autoboot ── */}
          <Section title="Startup">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={autoboot}
                onChange={(e) => handleAutobootChange(e.target.checked)}
                className="accent-jarvis-accent"
              />
              <span className="text-sm">Auto-start Jarvis on system boot</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer mt-2">
              <input
                type="checkbox"
                checked={devConsole}
                onChange={(e) => handleDevConsoleChange(e.target.checked)}
                className="accent-jarvis-accent"
              />
              <span className="text-sm">Developer Console</span>
            </label>
            <p className="text-[10px] text-jarvis-muted mt-1 ml-1">Show backend logs for debugging (requires restart)</p>
          </Section>

          {/* ── Advanced ── */}
          <Section title="Advanced">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={minimizeToTray}
                onChange={(e) => handleMinimizeToTrayChange(e.target.checked)}
                className="accent-jarvis-accent"
              />
              <span className="text-sm">Minimize to System Tray</span>
            </label>
            <p className="text-[10px] text-jarvis-muted mt-1 ml-1">Close button hides to tray instead of quitting; double-click tray icon to restore</p>
          </Section>

          {/* ── Display ── */}
          <Section title="Display">
            <label className="flex items-center gap-2 cursor-pointer mb-2">
              <input
                type="checkbox"
                checked={showChatHistory}
                onChange={(e) => handleChatHistoryToggle(e.target.checked)}
                className="accent-jarvis-accent"
              />
              <span className="text-sm">Show chat history</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={showSubtitles}
                onChange={(e) => handleSubtitlesToggle(e.target.checked)}
                className="accent-jarvis-accent"
              />
              <span className="text-sm">Show subtitles</span>
            </label>
            <p className="text-[10px] text-jarvis-muted mt-1 ml-1">Animated subtitles appear below the sphere when Jarvis speaks</p>
          </Section>

          {/* ── System Info ── */}
          {Object.keys(systemInfo).length > 0 && (
            <Section title="System Info">
              <div className="text-xs space-y-1 text-jarvis-muted">
                <p><span className="text-jarvis-text/60">Version:</span> {systemInfo.version || systemInfo.jarvis_version || '—'}</p>
                <p><span className="text-jarvis-text/60">Python:</span> {systemInfo.python_version || systemInfo.python || '—'}</p>
                <p><span className="text-jarvis-text/60">Platform:</span> {systemInfo.os || systemInfo.platform || systemInfo.os_version || '—'}</p>
                <p><span className="text-jarvis-text/60">Uptime:</span>
                  <span className="text-jarvis-accent font-mono ml-1">
                    {liveUptime > 0 ? formatUptime(liveUptime) : '—'}
                  </span>
                  <span className="text-[9px] ml-1 opacity-60">live</span>
                </p>
              </div>
            </Section>
          )}

          {/* ── Buttons ── */}
          <div className="flex gap-2 mt-6">
            <button
              onClick={handleExportConfig}
              disabled={saving}
              className="flex-1 py-2.5 rounded-lg bg-jarvis-accent/20 border border-jarvis-accent/30 hover:bg-jarvis-accent/30 text-jarvis-accent font-medium text-sm transition-all disabled:opacity-50"
            >
              {saving ? 'Exporting...' : 'Export Config'}
            </button>
            <button
              onClick={handleReset}
              className="px-4 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 text-red-400 text-sm transition-all"
            >
              Reset
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Section wrapper ──
function Section({ title, children }) {
  return (
    <div className="mb-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-jarvis-muted mb-2">{title}</h3>
      {children}
    </div>
  );
}
