# Installs the freshly built DivaLoader, starts the game through Steam and prints DivaLoader.log.
# -Skip takes debug_skip parts separated by commas (patches,scores,pv,cpk,db,rom) to isolate a crash.
# Example: powershell -File dev\trygame.ps1 -Skip "scores,pv" -Wait 60
param([string]$Skip = "", [int]$Wait = 60)
$P = Split-Path -Parent $PSScriptRoot
$G = (python -c "import sys; sys.path.insert(0, r'$P'); from divamgr import paths; print(paths.find_game() or '')").Trim()
if (-not $G) { throw "No se encontró el juego" }

Get-Process DivaMegaMix -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
Start-Sleep -Seconds 2
Copy-Item "$P\loader\build\dinput8.dll" "$G\dinput8.dll" -Force
$cfg = "enabled = true`nconsole = false`nmods = `"mods`"`n"
if ($Skip) { $cfg += "debug_skip = [" + ((($Skip -split ',') | ForEach-Object { "`"$_`"" }) -join ', ') + "]`n" }
[IO.File]::WriteAllText("$G\config.toml", $cfg)
[IO.File]::WriteAllText("$G\DivaLoader.log", "")

Start-Process "steam://rungameid/1761390"
$t0 = Get-Date; $seen = $false
while (((Get-Date) - $t0).TotalSeconds -lt $Wait) {
    if (Get-Process DivaMegaMix -ErrorAction SilentlyContinue) { $seen = $true } elseif ($seen) { break }
    Start-Sleep -Seconds 2
}
$alive = [bool](Get-Process DivaMegaMix -ErrorAction SilentlyContinue)
"skip=[$Skip]  juego vivo tras $([int]((Get-Date) - $t0).TotalSeconds) s: $alive"
Get-Content "$G\DivaLoader.log" -Encoding utf8
