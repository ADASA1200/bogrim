; installer.iss - בונה התקנה אמיתית (Setup.exe) ל-RDesk, במקום/בנוסף לקובץ נייד.
; קומפול: ISCC installer.iss   (מריץ אחרי python build_exe.py, שמייצר dist\RDesk.exe).
; AppId קבוע כדי שעדכון עתידי יזהה ויחליף התקנה קיימת, לא יתקין עותק נוסף.
#define MyAppName "RDesk"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "RDesk"
#define MyAppExeName "RDesk.exe"

[Setup]
AppId={{330A1271-659E-494A-8145-BD9539F345D8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer_dist
OutputBaseFilename=RDesk-Setup
SetupIconFile=rdesk_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\RDesk.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; רישום סכימת rdesk:// (קישורי הזמנה לסשן) - ב-HKCU כדי שלא ידרוש הרשאות
; מנהל, בהתאמה ל-PrivilegesRequired=lowest. uninsdeletekey מסיר את הרישום
; הזה (לא את שאר Software\Classes) בהסרת ההתקנה.
[Registry]
Root: HKCU; Subkey: "Software\Classes\rdesk"; ValueType: string; ValueName: ""; ValueData: "URL:RDesk Invite Link"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\rdesk"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\rdesk\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\rdesk\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
