using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

class Launcher {
    [STAThread]
    static void Main(string[] args) {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, "runtime", "python", "pythonw.exe");
        if (!File.Exists(python)) python = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
        string script = Path.Combine(root, "app.py");
        if (!File.Exists(python) || !File.Exists(script)) {
            MessageBox.Show("运行环境不完整，请保留 UCAS-Desktop 整个文件夹，并查看使用指南。", "UCAS 桌面助手");
            return;
        }
        try {
            // Only the fixed diagnostic flag is forwarded; paths stay separately quoted.
            string extra = Array.IndexOf(args, "--smoke-test") >= 0 ? " --smoke-test" : "";
            var info = new ProcessStartInfo(python, "\"" + script + "\"" + extra);
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            info.EnvironmentVariables["PYTHONUTF8"] = "1";
            Process.Start(info);
        } catch (Exception e) {
            MessageBox.Show("启动失败：" + e.Message, "UCAS 桌面助手");
        }
    }
}
