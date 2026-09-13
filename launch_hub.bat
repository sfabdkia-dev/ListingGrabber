@echo off
if not "%~1"=="" (
    start "" pythonw "%~dp0server\hub.py" "%~1"
) else (
    start "" pythonw "%~dp0server\hub.py"
)
