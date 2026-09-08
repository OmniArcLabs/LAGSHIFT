using System.Diagnostics;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Media;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media.Animation;

namespace Lagshift.Setup;

public partial class MainWindow : Window
{
    private const int PageCount = 6;
    private int _page = 1;
    private bool _installing;
    private bool _allowClose;
    private string? _tempDirectory;

    private static readonly string[] Titles =
    [
        "قبل از ادامه، این نکات مهم را مرور کن",
        "LAGSHIFT کجا نصب شود؟",
        "انتخاب‌های نهایی تو",
        "آماده‌ی ساخت مسیر سریع‌تر",
        "در حال نصب LAGSHIFT",
        "نصب با موفقیت کامل شد"
    ];

    private static readonly string[] Subtitles =
    [
        "تنظیمات فعلی تو حفظ می‌شوند و فقط اجزای ضروری نصب خواهند شد.",
        "مسیر پیشنهادی برای بیشتر کاربران، امن‌ترین و ساده‌ترین انتخاب است.",
        "مشخص کن بعد از نصب چه میانبرهایی ساخته و برنامه اجرا شود.",
        "انتخاب‌ها را بررسی کن؛ عملیات نصب با یک کلیک شروع می‌شود.",
        "فایل‌های ضروری با حفظ تنظیمات قبلی در حال نصب هستند.",
        "همه‌چیز آماده است؛ می‌توانی مستقیم وارد LAGSHIFT شوی."
    ];

    public MainWindow()
    {
        InitializeComponent();
        UpdatePage();
    }

