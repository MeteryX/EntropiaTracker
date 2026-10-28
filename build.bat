@echo off
title Entropia Tracker - Build
echo ========================================
echo   Entropia Tracker - Desktop EXE
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden.
    pause
    exit /b 1
)

echo Installiere Abhängigkeiten...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo.
echo Erstelle EXE...
pyinstaller --clean --noconfirm EntropiaTracker.spec

REM Datenbank in den dist-Ordner kopieren, falls vorhanden
if exist "entropia_tracker.db" (
    echo Kopiere Datenbank in dist...
    copy /Y entropia_tracker.db dist\entropia_tracker.db >nul
)

echo.
if exist "dist\EntropiaTracker.exe" (
    echo ERFOLG: dist\EntropiaTracker.exe
) else (
    echo FEHLER beim Erstellen.
)
pause
