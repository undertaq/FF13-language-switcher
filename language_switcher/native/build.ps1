$ErrorActionPreference = 'Stop'
$vs = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'MSVC is required for building only.' }
$vc = (Get-ChildItem -LiteralPath "$vs\VC\Tools\MSVC" -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkVersion = (Get-ChildItem -LiteralPath "${env:ProgramFiles(x86)}\Windows Kits\10\Lib" -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$sdk = "${env:ProgramFiles(x86)}\Windows Kits\10"
$env:PATH = "$sdk\bin\$sdkVersion\x64;$env:PATH"
$source = Join-Path $PSScriptRoot 'language_switcher.c'
$object = Join-Path $PSScriptRoot 'language_switcher.obj'
$output = Join-Path (Split-Path $PSScriptRoot -Parent) 'FF13LanguageSwitch.exe'
& "$vc\bin\Hostx64\x64\cl.exe" /nologo /c /O1 /Os /GS- /Zl /Gy /Gw /utf-8 /W4 /Oi "/I$vc\include" "/I$sdk\Include\$sdkVersion\um" "/I$sdk\Include\$sdkVersion\shared" "/I$sdk\Include\$sdkVersion\ucrt" "/Fo$object" $source
if ($LASTEXITCODE) { throw 'Compile failed.' }
& "$vc\bin\Hostx64\x64\link.exe" /nologo /NODEFAULTLIB /ENTRY:entry /SUBSYSTEM:WINDOWS /OPT:REF /OPT:ICF /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT /HIGHENTROPYVA /MANIFEST:EMBED "/MANIFESTUAC:level='asInvoker' uiAccess='false'" "/LIBPATH:$sdk\Lib\$sdkVersion\um\x64" "/OUT:$output" $object kernel32.lib user32.lib advapi32.lib shell32.lib
if ($LASTEXITCODE) { throw 'Link failed.' }
Get-Item -LiteralPath $output | Select-Object FullName,Length
