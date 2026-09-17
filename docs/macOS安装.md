# macOS 安装与运行

macOS 版本使用系统钥匙串保存账号，不读取 Windows 的 `data/accounts.dpapi`。

## 环境

需要：

- macOS 13 或更新版本
- Python 3.10–3.12；Apple Silicon 可使用 Homebrew Python 3.12
- Node.js 22 或更新版本
- Git
- Google Chrome、Microsoft Edge 或 Chromium（三选一）

## 安装

```bash
cd UCAS-Desktop
python3.12 scripts/setup.py --check
python3.12 scripts/setup.py
```

安装器会创建 `.venv` 并安装依赖。首次写入账号时，macOS 会将 SEP 和轻新课堂账号保存到钥匙串中的 `UCAS-Desktop` 项目，不会写入 Git 仓库。

## 启动

```bash
./启动mac.sh
```

也可以直接运行：

```bash
.venv/bin/python app.py
```

关闭窗口时，程序仍可留在 macOS 菜单栏/后台运行；从菜单中选择退出才会停止任务。

## 手机访问

桌面程序启动后，在“设置与更新”启用局域网访问并重启。局域网内可使用手机面板；跨网络访问时，不要直接暴露 8765 端口，建议使用 Cloudflare Tunnel，并将 Tunnel 的 HTTPS 地址填入 Vercel 手机面板。

Vercel 页面：<https://ucas-desktop-mobile.vercel.app>

## 限制

macOS 版本已支持桌面 UI、任务 API、账号安全存储和 Chrome/Edge 浏览器路径；学校页面、验证码、驱动和第三方模块仍需用本人的账号逐项验证。Vercel 只提供手机网页，不运行桌面任务。
