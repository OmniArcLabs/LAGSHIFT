#define MyAppName "LAGSHIFT"
#define MyAppVersion "1.0.3"
#define MyAppPublisher "OMNIARC"
#define MyAppExeName "LAGSHIFT.exe"
#define BuildSource "E:\LAGSHIFT-Builds\public-rc\dist\LAGSHIFT"

[Setup]
#ifdef QaBuild
AppId={{BAF079D2-28AF-44C7-A5F4-8CD7E7327E70}
#else
AppId={{E9B736F4-6827-47DB-8E66-0B6506E6A9D4}
#endif
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=LAGSHIFT Secure Installer
#ifdef QaBuild
DefaultDirName=E:\LAGSHIFT-Builds\qa-install
#else
DefaultDirName={autopf}\LAGSHIFT
#endif
DefaultGroupName=LAGSHIFT
DisableProgramGroupPage=yes
#ifdef QaBuild
PrivilegesRequired=lowest
#else
PrivilegesRequired=admin
#endif
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#ifdef BootstrapEngine
OutputDir=E:\LAGSHIFT-Builds\engine
OutputBaseFilename=LAGSHIFT-1.0.3-Engine
#else
OutputDir=E:\LAGSHIFT-Builds\public-rc\installer
#ifdef QaBuild
OutputBaseFilename=LAGSHIFT-1.0.3-QA-Setup
#else
OutputBaseFilename=LAGSHIFT-1.0.3-Setup
#endif
#endif
SetupIconFile=..\app\resources\branding\lagshift.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern dark polar includetitlebar
WizardBackColor=#071014
WizardBackImageFile=assets\lagshift-installer-background.png
WizardBackImageOpacity=105
WizardImageFile=
WizardSmallImageFile=
WizardSizePercent=115
Compression=lzma2/ultra64
SolidCompression=yes
MergeDuplicateFiles=yes
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}
RestartApplications=no
RestartIfNeededByRun=no
SetupLogging=yes
ShowLanguageDialog=no
AllowNoIcons=yes
InfoBeforeFile=release-notice-fa.txt

[Tasks]
Name: "desktopicon"; Description: "ساخت میانبر روی دسکتاپ"; GroupDescription: "میانبرها:"; Flags: unchecked

[Files]
Source: "{#BuildSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs notimestamp

; Runtime DLLs are one tested unit. Remove only the previous application
; payload before copying the new one so an upgrade can never mix Qt/Python
; generations. User settings live in AppData and are deliberately untouched.
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#MyAppExeName}"

[Dirs]
Name: "{app}"; Permissions: users-readexec

[Icons]
Name: "{autoprograms}\LAGSHIFT"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\LAGSHIFT"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "اجرای LAGSHIFT"; Flags: nowait postinstall skipifsilent

[Messages]
ButtonBrowse=انتخاب...
ButtonWizardBrowse=انتخاب...
WizardInfoBefore=نکات مهم
InfoBeforeLabel=پیش از ادامه، این اطلاعات کوتاه را مرور کن.
InfoBeforeClickLabel=وقتی آماده بودی، روی «ادامه» بزن.
WizardSelectDir=انتخاب مسیر نصب
SelectDirDesc=LAGSHIFT کجا نصب شود؟
SelectDirLabel3=LAGSHIFT در پوشه زیر نصب می‌شود.
SelectDirBrowseLabel=برای ادامه روی «ادامه» بزن؛ برای تغییر پوشه، «انتخاب» را بزن.
DiskSpaceGBLabel=حداقل [gb] گیگابایت فضای خالی لازم است.
DiskSpaceMBLabel=حداقل [mb] مگابایت فضای خالی لازم است.
WizardSelectTasks=انتخاب میانبرها
SelectTasksDesc=کدام میانبرها ساخته شوند؟
SelectTasksLabel2=میانبرهای دلخواه را انتخاب کن و سپس روی «ادامه» بزن.
WizardReady=آماده نصب
ReadyLabel1=همه‌چیز برای نصب [name] آماده است.
ReadyLabel2a=برای شروع «نصب LAGSHIFT» را بزن؛ برای تغییر انتخاب‌ها «بازگشت» را بزن.
ReadyLabel2b=برای شروع، روی «نصب LAGSHIFT» بزن.
WizardInstalling=در حال نصب
InstallingLabel=کمی صبر کن؛ [name] با حفظ تنظیمات قبلی نصب می‌شود.
FinishedHeadingLabel=LAGSHIFT آماده است
FinishedLabel=نصب [name] با موفقیت تمام شد.

[Code]
function SetTimer(hWnd: HWND; nIDEvent: UINT_PTR; uElapse: UINT; lpTimerFunc: NativeInt): UINT_PTR;
external 'SetTimer@user32.dll stdcall';

function KillTimer(hWnd: HWND; nIDEvent: UINT_PTR): BOOL;
external 'KillTimer@user32.dll stdcall';

function MessageBeep(uType: UINT): BOOL;
external 'MessageBeep@user32.dll stdcall';

var
  MotionTimer: UINT_PTR;
  MotionFrame: Integer;
  MotionLabel: TNewStaticText;
  StageProgress: TNewProgressBar;
  TermsPanel: TPanel;
  TermsText: TNewStaticText;

procedure LayoutWizardFooter;
var
  ButtonTop: Integer;
begin
  ButtonTop := WizardForm.ClientHeight - ScaleY(49);

  WizardForm.NextButton.Width := ScaleX(148);
  WizardForm.BackButton.Width := ScaleX(100);
  WizardForm.CancelButton.Width := ScaleX(96);
  WizardForm.NextButton.Height := ScaleY(38);
  WizardForm.BackButton.Height := ScaleY(38);
  WizardForm.CancelButton.Height := ScaleY(38);

  WizardForm.NextButton.Left := WizardForm.ClientWidth - ScaleX(18) - WizardForm.NextButton.Width;
  WizardForm.BackButton.Left := WizardForm.NextButton.Left - ScaleX(10) - WizardForm.BackButton.Width;
  WizardForm.CancelButton.Left := WizardForm.BackButton.Left - ScaleX(10) - WizardForm.CancelButton.Width;
  WizardForm.NextButton.Top := ButtonTop;
  WizardForm.BackButton.Top := ButtonTop;
  WizardForm.CancelButton.Top := ButtonTop;

  MotionLabel.Left := ScaleX(24);
  MotionLabel.Top := ButtonTop + ScaleY(10);
  MotionLabel.Width := WizardForm.CancelButton.Left - ScaleX(42);

  StageProgress.Left := 0;
  StageProgress.Top := ButtonTop - ScaleY(12);
  StageProgress.Width := WizardForm.ClientWidth;
  StageProgress.Height := ScaleY(4);

  WizardForm.NextButton.BringToFront;
  WizardForm.BackButton.BringToFront;
  WizardForm.CancelButton.BringToFront;
end;

procedure MotionTick(Arg1: HWND; Arg2: UINT; Arg3: UINT_PTR; Arg4: DWORD);
begin
  if (WizardForm = nil) or (MotionLabel = nil) then
    exit;

  Inc(MotionFrame);
  case MotionFrame mod 4 of
    0: MotionLabel.Font.Color := $00E8B94F;
    1: MotionLabel.Font.Color := $00F2C45B;
    2: MotionLabel.Font.Color := $00FFD778;
    3: MotionLabel.Font.Color := $00F2C45B;
  end;
end;

procedure InitializeWizard;
begin
  WizardForm.Caption := 'LAGSHIFT  •  Secure Setup';
  WizardForm.WelcomeLabel1.Caption := 'به مسیر سریع‌تر خوش آمدی';
  WizardForm.WelcomeLabel2.Caption :=
    'LAGSHIFT اتصال بازی‌ها و برنامه‌های پشتیبانی‌شده را اندازه‌گیری و بهینه می‌کند.' + #13#10 +
    'این محصول VPN عمومی نیست و تنظیمات شخصی شما را هنگام به‌روزرسانی حفظ می‌کند.';
  WizardForm.FinishedHeadingLabel.Caption := 'LAGSHIFT آماده است';
  WizardForm.FinishedLabel.Caption :=
    'نصب با موفقیت و بدون تغییر داده‌های شخصی قبلی انجام شد.';

  WizardForm.NextButton.Caption := 'ادامه  ←';
  WizardForm.NextButton.Font.Style := [fsBold];
  WizardForm.NextButton.Font.Size := 10;
  WizardForm.BackButton.Caption := 'بازگشت';
  WizardForm.CancelButton.Caption := 'انصراف';

  MotionLabel := TNewStaticText.Create(WizardForm);
  MotionLabel.Parent := WizardForm;
  MotionLabel.AutoSize := False;
  MotionLabel.Height := ScaleY(18);
  MotionLabel.Alignment := taLeftJustify;
  MotionLabel.Font.Style := [fsBold];
  MotionLabel.Font.Color := $00F2C45B;
  MotionLabel.Caption := '◆  مرحله ۱ از ۶  ·  شروع امن';

  StageProgress := TNewProgressBar.Create(WizardForm);
  StageProgress.Parent := WizardForm;
  StageProgress.Min := 0;
  StageProgress.Max := 6;
  StageProgress.Position := 1;

  WizardForm.InfoBeforeMemo.Visible := False;

  TermsPanel := TPanel.Create(WizardForm.InfoBeforePage);
  TermsPanel.Parent := WizardForm.InfoBeforePage;
  TermsPanel.ParentBackground := False;
  TermsPanel.BevelKind := bkFlat;
  TermsPanel.BevelOuter := bvNone;
  TermsPanel.Color := StrToColor('#101D25');
  TermsPanel.Left := WizardForm.InfoBeforeMemo.Left;
  TermsPanel.Top := WizardForm.InfoBeforeMemo.Top;
  TermsPanel.Width := WizardForm.InfoBeforeMemo.Width;
  TermsPanel.Height := WizardForm.InfoBeforeMemo.Height;
  TermsPanel.Caption := '';

  TermsText := TNewStaticText.Create(TermsPanel);
  TermsText.Parent := TermsPanel;
  TermsText.StyleElements := TermsText.StyleElements - [seFont];
  TermsText.AutoSize := False;
  TermsText.WordWrap := True;
  TermsText.Alignment := taRightJustify;
  TermsText.Left := ScaleX(18);
  TermsText.Top := ScaleY(16);
  TermsText.Width := TermsPanel.Width - ScaleX(36);
  TermsText.Height := TermsPanel.Height - ScaleY(32);
  TermsText.Font.Name := 'Segoe UI';
  TermsText.Font.Size := 10;
  TermsText.Font.Color := StrToColor('#ECF9FD');
  TermsText.Caption :=
    'LAGSHIFT یک بهینه‌ساز اتصال بازی‌ها و برنامه‌های پشتیبانی‌شده است و سرویس VPN عمومی محسوب نمی‌شود.' + #13#10 + #13#10 +
    'این نسخه امکان ورود کانفیگ یا Subscription ندارد. WARP فقط پس از شناسایی کلاینت رسمی و تأیید واقعی مسیر فعال می‌شود.' + #13#10 + #13#10 +
    'نصب نسخه جدید، تنظیمات و داده‌های شخصی قبلی را حذف نمی‌کند. حذف برنامه نیز اطلاعات شخصی را خودکار پاک نمی‌کند.' + #13#10 + #13#10 +
    'شرایط کامل استفاده و حریم خصوصی در اولین اجرای برنامه نمایش داده می‌شود.';

  LayoutWizardFooter;

  MotionTimer := SetTimer(0, 0, 420, CreateCallback(@MotionTick));
  MessageBeep($00000040);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  WizardForm.NextButton.Caption := 'ادامه  ←';
  case CurPageID of
    wpWelcome:
      begin
        MotionLabel.Caption := '◆  مرحله ۱ از ۶  ·  خوش‌آمدی';
        StageProgress.Position := 1;
      end;
    wpInfoBefore:
      begin
        WizardForm.PageNameLabel.Caption := 'نکات مهم قبل از شروع';
        WizardForm.PageDescriptionLabel.Caption := 'چند نکته کوتاه برای یک نصب امن و بی‌دردسر';
        MotionLabel.Caption := '◆  مرحله ۲ از ۶  ·  مرور نکات مهم';
        StageProgress.Position := 2;
      end;
    wpSelectDir:
      begin
        WizardForm.PageNameLabel.Caption := 'LAGSHIFT کجا نصب شود؟';
        WizardForm.PageDescriptionLabel.Caption := 'مسیر پیشنهادی برای بیشتر کاربران بهترین انتخاب است';
        MotionLabel.Caption := '◆  مرحله ۳ از ۶  ·  انتخاب مسیر نصب';
        StageProgress.Position := 3;
      end;
    wpSelectTasks:
      begin
        WizardForm.PageNameLabel.Caption := 'میانبرهای دلخواه';
        WizardForm.PageDescriptionLabel.Caption := 'انتخاب کن LAGSHIFT از کجا در دسترس باشد';
        MotionLabel.Caption := '◆  مرحله ۴ از ۶  ·  انتخاب میانبرها';
        StageProgress.Position := 4;
      end;
    wpReady:
      begin
        WizardForm.PageNameLabel.Caption := 'همه‌چیز آماده است';
        WizardForm.PageDescriptionLabel.Caption := 'با یک کلیک، نصب امن LAGSHIFT شروع می‌شود';
        MotionLabel.Caption := '◆  مرحله ۵ از ۶  ·  آماده‌ی نصب';
        StageProgress.Position := 5;
        WizardForm.NextButton.Caption := 'نصب LAGSHIFT  ←';
      end;
    wpInstalling:
      begin
        WizardForm.PageNameLabel.Caption := 'در حال آماده‌سازی مسیر';
        WizardForm.PageDescriptionLabel.Caption := 'فایل‌های ضروری با حفظ تنظیمات قبلی نصب می‌شوند';
        MotionLabel.Caption := '◆  مرحله ۶ از ۶  ·  نصب امن در حال انجام است';
        StageProgress.Position := 6;
      end;
    wpFinished:
      begin
        WizardForm.PageNameLabel.Caption := 'LAGSHIFT آماده است';
        WizardForm.PageDescriptionLabel.Caption := 'مسیر سریع‌تر از همین‌جا شروع می‌شود';
        MotionLabel.Caption := '◆  مسیر آماده است  ·  وقت بازی';
        StageProgress.Position := 6;
        WizardForm.NextButton.Caption := 'اجرای LAGSHIFT';
      end;
  end;
  LayoutWizardFooter;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then begin
    MotionLabel.Caption := '◆  LAGSHIFT  ·  آماده‌ی اجرا';
    MessageBeep($00000040);
  end;
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
var
  ProgressFile: String;
begin
  ProgressFile := ExpandConstant('{param:lagshiftprogress|}');
  if ProgressFile <> '' then
    SaveStringToFile(ProgressFile,
      IntToStr(CurProgress) + '|' + IntToStr(MaxProgress) + '|installing', False);
end;

procedure DeinitializeSetup;
begin
  if MotionTimer <> 0 then
    KillTimer(0, MotionTimer);
end;
