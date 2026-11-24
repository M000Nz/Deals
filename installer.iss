; Inno Setup script for the Deals installer. Built by the GitHub workflow:  iscc /DAppVersion=25 installer.iss
#ifndef AppVersion
  #define AppVersion "0"
#endif

[Setup]
; Never change AppId - it's how Windows recognises "the same app" when updating.
AppId={{6F1D3E52-8B7A-4C2E-9A41-D3A15E0B7C90}
AppName=Deals
AppVersion={#AppVersion}
AppPublisher=M000Nz
AppPublisherURL=https://github.com/M000Nz/Deals
DefaultDirName={autopf}\Deals
DefaultGroupName=Deals
DisableProgramGroupPage=yes
; Per-user install: no admin prompt, and the app can update itself without one.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=Deals-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\deals.ico
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=Deals
UninstallDisplayIcon={app}\Deals.exe
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Files]
Source: "dist\Deals\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Deals"; Filename: "{app}\Deals.exe"; IconFilename: "{app}\Deals.exe"
Name: "{autodesktop}\Deals"; Filename: "{app}\Deals.exe"; Tasks: desktopicon
Name: "{autoprograms}\Deals (classic window)"; Filename: "{app}\Deals.exe"; Parameters: "--classic"; IconFilename: "{app}\Deals.exe"

[Run]
; Runs after a normal install (ticked checkbox) and after a silent self-update (starts the new version automatically).
Filename: "{app}\Deals.exe"; Description: "Start Deals"; Flags: nowait postinstall

; Your watchlist and settings live in %APPDATA%\Deals and are deliberately NOT removed on uninstall.
