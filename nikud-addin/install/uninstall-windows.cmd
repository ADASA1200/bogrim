@echo off
chcp 65001 >nul
setlocal
rem הסרת "ניקוד קל" מ-Word. כדאי לשמור גיבוי של המילון לפני ההסרה.
set "DEST=%LOCALAPPDATA%\NikudKal"
set "KEY=HKCU\Software\Microsoft\Office\16.0\WEF\Developer"
reg delete "%KEY%" /v "%DEST%\manifest.xml" /f >nul 2>&1
if exist "%DEST%" rmdir /S /Q "%DEST%"
echo Nikud Kal was removed. Restart Word.
pause
