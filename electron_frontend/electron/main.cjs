const { app, BrowserWindow, ipcMain, dialog, session, Tray, Menu, nativeImage } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const { ICON_BASE64 } = require('./tray_icon.cjs');

// ── Globals ──────────────────────────────────────────────────────────────────
let mainWindow = null;
let backendProcess = null;
let tray = null;
let devConsoleEnabled = true;        // default ON — show backend CMD window
let minimizeToTrayEnabled = false;   // OFF by default
let isQuitting = false;              // tracks app quit vs. hide-to-tray
let isAutoStart = false;             // true when launched by boot VBS

// Paths
const distIndex = path.join(__dirname, '..', 'dist', 'index.html');
const isDev = !app.isPackaged && !fs.existsSync(distIndex);

// Detect if launched in silent (auto-start) mode — VBS passes --jarvis-silent
if (process.argv.includes('--jarvis-silent')) {
  isAutoStart = true;
  devConsoleEnabled = false;         // no console window on boot
}

const DEV_VITE_PORT = 5173;
const BACKEND_PORT = 11711;

// ── Persisted settings (read at startup before frontend loads) ──────────────

function getSettingsPath() {
  const userData = app.getPath('userData');
  return path.join(userData, 'electron-settings.json');
}

function readPersistedSettings() {
  try {
    const data = fs.readFileSync(getSettingsPath(), 'utf-8');
    return JSON.parse(data);
  } catch {
    return {};
  }
}

function writePersistedSettings(updates) {
  try {
    const current = readPersistedSettings();
    const merged = { ...current, ...updates };
    const dir = path.dirname(getSettingsPath());
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(getSettingsPath(), JSON.stringify(merged, null, 2), 'utf-8');
  } catch (e) {
    console.error('[JARVIS] Failed to persist setting:', e.message);
  }
}

// ── Backend Lifecycle ────────────────────────────────────────────────────────

function killProcessTree(pid) {
  try {
    spawn('taskkill', ['/F', '/T', '/PID', String(pid)], { stdio: 'ignore' });
  } catch (e) {
    // best-effort
  }
}

function startBackend() {
  if (backendProcess) return;

  // Read persisted dev console setting BEFORE spawning backend
  const persisted = readPersistedSettings();
  devConsoleEnabled = persisted.devConsole !== false; // default ON

  // Auto-start mode overrides — always silent on boot
  if (isAutoStart) {
    devConsoleEnabled = false;
  }

  const scriptPath = path.join(__dirname, '..', '..', 'run.py');
  const venvPython = path.join(__dirname, '..', '..', 'venv', 'Scripts', 'python.exe');

  if (devConsoleEnabled) {
    // ── Visible console window ──
    // On Windows, when a GUI app (Electron) spawns a console app (Python),
    // the console does NOT reliably appear with just windowsHide: false
    // because piped stdio interferes.  We route through cmd.exe /c start
    // which explicitly creates a NEW console window (CREATE_NEW_CONSOLE).
    // Build the command line as a single verbatim string for cmd.exe /c:
    //   start "Jarvis Backend" /wait "python.exe" "run.py" --server --port 11711
    const cmdLine =
      `start "Jarvis Backend" /wait "${venvPython}" "${scriptPath}" --server --port ${BACKEND_PORT}`;
    backendProcess = spawn('cmd.exe', ['/c', cmdLine], {
      cwd: path.join(__dirname, '..', '..'),
      windowsHide: true,           // hide the outer cmd.exe wrapper
      stdio: 'ignore',             // no piping — output goes to the new window
      windowsVerbatimArguments: true,  // pass the command line verbatim to cmd.exe
    });
  } else {
    // ── No console — quiet background process ──
    backendProcess = spawn(venvPython, [scriptPath, '--server', '--port', String(BACKEND_PORT)], {
      cwd: path.join(__dirname, '..', '..'),
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });

    backendProcess.stdout.on('data', (data) => {
      console.log(`[backend] ${data.toString().trim()}`);
    });
    backendProcess.stderr.on('data', (data) => {
      console.error(`[backend] ${data.toString().trim()}`);
    });
  }

  backendProcess.on('exit', (code) => {
    console.log(`[backend] exited with code ${code}`);
    backendProcess = null;
  });
}

function stopBackend() {
  if (backendProcess) {
    const pid = backendProcess.pid;
    backendProcess = null;
    killProcessTree(pid);
  }
}

// ── Tray ─────────────────────────────────────────────────────────────────────

function createTray() {
  if (tray) return;

  const icon = nativeImage.createFromBuffer(Buffer.from(ICON_BASE64, 'base64'));
  tray = new Tray(icon);
  tray.setToolTip('Jarvis Mark II');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Jarvis',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      },
    },
    {
      label: 'Hide to Tray',
      click: () => {
        if (mainWindow) mainWindow.hide();
      },
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);

  tray.on('double-click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.focus();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    }
  });
}

