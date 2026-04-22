; =====================================================================
;  AutoSubtitle_Setup.iss  —  Inno Setup 6 installer
;
;  HOW TO BUILD:
;  1. pip install pyinstaller openai-whisper stable-ts torch
;  2. python build_exe.py
;     → creates  dist\AutoSubtitle\
;  3. Install Inno Setup 6: https://jrsoftware.org/isinfo.php
;  4. Open this file in Inno Setup Compiler → Ctrl+F9
;     → creates  installer_output\AutoSubtitle_Setup.exe
; =====================================================================

#define BuildDir     "dist\AutoSubtitle"
#define AppName      "AutoSubtitle"
#define AppVersion   "1.0.0"
#define AppPublisher "Kormany (EditorTarou) Robert Karoly"
#define AppExe       "AutoSubtitle.exe"

[Setup]
AppId={{D7A2F3C1-9E4B-4A6D-8C0E-2F1B5D3A7E9C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=AutoSubtitle_Setup
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardResizable=no
MinVersion=10.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
Uninstallable=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
CreateUninstallRegKey=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop shortcut"
Name: "startmenuicon"; Description: "Start Menu shortcut"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\icon.ico"; Tasks: startmenuicon
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: dirifempty; Name: "{app}"