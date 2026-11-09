#define Ver GetEnv("VER")

[Setup]
AppId={{8E3B0C9A-5F21-4C7B-9D3E-2A6F1B7C4D55}
AppName=Synth Set Manager
AppVersion={#Ver}
AppPublisher=Razvan
DefaultDirName={localappdata}\Programs\Synth Set Manager
DefaultGroupName=Synth Set Manager
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=out
OutputBaseFilename=SynthSetManager-Setup
Compression=lzma2
SolidCompression=yes
CloseApplications=force
UninstallDisplayName=Synth Set Manager

[Files]
Source: "dist\SynthSetManager\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autodesktop}\Synth Set Manager"; Filename: "{app}\SynthSetManager.exe"
Name: "{autoprograms}\Synth Set Manager"; Filename: "{app}\SynthSetManager.exe"

[Run]
Filename: "{app}\SynthSetManager.exe"; Description: "Pornește Synth Set Manager"; Flags: nowait postinstall skipifsilent
Filename: "{app}\SynthSetManager.exe"; Parameters: "--actualizat"; Flags: nowait; Check: EAutoUpdate

[Code]
function EAutoUpdate: Boolean;
begin
  Result := Pos('/AUTOUPDATE', Uppercase(GetCmdTail)) > 0;
end;
