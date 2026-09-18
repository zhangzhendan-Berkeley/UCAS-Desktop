# Linux 安装与运行

Linux 支持来自维护者提供的 `UCAS-Desktop-linux-pr.tar.gz` 补丁，合入时保留提交作者信息，并补充系统密钥环、浏览器和回归检查。当前从 **main 主分支源码** 安装；v0.4.0 标签不包含这次更新，没有 Linux AppImage / deb / rpm 包。

## 环境与验证范围

- Python 3.10–3.12、Node.js 22+（建议 24 LTS，含 npm）、Git。
- 桌面会话或能够显示窗口的远程桌面；Qt 界面、登录窗口及验证码需要图形显示。
- 优先使用 Google Chrome，其次 Chromium，最后 Edge；支持 `/usr/bin/` 下的常见名称，包括 `microsoft-edge-stable`、`google-chrome-stable` 和 `chromium-browser`。
- 同一用户的 D-Bus 会话，以及已配置、可解锁的 Secret Service / KWallet。
- 自动检查使用 Ubuntu 24.04 x64。维护者反馈已在服务器版系统运行；其他发行版、架构和 KDE 环境仍需单独验证。

## Ubuntu / Debian 安装示例

在普通用户的桌面终端执行。以下安装桌面依赖，不会安装完整的桌面环境；Python 版本请先核对是否在支持范围内。

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv gnome-keyring dbus-x11 \
  fonts-noto-cjk libegl1 libopengl0 libxcb-cursor0 libxkbcommon-x11-0
```

另外安装 Node.js 22+ 和 Edge / Chrome / Chromium，确认 `node --version`、`npm --version` 可用。发行版自带 Node 版本可能较旧。

```bash
git clone https://github.com/zhangzhendan-Berkeley/UCAS-Desktop.git
cd UCAS-Desktop
python3 scripts/setup.py --check
python3 scripts/setup.py
./启动linux.sh
```

安装器创建独立 `.venv`；也可用 `.venv/bin/python app.py` 启动。讲座预约和自动选课是可选外部模块，阅读 [来源与许可](../THIRD_PARTY.md) 后执行：

```bash
python3 scripts/setup.py --with-external-modules
```

更新前退出应用并备份 `data/`，然后 `git pull --ff-only`，重新运行安装命令。无需移动或重新创建系统密钥环。

## 账号存储

在“个人信息”录入 SEP、轻新课堂及邮件账号。应用使用 `UCAS-Desktop` 服务名保存记录，与原始 Linux 补丁写入的三类账号兼容；新增扩展账号也会在重启时恢复。

应用只接受 keyring 自带的 Secret Service / KWallet 后端；拒绝明文文件或空后端。保存和忘记账号都核对实际结果，拒绝授权、密钥环锁定或删除失败会明确提示。Windows 的 DPAPI 账号文件不能在 Linux 解密，迁移后需重新输入账号。

GNOME 桌面通常使用 GNOME Keyring，可通过“密码和密钥”管理并解锁。KWallet 需要与 keyring 支持版本对应的服务和 Python D-Bus 依赖；当前固定 keyring 的原生适配是 KWallet 5/4，KDE 6 请先确认可用的 Secret Service 接口。CI 实测的是 GNOME Secret Service，未据此声称所有 KWallet 环境已通过。

若看到“无法访问 Linux 系统密钥环”，请在启动应用的同一会话检查：

```bash
.venv/bin/python -m keyring diagnose
```

确认 D-Bus、密钥环服务和解锁状态。不要安装明文 keyring 插件来绕过提示；检查输出可能包含本机路径，反馈前请自行检查。

## 服务器与后台运行

此应用仍是桌面程序。纯 SSH 会话通常缺少显示环境、D-Bus 或密钥环；服务器需要配置远程桌面或等效环境，并在该会话启动。Xvfb 可用于离线检查，但不会自动解决验证码、登录授权或密钥环弹窗。

定时计划使用运行进程的本地时区。服务器常设为 UTC，运行前请确认北京时间；可用 `TZ=Asia/Shanghai ./启动linux.sh` 只为本应用及其子进程设置时区，避免影响服务器上的其他服务。

系统托盘可用时，关闭窗口隐藏到托盘；托盘不可用时，界面会提示关闭窗口将退出，此时可最小化保留运行。注销桌面、电脑睡眠或关闭应用后，任务不能继续执行。目前没有提供 systemd 服务安装或无桌面常驻服务。

Linux 浏览器若安装在沙箱包中，需确认其可访问应用数据目录。若 Edge 启动日志提示 `SUID sandbox helper binary ... not configured correctly`，说明浏览器安装的沙箱辅助程序所有者或权限异常，请按浏览器发行包要求修复或重新安装。CI 验证使用 Chrome。预装 Edge 152 在该镜像修复权限后仍出现渲染进程超时，因此不据此宣称 Linux Edge 已完整验证；应用不会自动关闭浏览器沙箱。不要以 root 运行应用来处理浏览器权限问题。

## 验证

[Core checks](https://github.com/zhangzhendan-Berkeley/UCAS-Desktop/actions/workflows/check.yml) 在 Windows、macOS 和 Ubuntu 执行单元测试、界面检查、离线浏览器页面、任务启动与停止检查；Linux 额外在隔离 D-Bus 会话中使用 GNOME Keyring 验证保存、重启读取及忘记账号。测试使用临时服务名和虚构账号，不读写用户密钥环中的正式账号。

相关命令（已完成源码安装后）：

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/*.test.mjs
.venv/bin/python scripts/linux_keyring_self_test.py
```

最后一项需要已解锁的系统密钥环。自动检查不会登录学校、报名、选课或签到；真实学校功能仍应先预览并核对学校记录。
