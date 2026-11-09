@echo off
chcp 65001 >nul
setlocal
rem התקנת "ניקוד קל" ל-Word בווינדוס: מעתיק את המניפסט ורושם אותו ב-Word.
set "DEST=%LOCALAPPDATA%\NikudKal"
set "KEY=HKCU\Software\Microsoft\Office\16.0\WEF\Developer"

tasklist /FI "IMAGENAME eq WINWORD.EXE" 2>nul | find /I "WINWORD.EXE" >nul
if not errorlevel 1 (
  echo Word is open. Please close Word, then press any key.
  pause >nul
)

if not exist "%DEST%" mkdir "%DEST%"
copy /Y "%~dp0manifest.xml" "%DEST%\manifest.xml" >nul || goto :fail
reg add "%KEY%" /v "%DEST%\manifest.xml" /t REG_SZ /d "%DEST%\manifest.xml" /f >nul || goto :fail

echo.
echo Nikud Kal was installed.
echo Open Word: the "ניקוד קל" tab will appear on the ribbon.
echo.
pause
exit /b 0

:fail
echo.
echo Installation failed.
pause
exit /b 1
