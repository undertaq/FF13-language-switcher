@echo off
start "" /wait "%~dp0FF13LanguageSwitch.exe" zh %*
exit /b %errorlevel%
