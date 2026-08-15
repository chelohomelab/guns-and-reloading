; Inno Setup script for the Guns & Reloading desktop installer.
;
; Input: the PyInstaller onedir build at dist\InventoryAndReloading (see ..\inventory.spec) —
; must exist before this script is compiled. Built by .github/workflows/build-desktop.yml via:
;   iscc desktop\windows\installer.iss /DMyAppVersion=1.24
; Compiling directly with the placeholder version below still works for local testing.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "Guns & Reloading"
#define MyAppPublisher "chelohomelab"
#define MyAppExeName "InventoryAndReloading.exe"
#define MyAppURL "https://github.com/chelohomelab/guns-and-reloading"
; Fixed GUID so upgrades/uninstalls recognize the same product across versions — do not change.
#define MyAppId "{B3B1B487-6C1E-4F0E-9C7A-6B2F6D1D9C2E}"

[Setup]
AppId={{#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist\installer
OutputBaseFilename=GunsAndReloading-Setup-{#MyAppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\InventoryAndReloading\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Downloaded by the CI build step just before compiling (see build-desktop.yml) — kept out of git
; since it's a large external binary Microsoft updates independently. "dontcopy" means it's
; embedded in the installer but only extracted to a temp dir if actually run, below.
Source: "MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; Flags: dontcopy skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; pywebview needs the WebView2 runtime on Windows. It ships with Windows 11 and most up-to-date
; Windows 10 installs already, so this only triggers on older/stripped-down machines.
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2 Runtime..."; Check: not IsWebView2RuntimeInstalled; Flags: waituntilterminated skipifdoesntexist
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function IsWebView2RuntimeInstalled: Boolean;
const
  ClientKey = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  ClientKeyWow6432 = 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
var
  Version: String;
begin
  // The evergreen WebView2 runtime registers under one of these three locations depending on
  // whether it was installed machine-wide (32- or 64-bit registry view) or per-user.
  Result :=
    RegQueryStringValue(HKLM, ClientKeyWow6432, 'pv', Version)
    or RegQueryStringValue(HKLM, ClientKey, 'pv', Version)
    or RegQueryStringValue(HKCU, ClientKey, 'pv', Version);
end;
