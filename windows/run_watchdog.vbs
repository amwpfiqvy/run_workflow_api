Option Explicit
Dim fso, sh, dir, python, script
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
python = dir & "\.venv\Scripts\python.exe"
script = dir & "\run_watchdog.py"
If Not fso.FileExists(python) Then
  WScript.Quit 2
End If
If Not fso.FileExists(script) Then
  WScript.Quit 3
End If
sh.CurrentDirectory = dir
sh.Run """" & python & """ """ & script & """", 0, True
