@echo off
cd /d "%~dp0"
python tools\svoenrav.py start
if errorlevel 1 pause
