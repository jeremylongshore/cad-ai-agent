; Inno Setup script for cad-dxf-agent Windows installer
; Requires Inno Setup 6.x (https://jrsoftware.org/isinfo.php)
;
; Build with:
;   iscc installer/setup.iss

#define AppName "CAD DXF Agent"
#define AppVersion "0.1.0"
#define AppPublisher "Intent Solutions"
#define AppURL "https://github.com/jeremylongshore/cad-dxf-agent"
#define AppExeName "cad-dxf-agent.exe"

[Setup]
AppId={{F3A2B1C0-D4E5-4F6A-8B9C-0D1E2F3A4B5C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=cad-dxf-agent-setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc_dxf"; Description: "Associate .dxf files"; GroupDescription: "File Associations:"
Name: "fileassoc_dwg"; Description: "Associate .dwg files"; GroupDescription: "File Associations:"

[Files]
Source: "..\dist\cad-dxf-agent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; DXF file association
Root: HKA; Subkey: "Software\Classes\.dxf\OpenWithProgids"; ValueType: string; ValueName: "CADDXFAgent.dxf"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc_dxf
Root: HKA; Subkey: "Software\Classes\CADDXFAgent.dxf"; ValueType: string; ValueName: ""; ValueData: "DXF Drawing File"; Flags: uninsdeletekey; Tasks: fileassoc_dxf
Root: HKA; Subkey: "Software\Classes\CADDXFAgent.dxf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; Tasks: fileassoc_dxf
Root: HKA; Subkey: "Software\Classes\CADDXFAgent.dxf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: fileassoc_dxf

; DWG file association
Root: HKA; Subkey: "Software\Classes\.dwg\OpenWithProgids"; ValueType: string; ValueName: "CADDXFAgent.dwg"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc_dwg
Root: HKA; Subkey: "Software\Classes\CADDXFAgent.dwg"; ValueType: string; ValueName: ""; ValueData: "DWG Drawing File"; Flags: uninsdeletekey; Tasks: fileassoc_dwg
Root: HKA; Subkey: "Software\Classes\CADDXFAgent.dwg\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; Tasks: fileassoc_dwg
Root: HKA; Subkey: "Software\Classes\CADDXFAgent.dwg\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: fileassoc_dwg

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
