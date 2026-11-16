@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title PaperMate 打包

echo ============================================================
echo   PaperMate 打包（生成安装包 exe）
echo ============================================================
echo.

rem ---------- 1. 检查 Python ----------
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo [缺] 没找到 Python。打包机需要 Python 3.10+。
  pause & exit /b 1
)
echo [OK] Python:
%PY% -V

rem ---------- 2. 检查打包依赖 ----------
%PY% -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo [缺] 没装 PyInstaller，正在安装...
  %PY% -m pip install pyinstaller
  if errorlevel 1 ( echo 安装失败，请检查网络 & pause & exit /b 1 )
)
echo [OK] PyInstaller 已就绪

rem ---------- 3. 检查 Inno Setup ----------
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo [缺] 没找到 Inno Setup 6。
  echo       去 https://jrsoftware.org/isdl.php 下载安装后重跑本脚本。
  echo       ^(只想生成免安装版可跳过：只做第 4 步的 PyInstaller 即可^)
  pause & exit /b 1
)
echo [OK] Inno Setup: %ISCC%

rem ---------- 4. 运行环境自检，避免把坏代码打进去 ----------
echo.
echo ==^> 打包前自检
%PY% env_check.py
if errorlevel 1 (
  echo.
  echo [警告] 自检未通过。打包仍可继续（安装包内自带依赖），
  echo         但建议先修好，避免运行期出错。
)

rem ---------- 5. PyInstaller ----------
echo.
echo ==^> 构建 dist\PaperMate\（约 1 分钟）
%PY% -m PyInstaller --noconfirm --clean PaperMate.spec
if errorlevel 1 (
  echo [失败] PyInstaller 构建失败，请看上面的报错。
  pause & exit /b 1
)
echo [OK] 免安装版：dist\PaperMate\PaperMate.exe

rem ---------- 6. Inno Setup ----------
echo.
echo ==^> 生成安装包
"%ISCC%" PaperMate.iss
if errorlevel 1 (
  echo [失败] Inno Setup 编译失败，请看上面的报错。
  pause & exit /b 1
)

echo.
echo ============================================================
echo   完成
echo ============================================================
echo   免安装版：dist\PaperMate\PaperMate.exe
echo   安装包  ：dist_installer\PaperMate-Setup-*.exe
echo.
pause
