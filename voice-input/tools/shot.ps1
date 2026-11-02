param(
    [string]$OutFile = "D:\\dev\\小聆AI\\shots\\shot.png",
    [int]$ProcessId = 0,
    [int]$Pad = 0
)
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Shots {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
[Win32Shots]::SetProcessDPIAware() | Out-Null
$rect = New-Object Win32Shots+RECT
if ($ProcessId -ne 0) {
    $p = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $p) { Write-Host "process $ProcessId not found"; exit 1 }
    $hwnd = $p.MainWindowHandle
    if ($hwnd -eq [IntPtr]::Zero) { Write-Host "process $ProcessId has no window"; exit 1 }
    [Win32Shots]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
} else {
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $rect.Left = 0; $rect.Top = 0; $rect.Right = $bounds.Width; $rect.Bottom = $bounds.Height
}
$rect.Left -= $Pad; $rect.Top -= $Pad; $rect.Right += $Pad; $rect.Bottom += $Pad
$w = $rect.Right - $rect.Left
$h = $rect.Bottom - $rect.Top
if ($w -le 0 -or $h -le 0) { Write-Host "bad rect $w x $h"; exit 1 }
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bmp.Size)
$bmp.Save($OutFile, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Host "saved $OutFile ($w x $h)"
