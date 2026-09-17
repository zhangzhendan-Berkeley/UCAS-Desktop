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

## 已在本机验证（Apple Silicon / macOS）

| 项目 | 结果 |
|---|---|
| 安装依赖与 Python 3.12 虚拟环境 | 通过 |
| 桌面程序启动、载入选课规划模块 | 通过 |
| 本地 API `127.0.0.1:8765` 与手机面板页面 | 通过 |
| 钥匙串保存/读取/忘记账号 | 通过 |
| 任务子进程、日志脱敏、中途停止 | 通过 |
| Selenium 驱动本机 Chrome（无头） | 通过 |
| SEP 登录流程离线回归（登录、密码错误拒绝、已选表解析） | 通过 |
| 单元测试 `unittest discover -s tests` | 60 项通过（2 项 Windows DPAPI 测试跳过） |
| 界面冒烟（ui_smoke / automation_ui_smoke / profile_planner_smoke / dashboard_ui_smoke / refresh_ui_smoke） | 通过 |
| Node 测试（手机面板、浏览器通道、讲座历史、讲座仪表盘） | 11 项通过 |
| 外部模块安装（人文讲座 + 自动选课，含 tsc 构建） | 通过 |
| 讲座离线回归（门户/校区，Playwright 使用本机 Chrome） | 通过 |

账号与模块的对应关系：课程与讲座签到用**轻新课堂**账号；科研讲座时间表、人文讲座预约、自动选课用 **SEP** 账号。科研讲座时间表还需要已安装讲座模块，缺模块时提示的是安装命令，不会再误报成缺少账号。

浏览器选择：装了 Edge 就用 Edge，否则用 Google Chrome，两者都没有时由 Playwright 使用自带 Chromium。Windows 专用的 `creationflags`（隐藏控制台）只在 Windows 上设置，macOS 设置它会被 Python 拒绝。

`unittest discover` 中的字体检查需要图形版 Qt 应用，单独运行可执行：

```bash
.venv/bin/python -m unittest tests.test_macos_support -v
```

只读的任务面板、任务子进程、钥匙串账号都已在 macOS 上实测；学校页面登录、验证码和第三方上游模块仍需用你本人的账号逐项验证。

## 手机跨网络访问（可选）

同一局域网内直接使用手机面板即可。需要在外网查看时，用 Cloudflare Tunnel 把本机 8765 端口映射为 HTTPS，再把地址填进 Vercel 页面：

```bash
cloudflared tunnel --url http://127.0.0.1:8765
```

把输出的 `https://xxxx.trycloudflare.com` 填入手机面板的“桌面助手 API 地址”，访问密钥取自 `data/api-token.txt`（界面“复制手机面板地址”也包含该密钥）。

临时隧道域名随机且公开可访问：接口只读、必须携带 Token，不用时请关闭隧道进程。不要把这个地址长期公开给他人。

## 限制

macOS 版本已支持桌面 UI、任务 API、账号安全存储和 Chrome/Edge 浏览器路径；学校页面、验证码、驱动和第三方模块仍需用本人的账号逐项验证。Vercel 只提供手机网页，不运行桌面任务。
