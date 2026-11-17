@echo off
start "" /wait "%~dp0FF13LanguageSwitch.exe" status %*
exit /b %errorlevel%
