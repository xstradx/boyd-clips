# DPI-aware capture + real input. Supersedes ui.ps1's ClickShot, which omitted
# the virtual-screen origin (harmless at origin 0,0, wrong on a shifted desktop).
$src = @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class U2 {
  [DllImport("shcore.dll")] public static extern int SetProcessDpiAwareness(int v);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, int dx, int dy, uint d, IntPtr e);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  public struct RECT { public int Left, Top, Right, Bottom; }
  public static IntPtr Find(string needle) {
    IntPtr found = IntPtr.Zero;
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      if (!IsWindowVisible(h)) return true;
      var t = new StringBuilder(512); GetWindowText(h,t,512);
      if (t.ToString().Contains(needle)) { found = h; return false; }
      return true;
    }, IntPtr.Zero);
    return found;
  }
  public static string Title(IntPtr h) {
    var t = new StringBuilder(512); GetWindowText(h,t,512); return t.ToString();
  }
  public static string Fg() { return Title(GetForegroundWindow()); }
  public static void Click(int x, int y) {
    SetCursorPos(x, y);
    System.Threading.Thread.Sleep(180);
    mouse_event(0x0002, 0, 0, 0, IntPtr.Zero);
    System.Threading.Thread.Sleep(80);
    mouse_event(0x0004, 0, 0, 0, IntPtr.Zero);
  }
}
'@
if (-not ("U2" -as [type])) { Add-Type -TypeDefinition $src }
try { [U2]::SetProcessDpiAwareness(2) | Out-Null } catch {}
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

# Capture an explicit screen rect at native pixels, downscaled to $MaxW for reading.
# Returns the factor to multiply shot coords by, and the rect origin to add.
function ShotRect($X, $Y, $W, $H, $Path, $MaxW = 1600) {
  $bmp = New-Object System.Drawing.Bitmap $W, $H
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($X, $Y, 0, 0, $bmp.Size); $g.Dispose()
  $scale = [Math]::Min(1.0, $MaxW / $W)
  $w2 = [int]($W * $scale); $h2 = [int]($H * $scale)
  $small = New-Object System.Drawing.Bitmap $w2, $h2
  $g2 = [System.Drawing.Graphics]::FromImage($small)
  $g2.InterpolationMode = 'HighQualityBicubic'
  $g2.DrawImage($bmp, 0, 0, $w2, $h2); $g2.Dispose()
  $small.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose(); $small.Dispose()
  $global:ShotX = $X; $global:ShotY = $Y; $global:ShotF = 1.0 / $scale
  "rect ${X},${Y} ${W}x${H} -> $Path   real = ($X + sx*$([Math]::Round($global:ShotF,4)), $Y + sy*$([Math]::Round($global:ShotF,4)))"
}

# Click using coordinates read off the last ShotRect image.
function ClickAt($sx, $sy) {
  $x = [int]($global:ShotX + $sx * $global:ShotF)
  $y = [int]($global:ShotY + $sy * $global:ShotF)
  [U2]::Click($x, $y)
  "clicked screen ($x,$y)"
}

function Focus($needle) {
  $h = [U2]::Find($needle)
  if ($h -eq [IntPtr]::Zero) { return "NOT FOUND: $needle" }
  [U2]::ShowWindow($h, 9) | Out-Null
  [U2]::SetForegroundWindow($h) | Out-Null
  Start-Sleep -Milliseconds 700
  $r = New-Object U2+RECT
  [U2]::GetWindowRect($h, [ref]$r) | Out-Null
  $global:WinRect = $r
  "focused '$([U2]::Title($h))'  rect $($r.Left),$($r.Top) -> $($r.Right),$($r.Bottom)"
}
