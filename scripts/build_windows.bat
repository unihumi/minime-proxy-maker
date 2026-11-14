@echo off
setlocal
rem Baut "Proxy Maker <Version>.exe" mit der neuesten FFmpeg-Version und - falls
rem das Blackmagic RAW SDK installiert ist - mit BRAW-Unterstuetzung.
rem Ergebnis: dist\Proxy Maker <Version>.exe (Version aus src\proxymaker\__init__.py)
rem Always work from the repository root (this script lives in scripts\)
cd /d "%~dp0.."

set FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip

rem FFmpeg wird nur geladen, wenn es noch nicht da ist.
rem Aktualisieren: Ordner "ffbin" loeschen oder  scripts\build_windows.bat update
if /i "%~1"=="update" if exist ffbin rmdir /s /q ffbin
if exist build_tmp rmdir /s /q build_tmp
if exist brawlib rmdir /s /q brawlib
mkdir build_tmp
if exist ffbin\ffmpeg.exe (
  echo == FFmpeg bereits vorhanden, kein Download ==
  goto :ffmpeg_ready
)
echo == Lade aktuelle FFmpeg-Version (Windows x64) ==
if not exist ffbin mkdir ffbin
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue';" ^
  "Invoke-WebRequest -Uri '%FFMPEG_URL%' -OutFile 'build_tmp\ffmpeg.zip';" ^
  "Expand-Archive -Path 'build_tmp\ffmpeg.zip' -DestinationPath 'build_tmp' -Force;" ^
  "$f = Get-ChildItem 'build_tmp' -Recurse -Filter ffmpeg.exe | Select-Object -First 1;" ^
  "if (-not $f) { throw 'ffmpeg.exe nicht im Download gefunden' };" ^
  "Copy-Item $f.FullName 'ffbin\ffmpeg.exe'" || goto :error
:ffmpeg_ready
for /f "delims=" %%v in ('ffbin\ffmpeg.exe -hide_banner -version ^| findstr /b "ffmpeg version"') do echo Eingebaut: %%v

echo == Blackmagic RAW (optional) ==
set "BRAW_SDK="
set "BRAW_ARG="
call :find_sdk "%cd%\braw_sdk\Win"
call :find_sdk "%cd%\braw_sdk"
call :find_sdk "%ProgramFiles(x86)%\Blackmagic Design\Blackmagic RAW\Blackmagic RAW SDK\Win"
call :find_sdk "%ProgramFiles%\Blackmagic Design\Blackmagic RAW\Blackmagic RAW SDK\Win"
if not defined BRAW_SDK goto :no_sdk
echo SDK gefunden: %BRAW_SDK%
call :build_braw || goto :error
set "BRAW_ARG=--add-data brawlib;brawlib"
echo BRAW-Unterstuetzung wird eingebaut.
goto :python

:no_sdk
echo Kein Blackmagic RAW SDK gefunden - App wird OHNE BRAW gebaut.
echo Gesucht in: braw_sdk\ und "Blackmagic Design\Blackmagic RAW\Blackmagic RAW SDK\Win"

:python
echo == Python-Umgebung ==
py -3 -m venv .venv-build || goto :error
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller pillow || goto :error

rem Versionsnummer gehoert in den Dateinamen, z.B. "Proxy Maker 1.0.2.exe"
set "VER="
for /f "delims=" %%v in ('python -c "import sys; sys.path.insert(0, 'src'); from proxymaker import __version__; print(__version__)"') do set "VER=%%v"
if not defined VER goto :error
set "APPNAME=Proxy Maker %VER%"
echo Version: %VER%

set ICON=
if exist assets\icon.png set ICON=--icon=assets\icon.png

echo == Baue App ==
pyinstaller --noconfirm --clean --windowed --onefile ^
  --name "%APPNAME%" ^
  --add-data "assets;assets" ^
  --add-binary "ffbin\ffmpeg.exe;ffbin" ^
  %BRAW_ARG% ^
  --paths src ^
  %ICON% ^
  src\proxymaker\__main__.py || goto :error

rmdir /s /q build_tmp
echo.
if defined BRAW_SDK (echo BRAW: eingebaut) else (echo BRAW: NICHT eingebaut)
echo Fertig: %cd%\dist\%APPNAME%.exe
if not defined CI (
  explorer dist
  pause
)
exit /b 0


rem ------------------------------------------------------------------
:find_sdk
rem Unter Windows liegt die Schnittstelle als .idl vor, sonst als .h
if defined BRAW_SDK exit /b 0
if exist "%~1\Include\BlackmagicRawAPI.idl" set "BRAW_SDK=%~1"
if exist "%~1\Include\BlackmagicRawAPI.h" set "BRAW_SDK=%~1"
exit /b 0


rem ------------------------------------------------------------------
:build_braw
rem C++-Compiler (Visual Studio Build Tools) suchen und Umgebung laden
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" goto :no_compiler
set "VSPATH="
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSPATH=%%i"
if not defined VSPATH goto :no_compiler
call "%VSPATH%\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1

mkdir brawlib
xcopy /e /i /q /y "%BRAW_SDK%\Libraries" brawlib >nul || exit /b 1

set "GEN=%cd%\build_tmp\bgen"
mkdir "%GEN%"
set "IDL=%BRAW_SDK%\Include\BlackmagicRawAPI.idl"
set "IIDC=%BRAW_SDK%\Include\BlackmagicRawAPI_i.c"
set "IIDS="

rem .idl -> Header + IID-Definitionen (MIDL gehoert zu den Build Tools)
if exist "%IDL%" echo Erzeuge Header aus BlackmagicRawAPI.idl ...
if exist "%IDL%" midl /nologo /env x64 /h BlackmagicRawAPI.h /iid BlackmagicRawAPI_i.c /out "%GEN%" "%IDL%"
if exist "%IDL%" if not exist "%GEN%\BlackmagicRawAPI.h" exit /b 1
if exist "%GEN%\BlackmagicRawAPI_i.c" set "IIDS=%GEN%\BlackmagicRawAPI_i.c"

rem IID-Definitionen aus dem SDK, falls MIDL keine erzeugt hat
if not defined IIDS if exist "%IIDC%" copy /y "%IIDC%" build_tmp\ >nul
if not defined IIDS if exist "%IIDC%" set "IIDS=build_tmp\BlackmagicRawAPI_i.c"
set "QIIDS="
if defined IIDS set QIIDS="%IIDS%"
echo Kompiliere brawpipe.exe ...
cl /nologo /EHsc /O2 /std:c++17 /utf-8 /I "%GEN%" /I "%BRAW_SDK%\Include" native\brawpipe\brawpipe.cpp %QIIDS% ole32.lib oleaut32.lib uuid.lib /Fo"build_tmp\\" /Fe"brawlib\brawpipe.exe" || exit /b 1
exit /b 0

:no_compiler
echo.
echo Fuer BRAW werden die kostenlosen "Visual Studio Build Tools" benoetigt
echo (Workload "Desktopentwicklung mit C++"):
echo   https://visualstudio.microsoft.com/de/visual-cpp-build-tools/
echo Danach den Build erneut starten.
exit /b 1

:error
echo.
echo Build fehlgeschlagen - siehe Meldungen oben.
if not defined CI pause
exit /b 1
