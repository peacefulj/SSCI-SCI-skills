; =====================================================================
;  PaperMate（开源论文搭子）安装程序脚本
;  编译：ISCC.exe PaperMate.iss
;  产物：dist_installer\PaperMate-Setup-1.2.8.exe
;
;  设计原则
;  1. 装到用户目录（%LOCALAPPDATA%\Programs\PaperMate），**不需要管理员权限**——
;     学术用户大多是学生/老师，学校机房、单位电脑常常拿不到管理员。
;  2. 可写数据（上传文件、成稿记录、.env）放 %LOCALAPPDATA%\PaperMate，
;     与程序文件分离：升级程序不会丢用户的稿子和 key。
;  3. 安装前做环境体检（系统位数/内存/磁盘/端口/依赖运行时），缺什么就地补什么，
;     补不上就说清原因和替代做法，绝不装完才发现打不开。
; =====================================================================

#define AppName        "PaperMate"
#define AppNameCN      "开源论文搭子"
#define AppVersion     "1.3.0"
#define AppPublisher   "PaperMate"
#define AppExeName     "PaperMate.exe"
#define BuildDir       "dist\PaperMate"

[Setup]
AppId={{8F3C2A61-5D74-4B9E-9A1C-7E2D4F6B8A30}
AppName={#AppNameCN}（{#AppName}）
AppVersion={#AppVersion}
AppVerName={#AppNameCN} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppNameCN}
DisableProgramGroupPage=yes
; 用户级安装：不弹 UAC，不需要管理员
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist_installer
OutputBaseFilename=PaperMate-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppNameCN}（{#AppName}）
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 64 位应用（内置 64 位 Python 运行时）
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 最低 Windows 10：内置的 Python 3.13 需要 Win10+，Win7/8 装了也跑不起来
MinVersion=10.0
LicenseFile=LICENSE.txt
; 安装包体积大，允许用户自己改目录
DisableDirPage=no
CloseApplications=yes
RestartApplications=no

[Languages]
; 语言文件随项目分发（installer/ChineseSimplified.isl），不依赖 Inno 安装目录——
; 官方安装包已不再自带简体中文，从外部路径引用会让别人的机器编译失败。
Name: "chinesesimp"; MessagesFile: "installer\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce
Name: "quicklaunch"; Description: "创建开始菜单快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce

[Files]
; 主程序（onedir 全量）
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppNameCN}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\卸载 {#AppNameCN}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppNameCN}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; 安装完可以直接启动（默认勾选）
Filename: "{app}\{#AppExeName}"; Description: "立即启动 {#AppNameCN}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 只删程序目录；用户数据（%LOCALAPPDATA%\PaperMate）保留，避免卸载丢稿
Type: filesandordirs; Name: "{app}"

[Dirs]
; 用户数据目录（可写，与程序分离）
Name: "{localappdata}\PaperMate"; Permissions: users-full
Name: "{localappdata}\PaperMate\uploads"; Permissions: users-full
Name: "{localappdata}\PaperMate\_oneshot"; Permissions: users-full

[Code]
var
  EnvCheckPage: TOutputMsgWizardPage;
  EnvReport: String;
  EnvBlocked: Boolean;
  MissingItems: String;

{ ---------- 工具函数 ---------- }

function RunHidden(const Cmd, Params: String; var Output: String): Boolean;
var
  TmpFile: String;
  ExecOK: Boolean;
  RC: Integer;
  Loaded: AnsiString;
begin
  TmpFile := ExpandConstant('{tmp}\pm_probe.txt');
  { Exec 的出参是 Integer 退出码，不能直接塞给 Boolean 的 Result }
  ExecOK := Exec(ExpandConstant('{cmd}'), '/C ' + Cmd + ' ' + Params + ' > "' + TmpFile + '" 2>&1',
                 '', SW_HIDE, ewWaitUntilTerminated, RC);
  Output := '';
  if FileExists(TmpFile) then
  begin
    if LoadStringFromFile(TmpFile, Loaded) then
      Output := Trim(String(Loaded));
    DeleteFile(TmpFile);
  end;
  Result := ExecOK;
end;

function GetSystemMemMB(): Integer;
var
  S: String;
begin
  { 用 wmic 取物理内存（KB），换算成 MB }
  Result := 0;
  if RunHidden('wmic', 'ComputerSystem get TotalPhysicalMemory /value', S) then
  begin
    if Pos('TotalPhysicalMemory=', S) > 0 then
      Result := StrToInt64Def(Copy(S, Pos('=', S) + 1, 20), 0) div 1024 div 1024;
  end;
end;

function GetFreeDiskMB(const Dir: String): Integer;
var
  S, T, Drive: String;
begin
  Result := 0;
  Drive := ExtractFileDrive(Dir);
  if RunHidden('dir', '"' + Drive + '\"', S) then
  begin
    { 解析 "123,456,789 bytes free"。注意 StringChange 在 Inno Pascal 里是
      **过程**（原地改第一个参数），不是函数——写成 StringChange(S,..) 会报
      "Variable Expected"。 }
    if Pos('bytes free', S) > 0 then
    begin
      T := Copy(S, 1, Pos('bytes free', S) - 1);
      StringChange(T, ' ', '');
      StringChange(T, ',', '');
      StringChange(T, #13, '');
      StringChange(T, #10, '');
      T := Trim(T);
      Result := StrToInt64Def(T, 0) div 1024 div 1024;
    end;
  end;
end;

{ 端口是否被占用：netstat 里出现 LISTENING }
function PortInUse(Port: Integer): Boolean;
var
  S: String;
begin
  Result := False;
  if RunHidden('netstat', '-ano -p TCP', S) then
    Result := Pos(':' + IntToStr(Port) + ' ', S) > 0;
end;

{ 检测 VC++ 运行库：检查系统目录下关键 DLL }
function HasVCRuntime(): Boolean;
begin
  Result := FileExists(ExpandConstant('{sys}\vcruntime140.dll')) and
            FileExists(ExpandConstant('{sys}\msvcp140.dll'));
end;

function HasUCRT(): Boolean;
begin
  { Win10+ 自带 UCRT，这里作为显式确认 }
  Result := FileExists(ExpandConstant('{sys}\ucrtbase.dll'));
end;

{ 检测是否已有旧版本在运行 }
function AppRunning(): Boolean;
var
  S: String;
begin
  Result := False;
  if RunHidden('tasklist', '/FI "IMAGENAME eq PaperMate.exe" /NH', S) then
    Result := Pos('PaperMate.exe', S) > 0;
end;

{ ---------- 环境体检 ---------- }

{ 目录是否真的可写：建临时文件再删。
  不能用 FileExists 判断目录——它只认文件，对目录永远返回 False，
  曾因此把所有用户都误判成"用户目录不可写"而拦住安装。 }
function DirWritable(const Dir: String): Boolean;
var
  Probe: String;
  CreatedDir: Boolean;
begin
  Result := False;
  CreatedDir := not DirExists(Dir);
  if CreatedDir then
  begin
    { 目录不存在就顺手建出来；建不出来说明不可写 }
    if not ForceDirectories(Dir) then
      Exit;
  end;
  Probe := AddBackslash(Dir) + '.pm_probe.tmp';
  if SaveStringToFile(Probe, 'ok', False) then
  begin
    Result := True;
    DeleteFile(Probe);
  end;
  { 体检阶段只是探测，别留下空目录——用户可能中途取消安装 }
  if CreatedDir then
    RemoveDir(Dir);
end;

procedure BuildEnvReport();
var
  MemMB, DiskMB: Integer;
begin
  EnvReport := '';
  EnvBlocked := False;
  MissingItems := '';

  { 1. 操作系统：MinVersion 已拦 Win10 以下，这里补充说明 }
  EnvReport := EnvReport + '[OK] 操作系统：Windows 10 及以上' + #13#10;

  { 2. 系统位数 }
  if IsWin64 then
    EnvReport := EnvReport + '[OK] 系统架构：64 位' + #13#10
  else
  begin
    EnvReport := EnvReport + '[X] 系统架构：32 位（本程序需要 64 位 Windows）' + #13#10;
    EnvBlocked := True;
    MissingItems := MissingItems + '64 位 Windows；';
  end;

  { 3. 内存 }
  MemMB := GetSystemMemMB();
  if MemMB > 0 then
  begin
    if MemMB >= 2048 then
      EnvReport := EnvReport + '[OK] 内存：' + IntToStr(MemMB) + ' MB' + #13#10
    else
      EnvReport := EnvReport + '[!] 内存：' + IntToStr(MemMB) + ' MB（建议 4GB 以上，2GB 也能跑但长时间成稿会吃紧）' + #13#10;
  end
  else
    EnvReport := EnvReport + '[--] 内存：无法读取（不影响安装）' + #13#10;

  { 4. 磁盘空间 }
  DiskMB := GetFreeDiskMB(ExpandConstant('{localappdata}'));
  if DiskMB > 0 then
  begin
    if DiskMB >= 800 then
      EnvReport := EnvReport + '[OK] 磁盘可用：' + IntToStr(DiskMB) + ' MB' + #13#10
    else
    begin
      EnvReport := EnvReport + '[X] 磁盘可用：' + IntToStr(DiskMB) + ' MB（需要至少 800 MB）' + #13#10;
      EnvBlocked := True;
      MissingItems := MissingItems + '磁盘空间不足 800MB；';
    end;
  end;

  { 5. 权限：用户级安装不需要管理员，但检查用户目录可写 }
  if DirWritable(ExpandConstant('{localappdata}\PaperMate')) then
    EnvReport := EnvReport + '[OK] 安装权限：当前用户目录可写（无需管理员）' + #13#10
  else
  begin
    EnvReport := EnvReport + '[X] 安装权限：无法写入 ' +
      ExpandConstant('{localappdata}\PaperMate') + #13#10 +
      '     常见原因：公司电脑的策略限制、或该目录被占用。' + #13#10 +
      '     办法：换一个有写权限的位置安装，或联系 IT 放开该目录。' + #13#10;
    EnvBlocked := True;
    MissingItems := MissingItems + '用户目录不可写；';
  end;

  { 6. 运行时库 }
  if HasUCRT() and HasVCRuntime() then
    EnvReport := EnvReport + '[OK] 系统运行库：已就绪' + #13#10
  else
  begin
    { 非阻断：内置 Python 自带大部分依赖，缺 VC 运行库只影响 PDF 解析等可选功能 }
    EnvReport := EnvReport + '[!] 系统运行库：缺少 VC++ 2015-2022 运行库，' +
      'PDF 解析等个别功能可能不可用。' + #13#10 +
      '     解决：安装后从 https://aka.ms/vs/17/release/vc_redist.x64.exe 补装（可选）' + #13#10;
  end;

  { 7. 端口：不阻断，说明会自动顺延 }
  if PortInUse(8000) then
    EnvReport := EnvReport + '[--] 8000 端口：已被占用，程序会自动改用 8001/8002…' + #13#10
  else
    EnvReport := EnvReport + '[OK] 8000 端口：可用' + #13#10;

  { 8. 旧版本进程 }
  if AppRunning() then
  begin
    EnvReport := EnvReport + '[X] 检测到 PaperMate 正在运行，请先关闭再安装' + #13#10;
    EnvBlocked := True;
    MissingItems := MissingItems + '请先关闭正在运行的 PaperMate；';
  end;

  EnvReport := EnvReport + #13#10 + '点击「下一步」开始安装。程序会自动创建所需目录与配置。';
end;

procedure InitializeWizard();
begin
  BuildEnvReport();
  EnvCheckPage := CreateOutputMsgPage(wpSelectDir,
    '环境检查', '安装前自动检查了你的电脑环境',
    EnvReport);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = EnvCheckPage.ID then
  begin
    { 重新体检一次：用户可能在向导停留期间关掉了旧进程 }
    BuildEnvReport();
    if EnvBlocked then
    begin
      MsgBox('安装暂不能继续，需要先处理：' + #13#10#13#10 + MissingItems + #13#10 +
             '处理完点击「下一步」会重新检查。', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { 静默安装（/SILENT 或 /VERYSILENT）没有人能点「下一步」，
    自建的体检页必须跳过，否则部署脚本会永久卡在这一页。
    体检结论改写到安装日志，信息不丢。 }
  Result := (PageID = EnvCheckPage.ID) and WizardSilent;
  if Result then
  begin
    Log('静默安装：跳过环境检查页，体检结果如下');
    Log(EnvReport);
    if EnvBlocked then
      Log('警告：静默安装时检出阻断项：' + MissingItems);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    { 安装完成：确保用户数据目录存在 }
    DataDir := ExpandConstant('{localappdata}\PaperMate');
    ForceDirectories(DataDir);
    ForceDirectories(DataDir + '\uploads');
    ForceDirectories(DataDir + '\_oneshot');

    { 关键：把数据目录告诉程序。
      程序目录会随卸载/覆盖升级被清掉，稿件和 .env 必须放在用户目录。
      用文件而不是环境变量——用户可能从开始菜单、桌面快捷方式或直接双击
      exe 启动，这几种方式都读不到安装时设的环境变量。 }
    if not SaveStringToFile(ExpandConstant('{app}\datahome.txt'),
                            DataDir, False) then
      MsgBox('无法写入数据目录配置，已安装的程序会把数据存到程序目录，' + #13#10 +
             '升级或卸载时可能丢失稿件。请以当前用户身份重新安装。',
             mbError, MB_OK);
  end;
end;
