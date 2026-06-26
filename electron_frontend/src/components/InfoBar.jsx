import React, { useState, useRef, useEffect } from 'react';

export default function InfoBar({ provider, model, toolCount, version, groupedModels, onSelectModel, onSelectProvider, providerEnabled, providerProfiles }) {
  const [providerOpen, setProviderOpen] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const [customInput, setCustomInput] = useState(null); // provider name or null
  const [customValue, setCustomValue] = useState('');
  const inputRef = useRef(null);
  const containerRef = useRef(null);
  const providerRef = useRef(null);
  const modelRef = useRef(null);

  // Close either dropdown on outside click
  useEffect(() => {
    if (!providerOpen && !modelOpen) return;
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setProviderOpen(false);
        setModelOpen(false);
        setCustomInput(null);
        setCustomValue('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [providerOpen, modelOpen]);

  // Auto-focus custom input when it appears
  useEffect(() => {
    if (customInput && inputRef.current) {
      inputRef.current.focus();
    }
  }, [customInput]);

  // ── Derive data ──

  // Providers shown in dropdown
  // Local providers (auth_type="none"): auto-show if server is running (default-true)
  // Auth providers (auth_type="api_key"): only show if explicitly toggled ON in Settings
  const availableProviders = [];
  if (groupedModels && typeof groupedModels === 'object') {
    for (const [prov, models] of Object.entries(groupedModels)) {
      const profile = providerProfiles?.[prov];
      const isLocal = profile?.auth_type === "none";
      const enabled = isLocal
        ? (providerEnabled ? providerEnabled[prov] !== false : true)
        : (providerEnabled ? providerEnabled[prov] === true : false);
      if (enabled && Array.isArray(models) && models.length > 0) {
        availableProviders.push(prov);
      }
    }
  }
  // Sort alphabetically
  availableProviders.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));

  // Models for the current provider only
  const currentModels = [];
  if (groupedModels && typeof groupedModels === 'object' && provider) {
    const raw = groupedModels[provider];
    if (Array.isArray(raw)) {
      for (const m of raw) {
        currentModels.push(m.id || m.name || m);
      }
    }
  }
  // Sort alphabetically
  currentModels.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));

  const displayProvider = provider || '—';
  const displayModel = model || '—';

  return (
    <div id="info-bar" className="text-xs" ref={containerRef}>
      {/* Provider dropdown */}
      <div className="relative inline-block" ref={providerRef}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setProviderOpen((v) => !v);
            setModelOpen(false);
          }}
          className="hover:text-jarvis-accent transition-colors cursor-pointer bg-transparent border-none text-inherit font-inherit text-xs"
          title="Click to change provider"
        >
          <span id="info-provider">{displayProvider}</span>
          <span className="ml-1 text-jarvis-muted/50">▼</span>
        </button>

        {providerOpen && (
          <div className="absolute bottom-full left-0 mb-1 w-48 max-h-60 overflow-y-auto rounded-lg bg-jarvis-surface/95 backdrop-blur-xl border border-jarvis-border shadow-xl z-50">
            {availableProviders.length === 0 ? (
              <div className="p-3 text-xs text-jarvis-muted text-center">No providers added</div>
            ) : (
              availableProviders.map((prov) => {
                const isActive = prov === provider;
                return (
                  <button
                    key={prov}
                    onClick={() => {
                      if (prov !== provider) {
                        onSelectProvider(prov);
                      }
                      setProviderOpen(false);
                    }}
                    className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                      isActive
                        ? 'text-jarvis-accent bg-jarvis-accent/10'
                        : 'text-jarvis-text/80 hover:bg-jarvis-bg/50 hover:text-jarvis-text'
                    }`}
                  >
                    {prov}
                  </button>
                );
              })
            )}
          </div>
        )}
      </div>

      {/* Model dropdown */}
      <div className="relative inline-block" ref={modelRef}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setModelOpen((v) => !v);
            setProviderOpen(false);
          }}
          className="hover:text-jarvis-accent transition-colors cursor-pointer bg-transparent border-none text-inherit font-inherit text-xs"
          title="Click to change model"
        >
          <span id="info-model">{displayModel}</span>
          <span className="ml-1 text-jarvis-muted/50">▼</span>
        </button>

        {modelOpen && (
          <div className="absolute bottom-full left-0 mb-1 w-56 max-h-60 overflow-y-auto rounded-lg bg-jarvis-surface/95 backdrop-blur-xl border border-jarvis-border shadow-xl z-50">
            {currentModels.length === 0 && customInput !== provider ? (
              <div className="p-3 text-xs text-jarvis-muted text-center">No models available</div>
            ) : null}
            {currentModels.map((mid) => {
              const isActive = mid === model;
              return (
                <button
                  key={mid}
                  onClick={() => {
                    onSelectModel(mid, provider);
                    setModelOpen(false);
                    setCustomInput(null);
                    setCustomValue('');
                  }}
                  className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                    isActive
                      ? 'text-jarvis-accent bg-jarvis-accent/10'
                      : 'text-jarvis-text/80 hover:bg-jarvis-bg/50 hover:text-jarvis-text'
                  }`}
                >
                  {mid}
                </button>
              );
            })}
            {/* Custom model input */}
            <div className="border-t border-jarvis-border/30 mt-1 pt-1">
              {customInput === provider ? (
                <div className="px-3 pb-2 pt-1">
                  <input
                    ref={inputRef}
                    type="text"
                    value={customValue}
                    onChange={(e) => setCustomValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && customValue.trim()) {
                        onSelectModel(customValue.trim(), provider);
                        setModelOpen(false);
                        setCustomInput(null);
                        setCustomValue('');
                      }
                      if (e.key === 'Escape') {
                        setCustomInput(null);
                        setCustomValue('');
                      }
                    }}
                    placeholder="Type model name..."
                    className="w-full bg-jarvis-bg border border-jarvis-border rounded px-2 py-1 text-xs text-jarvis-text placeholder-jarvis-muted focus:border-jarvis-accent/50 outline-none"
                  />
                </div>
              ) : (
                <button
                  onClick={() => {
                    setCustomInput(provider);
                    setCustomValue('');
                  }}
                  className="w-full text-left px-3 py-1 text-[11px] text-jarvis-muted/60 hover:text-jarvis-accent hover:bg-jarvis-accent/5 transition-colors italic"
                >
                  Custom...
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Effort selector moved to chat header */}

      <span className="sep">|</span>
      <span id="info-tools">{toolCount ?? 0} tools & skills</span>
      <span className="sep">|</span>
      <span id="info-version">v{version || '0.0.0'}</span>
    </div>
  );
}
