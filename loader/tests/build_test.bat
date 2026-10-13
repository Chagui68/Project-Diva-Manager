@echo off
setlocal
set "VSDIR=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools"
call "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
cd /d "%~dp0"
if not exist ..\build\test mkdir ..\build\test
cl /nologo /std:c++17 /O2 /MT /EHsc /utf-8 /D_CRT_SECURE_NO_WARNINGS /Fo..\build\test\ selftest.cpp ..\src\Hook.cpp ..\src\Toml.cpp ..\src\Log.cpp ^
   /Fe..\build\test\selftest.exe /link /NOLOGO psapi.lib user32.lib || exit /b 1
..\build\test\selftest.exe
