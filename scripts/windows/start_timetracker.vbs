' start_timetracker.vbs
' Launch: venv\Scripts\pythonw.exe -m timetracker start
' Place this file in scripts\windows\. It will auto-detect the project root.

Option Explicit

Dim fso, shell, scriptFull, scriptDir, projectDir, tryDir
Dim pyExe, venvScripts, cmd, i, envProc

Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptFull = WScript.ScriptFullName
scriptDir  = fso.GetParentFolderName(scriptFull)

' Try to locate the project root by walking up until we find venv\Scripts
projectDir = ""
tryDir = scriptDir
For i = 0 To 3
  If fso.FolderExists(fso.BuildPath(tryDir, "venv\Scripts")) Then
    projectDir = tryDir
    Exit For
  End If
  If fso.GetParentFolderName(tryDir) = "" Then Exit For
  tryDir = fso.GetParentFolderName(tryDir)
Next

If projectDir = "" Then
  MsgBox "Could not locate project root (folder containing venv\Scripts)." & vbCrLf & _
         "Starting from: " & scriptDir, vbCritical, "TimeTracker"
  WScript.Quit 1
End If

' Resolve Python executable from the venv
venvScripts = fso.BuildPath(projectDir, "venv\Scripts")
pyExe = fso.BuildPath(venvScripts, "python.exe")

If Not fso.FileExists(pyExe) Then
  MsgBox "Could not find venv\Scripts\python.exe in:" & vbCrLf & projectDir, _
         vbCritical, "TimeTracker"
  WScript.Quit 1
End If

' Mimic an activated venv: prepend venv\Scripts to PATH
Set envProc = shell.Environment("PROCESS")
envProc("PATH") = venvScripts & ";" & envProc("PATH")

' Ensure the module path resolves (src layout)
envProc("PYTHONPATH") = fso.BuildPath(projectDir, "src")

' Set working directory to the project root (important for DB/log files)
shell.CurrentDirectory = projectDir

' Run hidden, do not wait (equivalent to: python -m timetracker start)
cmd = "cmd /c ""python -m timetracker start"""
shell.Run cmd, 0, False
