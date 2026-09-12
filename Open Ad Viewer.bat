@echo off
setlocal

REM If a folder path is dragged onto this bat, open that project directly.
if not "%~1"=="" (
    pythonw "%~dp0ad_viewer.py" "%~1"
    exit /b
)

REM No argument — launch the viewer (auto-loads the last active project).
pythonw "%~dp0ad_viewer.py"
