# Saves a PNG of a window by its title, even when another window covers it (PrintWindow).
# Example: powershell -File dev\capture_window.ps1 -Title "Diva Manager" -Out shot.png
param([Parameter(Mandatory)][string]$Title, [Parameter(Mandatory)][string]$Out)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$h = [Win]::FindWindow([NullString]::Value, $Title)
if ($h -eq [IntPtr]::Zero) { throw "No hay ventana con titulo '$Title'" }
$r = New-Object Win+RECT
[void][Win]::GetWindowRect($h, [ref]$r)
$bmp = New-Object System.Drawing.Bitmap ($r.Right - $r.Left), ($r.Bottom - $r.Top)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[void][Win]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc)
$bmp.Save($Out)
"guardado $Out ($($bmp.Width)x$($bmp.Height))"

