@echo off
rem Builds DivaLoader as dinput8.dll (x64, static CRT). Needs Visual Studio Build Tools with C++.
setlocal
set "VSDIR="
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" (
  for /f "usebackq delims=" %%i in (`call "%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSDIR=%%i"
)
if not defined VSDIR if exist "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set "VSDIR=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools"
if not defined VSDIR (
  echo No se encontro MSVC. Instala Visual Studio Build Tools con "Desarrollo de escritorio con C++".
  exit /b 1
)
call "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1

cd /d "%~dp0"
if not exist build mkdir build
cl /nologo /std:c++17 /O2 /MT /EHsc /W3 /utf-8 /DNDEBUG /D_CRT_SECURE_NO_WARNINGS /Fobuild\ ^
   src\Loader.cpp src\Game.cpp src\Hook.cpp src\Mods.cpp src\Patches.cpp src\Scores.cpp src\Toml.cpp src\Log.cpp ^
   /LD /Febuild\dinput8.dll /link /NOLOGO psapi.lib user32.lib || exit /b 1
echo.
echo OK: %~dp0build\dinput8.dll