function destroyTray() {
  if (tray) {
    tray.destroy();
    tray = null;
  }
}

// ── Window Controls (IPC) ────────────────────────────────────────────────────

ipcMain.on('window:minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window:maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) mainWindow.unmaximize();
    else mainWindow.maximize();
  }
});

ipcMain.on('window:close', () => {
  if (mainWindow) {
    if (minimizeToTrayEnabled) {
      mainWindow.hide();
    } else {
      mainWindow.close();
    }
  }
});

ipcMain.handle('window:isMaximized', () => {
  return mainWindow ? mainWindow.isMaximized() : false;
});

// ── Settings IPC ─────────────────────────────────────────────────────────────

ipcMain.on('set-autoboot', (_event, enabled) => {
  const { spawn } = require('child_process');
  const regPath = path.join(process.env.windir || 'C:\\Windows', 'System32', 'reg.exe');

  if (enabled) {
    // Point auto-start to the VBS silent launcher so no console window appears.
    // Use spawn() with argument array instead of exec() — this avoids cmd.exe shell
    // parsing bugs with \" inside quoted /d values. Node.js builds the command line
    // following CommandLineToArgvW conventions, which reg.exe understands correctly.
    const vbsPath = path.join(__dirname, '..', '..', 'Launch Jarvis (Silent).vbs');
    const commandValue = `wscript.exe "${vbsPath}"`;

    spawn(regPath, [
      'add',
      'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
      '/v', 'JarvisMarkII',
      '/t', 'REG_SZ',
      '/d', commandValue,
      '/f'
    ], { stdio: 'ignore' });
  } else {
    // Remove the auto-start registry entry
    spawn(regPath, [
      'delete',
      'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
      '/v', 'JarvisMarkII',
      '/f'
    ], { stdio: 'ignore' });
  }
});

ipcMain.on('set-dev-console', (_event, enabled) => {
  devConsoleEnabled = Boolean(enabled);
  writePersistedSettings({ devConsole: Boolean(enabled) });
});

ipcMain.on('set-minimize-to-tray', (_event, enabled) => {
  minimizeToTrayEnabled = Boolean(enabled);
  if (minimizeToTrayEnabled) {
    createTray();
  } else {
    destroyTray();
  }
});

ipcMain.handle('get-tray-state', () => {
  return { minimizeToTrayEnabled, hasTray: !!tray };
});

// ── File Dialogs ─────────────────────────────────────────────────────────────

ipcMain.handle('dialog:selectFolder', async () => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Select Skill Folder',
  });
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0];
});

// ── Wait for backend to be ready ─────────────────────────────────────────────

function waitForBackend(retries = 60, delay = 500) {
  return new Promise((resolve, reject) => {
    function poll(attemptsLeft) {
      const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/health`, (res) => {
        if (res.statusCode === 200) resolve();
        else if (attemptsLeft > 0) setTimeout(() => poll(attemptsLeft - 1), delay);
        else reject(new Error('Backend not ready after max retries'));
      });
      req.on('error', () => {
        if (attemptsLeft > 0) setTimeout(() => poll(attemptsLeft - 1), delay);
        else reject(new Error('Backend connection refused'));
      });
      req.end();
    }
    poll(retries);
  });
}

// ── Create Window ────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    frame: false,
    backgroundColor: '#050810',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  // ── Allow microphone for SpeechRecognition API ──
  mainWindow.webContents.session.setPermissionRequestHandler((webContents, permission, callback) => {
    const allowed = ['media', 'mediaKeySystem', 'clipboard-write'];
    callback(allowed.includes(permission));
  });

  // Show window when ready
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Track maximize state
  mainWindow.on('maximize', () => {
    mainWindow.webContents.send('window:maximized-changed', true);
  });
  mainWindow.on('unmaximize', () => {
    mainWindow.webContents.send('window:maximized-changed', false);
  });

  // Intercept close: minimize to tray instead
  mainWindow.on('close', (event) => {
    if (minimizeToTrayEnabled && !isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  // Clean up when actually closed
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Load the app
  if (isDev) {
    mainWindow.loadURL(`http://localhost:${DEV_VITE_PORT}`);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    waitForBackend()
      .then(() => mainWindow.loadURL(`http://127.0.0.1:${BACKEND_PORT}/`))
      .catch((err) => {
        console.error('[JARVIS] Backend failed to start:', err.message);
        mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
      });
  }
}

// ── GPU Resilience ───────────────────────────────────────────────────────────

app.commandLine.appendSwitch('disable-gpu-process-crash-limiter');
app.commandLine.appendSwitch('ignore-gpu-blocklist');

// ── App Lifecycle ────────────────────────────────────────────────────────────

app.whenReady().then(() => {
  startBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
});

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  isQuitting = true;
  stopBackend();
  destroyTray();
});
