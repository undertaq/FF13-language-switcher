@echo off
start "" /wait "%~dp0FF13LanguageSwitch.exe" en %*
exit /b %errorlevel%
