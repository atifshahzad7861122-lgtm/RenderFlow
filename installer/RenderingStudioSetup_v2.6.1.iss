; =========================================================================
; Rendering Studio Engine v2 — Professional Windows Installer Script (Inno Setup)
; =========================================================================
; Version: 2.6.1 Official Release Candidate — Dual Package Updater + Auto/Manual Timeline + ZIP Ordering
; Target OS: Windows 10 / Windows 11 (64-bit)
; Packages: Frozen runtime, FFmpeg, FFprobe, Whisper Small, Web UI, Transition Pack, engine/updates
; Includes: In-App Auto-Updater, Dual Package Support, Deterministic Image Sorting, Mode Toggles

#define MyAppName "RenderFlow"
#define MyAppVersion "2.6.1"
#define MyAppPublisher "AI With Atif"
#define MyAppURL "https://renderflow.local"
#define MyAppExeName "RenderingStudio.exe"

[Setup]
; Unique AppId to prevent multi-install collisions
AppId={{9F82A4C1-4B9E-431A-9721-5082E004BA2B}
AppName={#MyAppName} by {#MyAppPublisher}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\RenderFlow by AI With Atif
DefaultGroupName={#MyAppName} by {#MyAppPublisher}
AllowNoIcons=yes
LicenseFile=..\docs\HARDWARE_RENDERING_GUIDE.md
OutputDir=..\release
OutputBaseFilename=RenderFlow-Setup-v2.6.1
Compression=lzma2/fast
SolidCompression=no
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Primary application distribution from audited candidate build
; Strictly exclude user projects and active settings to prevent accidental overwrites
Source: "..\dist\RenderingStudio_v2.6.1_candidate_v3\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "projects\*,config\settings.json,*.key,.cache\*,.tmp_uploads\*,.renderflow_instance.json,config\ai_credentials.vault,*\RenderingStudio_TransitionPack\*"

[Icons]
Name: "{autoprograms}\{#MyAppName} by {#MyAppPublisher}\{#MyAppName} · Cinematic Workstation"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName} by {#MyAppPublisher}\Hardware Diagnostics"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--diagnostics"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName} by {#MyAppPublisher}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName} by {#MyAppPublisher}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Filename: "{app}\{#MyAppExeName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Preserve user projects in {app}\projects and user configurations
Type: files; Name: "{app}\.cache\*"
Type: files; Name: "{app}\.tmp_uploads\*"
Type: dirifempty; Name: "{app}\.cache"
Type: dirifempty; Name: "{app}\.tmp_uploads"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
