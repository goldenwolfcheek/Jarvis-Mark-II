import React from 'react';

export default function TopBar({ status, settingsOpen, onToggleSettings }) {
  const [isMaximized, setIsMaximized] = React.useState(false);

  React.useEffect(() => {
    if (window.electronAPI?.onMaximizedChanged) {
      window.electronAPI.onMaximizedChanged(setIsMaximized);
    }
  }, []);

  const handleMinimize = () => window.electronAPI?.minimize();
  const handleMaximize = () => window.electronAPI?.maximize();
  const handleClose = () => window.electronAPI?.close();

  const statusColor =
    status === 'connected' ? 'bg-jarvis-success' :
    status === 'connecting' ? 'bg-jarvis-warning' :
    'bg-jarvis-error';

  const statusText =
    status === 'connected' ? 'Connected' :
    status === 'connecting' ? 'Connecting...' :
    'Disconnected';

  return (
    <div className="title-bar fixed top-0 left-0 right-0 h-9 flex items-center z-50 bg-jarvis-bg/90 backdrop-blur-md border-b border-jarvis-border">
      {/* App title */}
      <div className="flex items-center gap-2 px-3 text-sm font-semibold tracking-wider text-jarvis-accent select-none">
        <span className="w-2 h-2 rounded-full bg-jarvis-accent shadow-[0_0_6px_rgba(0,212,255,0.6)]" />
        JARVIS Mark II
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Connection status — centered in the title bar using absolute positioning */}
      <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-1.5 text-xs text-jarvis-muted z-[60]">
        <span className={`connection-dot ${status}`} />
        <span>{statusText}</span>
      </div>

      {/* Settings gear */}
      <button
        onClick={onToggleSettings}
        className="mr-2 p-1.5 rounded-lg hover:bg-white/5 text-jarvis-muted hover:text-jarvis-text transition-colors"
        title="Settings"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      {/* Window controls */}
      <div className="flex h-full">
        <button
          onClick={handleMinimize}
          className="px-3 h-full hover:bg-white/10 transition-colors text-jarvis-muted hover:text-jarvis-text"
          title="Minimize"
        >
          <svg width="12" height="12" viewBox="0 0 12 12">
            <rect y="5" width="12" height="1.5" fill="currentColor" rx="0.75" />
          </svg>
        </button>
        <button
          onClick={handleMaximize}
          className="px-3 h-full hover:bg-white/10 transition-colors text-jarvis-muted hover:text-jarvis-text"
          title={isMaximized ? 'Restore' : 'Maximize'}
        >
          {isMaximized ? (
            <svg width="12" height="12" viewBox="0 0 12 12">
              <rect x="1" y="3" width="8" height="8" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2" />
              <rect x="3" y="1" width="8" height="8" rx="1" fill="#050810" stroke="currentColor" strokeWidth="1.2" />
            </svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 12 12">
              <rect x="1.5" y="1.5" width="9" height="9" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2" />
            </svg>
          )}
        </button>
        <button
          onClick={handleClose}
          className="px-3 h-full hover:bg-red-500/20 hover:text-red-400 transition-colors text-jarvis-muted"
          title="Close"
        >
          <svg width="12" height="12" viewBox="0 0 12 12">
            <line x1="1" y1="1" x2="11" y2="11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="11" y1="1" x2="1" y2="11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