    private void TitleBar_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ClickCount == 2) WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
        else DragMove();
    }

    private void Minimize_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

    private void Window_SizeChanged(object sender, SizeChangedEventArgs e) => AnimateStage((double)_page / PageCount);

    private void Window_Closing(object? sender, CancelEventArgs e)
    {
        if (_installing)
        {
            e.Cancel = true;
            return;
        }

        if (!_allowClose && _page < 6)
        {
            e.Cancel = true;
            ShowExitConfirmation();
        }
    }

    private void Window_Closed(object? sender, EventArgs e) => System.Windows.Application.Current.Shutdown();

    private void Close_Click(object sender, RoutedEventArgs e)
    {
        if (_installing) return;
        if (_page == 6)
        {
            _allowClose = true;
            Close();
            return;
        }
        ShowExitConfirmation();
    }

    private void ShowExitConfirmation()
    {
        ExitOverlay.Visibility = Visibility.Visible;
        NextButton.IsEnabled = BackButton.IsEnabled = CancelButton.IsEnabled = false;
    }

    private void ContinueSetup_Click(object sender, RoutedEventArgs e)
    {
        ExitOverlay.Visibility = Visibility.Collapsed;
        UpdatePage();
    }

    private void ConfirmExit_Click(object sender, RoutedEventArgs e)
    {
        _allowClose = true;
        Close();
    }

    private void Browse_Click(object sender, RoutedEventArgs e)
    {
        using var dialog = new System.Windows.Forms.FolderBrowserDialog
        {
            Description = "انتخاب پوشه نصب LAGSHIFT",
            SelectedPath = InstallPathBox.Text,
            ShowNewFolderButton = true
        };
        if (dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK) InstallPathBox.Text = dialog.SelectedPath;
    }

    private void Back_Click(object sender, RoutedEventArgs e)
    {
        if (_installing || _page <= 1) return;
        _page--;
        UpdatePage();
    }

    private async void Next_Click(object sender, RoutedEventArgs e)
    {
        if (_page == 2 && string.IsNullOrWhiteSpace(InstallPathBox.Text))
        {
            System.Windows.MessageBox.Show(this, "مسیر نصب را انتخاب کن.", "LAGSHIFT", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        if (_page < 4)
        {
            _page++;
            UpdatePage();
            return;
        }

        if (_page == 4) await InstallAsync();
        else if (_page == 6)
        {
            if (LaunchAfterCheck.IsChecked == true)
            {
                var app = Path.Combine(InstallPathBox.Text.Trim(), "LAGSHIFT.exe");
                if (File.Exists(app)) Process.Start(new ProcessStartInfo(app) { UseShellExecute = true });
            }
            _allowClose = true;
            Close();
        }
    }

    private void UpdatePage()
    {
        InfoPage.Visibility = _page == 1 ? Visibility.Visible : Visibility.Collapsed;
        LocationPage.Visibility = _page == 2 ? Visibility.Visible : Visibility.Collapsed;
        OptionsPage.Visibility = _page == 3 ? Visibility.Visible : Visibility.Collapsed;
        ReadyPage.Visibility = _page == 4 ? Visibility.Visible : Visibility.Collapsed;
        InstallingPage.Visibility = _page == 5 ? Visibility.Visible : Visibility.Collapsed;
        FinishedPage.Visibility = _page == 6 ? Visibility.Visible : Visibility.Collapsed;

        TitleText.Text = Titles[_page - 1];
        SubtitleText.Text = Subtitles[_page - 1];
        StageText.Text = _page == 6 ? "مسیر آماده است · وقت بازی" : $"مرحله {_page.ToString(CultureInfo.InvariantCulture)} از {PageCount} · {StageName(_page)}";
        KickerText.Text = _page switch { 5 => "نصب امن و قابل‌برگشت", 6 => "ماموریت با موفقیت انجام شد", _ => "راه‌اندازی امن و سریع" };
        ReadyPath.Text = InstallPathBox.Text;
        ReadyShortcut.Text = DesktopShortcutCheck.IsChecked == true ? "ساخته می‌شود" : "ساخته نمی‌شود";
        ReadyOperation.Text = RepairInstallCheck.IsChecked == true ? "تعمیر امن فایل‌ها" : "نصب یا به‌روزرسانی";

        BackButton.IsEnabled = !_installing && _page is > 1 and < 6;
        CancelButton.IsEnabled = !_installing;
        NextButton.IsEnabled = !_installing;
        NextButton.Content = _page switch { 4 => "نصب LAGSHIFT  ←", 5 => "در حال نصب…", 6 => "پایان و اجرا", _ => "ادامه  ←" };
        AnimateStage((double)_page / PageCount);
    }

    private static string StageName(int page) => page switch
    {
        1 => "مرور نکات مهم", 2 => "انتخاب مسیر نصب", 3 => "انتخاب میانبرها",
        4 => "بازبینی نهایی", 5 => "نصب امن", _ => "آماده‌ی اجرا"
    };

    private void AnimateStage(double ratio)
    {
        var target = Math.Max(12, ActualWidth > 0 ? (ActualWidth - 2) * ratio : 898 * ratio);
        if (ReduceMotionCheck.IsChecked == true)
        {
            StageProgress.BeginAnimation(WidthProperty, null);
            StageProgress.Width = target;
            return;
        }
        StageProgress.BeginAnimation(WidthProperty, new DoubleAnimation(target, TimeSpan.FromMilliseconds(320))
        { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut } });
    }

    private async Task InstallAsync()
    {
        _page = 5;
        _installing = true;
        UpdatePage();
        NextButton.IsEnabled = BackButton.IsEnabled = CancelButton.IsEnabled = false;

        _tempDirectory = Path.Combine(Path.GetTempPath(), "LAGSHIFT-Setup-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_tempDirectory);
        var enginePath = Path.Combine(_tempDirectory, "LAGSHIFT-Engine.exe");
        var progressPath = Path.Combine(_tempDirectory, "progress.txt");
        var backupPath = Path.Combine(_tempDirectory, "previous-version");
        var installPath = "";
        var previousVersionBackedUp = false;

        try
        {
            await ExtractEngineAsync(enginePath);
            InstallStatus.Text = "موتور نصب آماده شد؛ در حال بررسی فایل‌ها…";
            SetInstallProgress(3);

            installPath = Path.GetFullPath(InstallPathBox.Text.Trim()).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            ValidateInstallPath(installPath);
            if (Directory.Exists(installPath) && Directory.EnumerateFileSystemEntries(installPath).Any())
            {
                InstallStatus.Text = "در حال ساخت نقطه بازگشت از نسخه فعلی…";
                CopyDirectory(installPath, backupPath, overwrite: false);
                previousVersionBackedUp = true;
            }
            var tasks = DesktopShortcutCheck.IsChecked == true ? "/TASKS=\"desktopicon\"" : "/MERGETASKS=\"!desktopicon\"";
            var args = $"/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /DIR=\"{installPath}\" {tasks} /LAGSHIFTPROGRESS=\"{progressPath}\"";
            using var process = Process.Start(new ProcessStartInfo(enginePath, args)
            {
                UseShellExecute = true,
                WorkingDirectory = _tempDirectory
            }) ?? throw new InvalidOperationException("موتور نصب اجرا نشد.");

            while (!process.HasExited)
            {
                ReadEngineProgress(progressPath);
                await Task.Delay(120);
            }

            if (process.ExitCode != 0) throw new InvalidOperationException($"نصب با کد {process.ExitCode} متوقف شد.");

            SetInstallProgress(100);
            if (MuteInstallerCheck.IsChecked != true) SystemSounds.Asterisk.Play();
            _installing = false;
            _page = 6;
            UpdatePage();
        }
        catch (Exception ex)
        {
            var rollbackMessage = "";
            if (previousVersionBackedUp && !string.IsNullOrWhiteSpace(installPath))
            {
                try
                {
                    CopyDirectory(backupPath, installPath, overwrite: true);
                    rollbackMessage = "\nنسخه قبلی از نقطه بازگشت محلی بازیابی شد.";
                }
                catch (Exception rollbackError)
                {
                    rollbackMessage = "\nبازیابی خودکار نسخه قبلی کامل نشد: " + rollbackError.Message;
                }
            }
            _installing = false;
            _page = 4;
            UpdatePage();
            System.Windows.MessageBox.Show(this, "نصب کامل نشد. هیچ اتصال شبکه‌ای تغییر نکرد.\n\n" + ex.Message + rollbackMessage, "LAGSHIFT", MessageBoxButton.OK, MessageBoxImage.Error);
        }
        finally
        {
            TryCleanup();
        }
    }

    private static void ValidateInstallPath(string path)
    {
        var root = Path.GetPathRoot(path)?.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var normalized = path.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        if (string.IsNullOrWhiteSpace(root) || string.Equals(root, normalized, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("نصب مستقیم در ریشه درایو مجاز نیست.");
        var windows = Environment.GetFolderPath(Environment.SpecialFolder.Windows).TrimEnd(Path.DirectorySeparatorChar);
        if (normalized.StartsWith(windows + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(normalized, windows, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("پوشه Windows مسیر نصب مجاز نیست.");
    }

    private static void CopyDirectory(string source, string destination, bool overwrite)
    {
        var sourceInfo = new DirectoryInfo(source);
        if (!sourceInfo.Exists) return;
        Directory.CreateDirectory(destination);
        foreach (var file in sourceInfo.EnumerateFiles())
            file.CopyTo(Path.Combine(destination, file.Name), overwrite);
        foreach (var directory in sourceInfo.EnumerateDirectories())
        {
            if ((directory.Attributes & FileAttributes.ReparsePoint) != 0) continue;
            CopyDirectory(directory.FullName, Path.Combine(destination, directory.Name), overwrite);
        }
    }

    private static async Task ExtractEngineAsync(string path)
    {
        using var source = Assembly.GetExecutingAssembly().GetManifestResourceStream("Lagshift.Setup.Payload.Engine.exe")
            ?? throw new InvalidOperationException("بسته داخلی نصب پیدا نشد.");
        using var destination = File.Create(path);
        await source.CopyToAsync(destination);
    }

    private void ReadEngineProgress(string path)
    {
        try
        {
            if (!File.Exists(path)) return;
            var value = File.ReadAllText(path).Trim().Split('|');
            if (value.Length < 2 || !double.TryParse(value[0], NumberStyles.Float, CultureInfo.InvariantCulture, out var current) ||
                !double.TryParse(value[1], NumberStyles.Float, CultureInfo.InvariantCulture, out var max) || max <= 0) return;
            SetInstallProgress(Clamp(current / max * 100, 3, 99));
            if (value.Length > 2 && !string.IsNullOrWhiteSpace(value[2])) InstallStatus.Text = "در حال نصب فایل‌های ضروری…";
        }
        catch (IOException) { }
    }

    private void SetInstallProgress(double percent)
    {
        InstallPercent.Text = ToPersianDigits($"{Math.Round(percent):0}٪");
        var available = Math.Max(1, InstallingPage.ActualWidth - 4);
        var target = available * percent / 100;
        if (ReduceMotionCheck.IsChecked == true)
        {
            InnerProgress.BeginAnimation(WidthProperty, null);
            InnerProgress.Width = target;
        }
        else
        {
            InnerProgress.BeginAnimation(WidthProperty, new DoubleAnimation(target, TimeSpan.FromMilliseconds(180))
            { EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut } });
        }
    }

    private void AccessibilityChanged(object sender, RoutedEventArgs e)
    {
        if (!IsLoaded) return;
        AnimateStage((double)_page / PageCount);
    }

    private static string ToPersianDigits(string value)
    {
        const string latin = "0123456789";
        const string persian = "۰۱۲۳۴۵۶۷۸۹";
        for (var i = 0; i < latin.Length; i++) value = value.Replace(latin[i], persian[i]);
        return value;
    }

    private static double Clamp(double value, double minimum, double maximum) =>
        value < minimum ? minimum : value > maximum ? maximum : value;

    private void TryCleanup()
    {
        if (string.IsNullOrWhiteSpace(_tempDirectory)) return;
        try { Directory.Delete(_tempDirectory, true); } catch { }
    }
}
