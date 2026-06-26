const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // ── Window controls ──
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close: () => ipcRenderer.send('window:close'),
  isMaximized: () => ipcRenderer.invoke('window:isMaximized'),
  onMaximizedChanged: (callback) => {
    ipcRenderer.on('window:maximized-changed', (_event, value) => callback(value));
  },

  // ── File dialogs ──
  selectFolder: () => ipcRenderer.invoke('dialog:selectFolder'),

  // ── Auto-start / boot ──
  setAutoboot: (enabled) => ipcRenderer.send('set-autoboot', enabled),

  // ── Developer Console toggle ──
  setDevConsole: (enabled) => ipcRenderer.send('set-dev-console', enabled),

  // ── Minimize to Tray toggle ──
  setMinimizeToTray: (enabled) => ipcRenderer.send('set-minimize-to-tray', enabled),
  getTrayState: () => ipcRenderer.invoke('get-tray-state'),
});
