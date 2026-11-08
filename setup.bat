@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem --- Python 찾기: py 런처 > python > C:\Python
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY if exist "C:\Python\python.exe" set "PY=C:\Python\python.exe"
if not defined PY (
  echo [오류] Python 3.10 이상을 찾을 수 없습니다. https://www.python.org 에서 설치하세요.
  pause
  exit /b 1
)

echo 사용할 Python: %PY%
%PY% --version
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || goto :fail
)
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -e ".[dev]" || goto :fail
echo.
echo 설치 완료. run.bat 으로 실행하세요.
exit /b 0

:fail
echo [오류] 설치에 실패했습니다. 위 메시지를 확인하세요.
pause
exit /b 1
