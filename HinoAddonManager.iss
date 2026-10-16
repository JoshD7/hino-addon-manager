#define AppName "Hino Addon Manager"
#define AppVersion "4.1.1"
[Setup]
AppId={{C7BD2612-32C6-4DFE-9DF8-FA49E4C0762A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Hino Addon Manager
DefaultDirName={localappdata}\Programs\Hino Addon Manager
DefaultGroupName=Hino Addon Manager
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=HinoAddonManager-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\HinoAddonManager.exe
CloseApplications=yes
RestartApplications=no
WizardStyle=modern
[Files]
Source: "dist\HinoAddonManager.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "HinoUpdateHelper.ps1"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{autoprograms}\Hino Addon Manager"; Filename: "{app}\HinoAddonManager.exe"
Name: "{autodesktop}\Hino Addon Manager"; Filename: "{app}\HinoAddonManager.exe"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{app}\HinoAddonManager.exe"; Description: "Launch Hino Addon Manager"; Flags: nowait postinstall skipifsilent
