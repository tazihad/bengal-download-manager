; Bengal Download Manager — Inno Setup 6 Installer Script
; Packaging installer script for Bengal Download Manager on Windows
; Build with: iscc /DAppVersion="x.y.z" build/windows/config/installer.iss

#define AppName      "Bengal Download Manager"
#ifndef AppVersion
  #define AppVersion "0.2.46"
#endif
#define AppPublisher "Bengal Download Manager Team"
#define AppURL       "https://github.com/tazihad/bengal-download-manager"
#define AppExeName   "bengal-download-manager.exe"
#define BuildDir     "..\..\..\dist\bengal-download-manager"
#define IconFile     "assets\app_icon.ico"
#ifndef OutputDirOverride
  #define OutputDirOverride "..\..\..\dist\windows"
#endif
#ifndef OutputBaseFilenameOverride
  #define OutputBaseFilenameOverride "BengalSetup-" + AppVersion
#endif

[Setup]
AppId={{D3E8F4A1-2B5C-4F9A-8E7D-9876543210BD}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
; Install to %LOCALAPPDATA%\BengalDownloadManager — no UAC, no admin elevation required
DefaultDirName={localappdata}\BengalDownloadManager
DefaultGroupName=Bengal Download Manager
OutputDir={#OutputDirOverride}
OutputBaseFilename={#OutputBaseFilenameOverride}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=yes
CloseApplicationsFilter={#AppExeName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Installer

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunch";  Description: "Create a Quick Launch shortcut"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main application directory payload produced by PyInstaller (onedir)
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
