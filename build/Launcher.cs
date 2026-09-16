using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

class Launcher {
    [STAThread]
    static void Main() {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
        string script = Path.Combine(root, "app.py");
        if (!File.Exists(python) || !File.Exists(script)) {
            MessageBox.Show("运行环境不完整，请保留 UCAS-Desktop 整个文件夹，并查看使用指南。", "UCAS 桌面助手");
            return;
        }
        try {
            var info = new ProcessStartInfo(python, "\"" + script + "\"");
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            Process.Start(info);
        } catch (Exception e) {
            MessageBox.Show("启动失败：" + e.Message, "UCAS 桌面助手");
        }
    }
}
