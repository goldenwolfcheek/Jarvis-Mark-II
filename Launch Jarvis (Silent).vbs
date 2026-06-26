' Jarvis Mark II — Silent Launcher (Boot-Time)
' Launched by Windows Run registry key at startup.
' No console window. Logs to %TEMP%\jarvis-boot.log for troubleshooting.
' If the app doesn't appear after boot, check that log file.

Option Explicit

Dim shell, fs, currentDir, electronDir, logFile, logStream, distFile

Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")

currentDir = fs.GetParentFolderName(WScript.ScriptFullName)
electronDir = currentDir & "\electron_frontend"
logFile = shell.ExpandEnvironmentStrings("%TEMP%") & "\jarvis-boot.log"

' ── Open log file (overwrite each boot) ──
Set logStream = fs.CreateTextFile(logFile, True)

Sub Log(msg)
    logStream.WriteLine Now() & " [JARVIS] " & msg
End Sub

' ── Phase 1: Verify environment ──
Log "=== Jarvis Mark II Boot Launcher ==="
Log "Script: " & WScript.ScriptFullName
Log "Project root: " & currentDir
Log "Electron dir: " & electronDir

If Not fs.FolderExists(electronDir) Then
    Log "FATAL: electron_frontend directory not found: " & electronDir
    Log "=== Aborted ==="
    logStream.Close
    WScript.Quit 1
End If

If Not fs.FileExists(electronDir & "\package.json") Then
    Log "FATAL: package.json not found in: " & electronDir
    Log "=== Aborted ==="
    logStream.Close
    WScript.Quit 1
End If

' Check if node is available (npx needs it)
Dim nodeCheck
nodeCheck = shell.Run("cmd /c where node >nul 2>&1", 0, True)
If nodeCheck <> 0 Then
    Log "WARNING: node.exe not found in PATH. Electron may fail."
End If

shell.CurrentDirectory = electronDir
Log "Working directory: " & electronDir

' ── Phase 2: Build frontend if needed ──
distFile = electronDir & "\dist\index.html"

If fs.FileExists(distFile) Then
    Log "dist/index.html exists — skipping vite build (fast boot)"
Else
    Log "dist/index.html missing — running vite build"
    Log "Command: cmd /c npx vite build"
    Dim buildExit
    buildExit = shell.Run("cmd /c npx vite build >nul 2>&1", 0, True)
    If buildExit <> 0 Then
        Log "WARNING: vite build exit code = " & buildExit & " — continuing anyway"
    Else
        Log "vite build completed successfully"
    End If
End If

' ── Phase 3: Launch Electron ──
' Use cmd /c so .cmd/.bat files (npx.cmd) execute correctly
Log "Launching: npx electron . --jarvis-silent"
shell.Run "cmd /c npx electron . --jarvis-silent", 0, False
Log "Electron launch issued. Script exiting."
Log "=== Boot Launcher Complete ==="

logStream.Close
Set logStream = Nothing
Set shell = Nothing
Set fs = Nothing
