@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PaperMate

echo ============================================================
echo   PaperMate 启动
echo ============================================================
echo.

rem ---------- 1. 找 Python（优先 py -3，再 python） ----------
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY=python"
  )
)
if not defined PY goto nopython

rem ---------- 2. 版本必须 3.10+ ----------
%PY% -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)"
if errorlevel 1 goto oldpython

rem ---------- 3. 环境自检 + 缺依赖自动安装 ----------
%PY% env_check.py --install
if errorlevel 1 goto notready

rem ---------- 4. 启动（浏览器会自动打开） ----------
echo.
echo 启动中；停止服务请按 Ctrl+C，或直接关闭本窗口。
echo.
%PY% server.py
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo [错误] 服务异常退出（代码 %RC%）。请把上面的报错内容截图或复制出来。
) else (
  echo 服务已停止。
)
pause
exit /b %RC%

:nopython
echo [缺] 没有找到可用的 Python。
echo.
echo   1) 打开 https://www.python.org/downloads/ 下载 Python 3.10 或更高版本
echo   2) 安装时务必勾选 "Add python.exe to PATH"
echo   3) 装完重启这个窗口（或重启电脑），再双击 start.bat
echo.
echo   如果已经装过 Python 仍看到这一行，多半是装的时候没勾 PATH；
echo   重装一次并勾上即可，不必先卸载。
echo.
pause
exit /b 1

:oldpython
echo [缺] Python 版本太低：
%PY% -V
echo.
echo   PaperMate 需要 3.10 或更高版本。
echo   请到 https://www.python.org/downloads/ 装新版，装完再双击本文件。
echo.
pause
exit /b 1

:notready
echo.
echo 上面的 [缺] 项还没解决，先把它们补上再启动。
echo 提示：
echo   - 依赖装不上：多半是网络，试试
echo     %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo   - 数据目录不可写：把整个文件夹解压到桌面或「文档」，不要放在
echo     Program Files、只读盘，也不要直接双击压缩包里的文件。
echo.
pause
exit /b 1
