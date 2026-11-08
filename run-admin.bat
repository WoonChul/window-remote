@echo off
rem 관리자 권한으로 실행된 프로그램을 제어할 때 사용
cd /d "%~dp0"
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0run.bat' -Verb RunAs"
