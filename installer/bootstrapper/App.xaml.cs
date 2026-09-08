using System.IO;
using System.Windows;

namespace Lagshift.Setup;

public partial class App : System.Windows.Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        try
        {
            ShutdownMode = ShutdownMode.OnMainWindowClose;
            var window = new MainWindow();
            MainWindow = window;
            window.Show();
        }
        catch (Exception ex)
        {
            var logPath = Path.Combine(Path.GetTempPath(), "LAGSHIFT-Setup-error.txt");
            try { File.WriteAllText(logPath, ex.ToString()); } catch { }
            System.Windows.MessageBox.Show("رابط نصب LAGSHIFT اجرا نشد.\n\n" + ex.Message + "\n\nگزارش خطا: " + logPath,
                "LAGSHIFT Setup", MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(1);
        }
    }
}
