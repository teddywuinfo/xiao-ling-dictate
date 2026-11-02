' 小聆听写 · 无窗口启动（双击这个文件即可）
Option Explicit

Dim fso, shell, baseDir, pythonw
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = baseDir

pythonw = "pythonw.exe"
On Error Resume Next
shell.Run """" & pythonw & """ """ & baseDir & "\app.py""", 0, False
If Err.Number <> 0 Then
    MsgBox "启动失败：没有找到 pythonw.exe，请先安装 Python 3.10+ 并加入 PATH。", 16, "小聆听写"
End If
