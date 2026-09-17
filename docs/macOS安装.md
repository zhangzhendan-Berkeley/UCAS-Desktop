# macOS 安装与运行

v0.4.0 新增 macOS 源码运行支持，感谢提交署名 cuizixian0328 与 [@zihenghe04 的 PR #1](https://github.com/zhangzhendan-Berkeley/UCAS-Desktop/pull/1)。目前不提供签名的 `.app` / `.dmg`；Windows 便携 ZIP 不能用于 Mac。

## 环境

- macOS 13 或更新版本；自动检查使用 macOS 15 / Apple Silicon。
- Python 3.10–3.12、Node.js 22+（建议 24 LTS，含 npm）、Git。
- Microsoft Edge 或 Google Chrome，安装到 `/Applications` 或 `~/Applications`。优先选择 Edge，否则 Chrome；两者都没有时会明确提示安装。
- 网络能够访问 GitHub、PyPI、npm、浏览器驱动下载及学校入口。首次 Selenium 启动可能自动下载驱动。

## 安装与启动

在终端运行（示例使用 Python 3.12，其他支持版本可替换命令）：

```bash
git clone https://github.com/zhangzhendan-Berkeley/UCAS-Desktop.git
cd UCAS-Desktop
python3.12 scripts/setup.py --check
python3.12 scripts/setup.py
.venv/bin/python app.py
```

安装器创建独立 `.venv` 并下载固定版本的依赖。后续可在项目目录运行 `bash 启动mac.sh`。

人文预约和自动选课依赖需另行启用。阅读 [来源与许可](../THIRD_PARTY.md) 后，可执行：

```bash
python3.12 scripts/setup.py --with-external-modules
```

关闭窗口后，程序继续在菜单栏/后台运行；使用菜单中的“退出程序”才会结束。电脑睡眠、关机或退出程序时，任务不能继续执行。

## 账号与日常使用

1. 打开“个人信息”，分别填写 SEP、轻新课堂、发件邮箱和收件邮箱；使用检测按钮检查账号。
2. 课程与讲座签到使用轻新课堂；讲座时间表、预约和选课使用 SEP。讲座查询还需要已安装讲座模块。
3. 勾选记住账号时，账号通过原生 Keychain API 保存到系统钥匙串 `UCAS-Desktop`，不会通过 shell 或命令行参数传递密码。若系统提示授权，应核对是本应用使用的 Python。
4. 钥匙串锁定或拒绝访问时会显示错误，不回退到明文文件。忘记账号失败时会明确提示，请先解锁钥匙串再试。
5. Windows 的 `data/accounts.dpapi` 无法在 Mac 解密，迁移后请重新填写账号。规划、定时任务和其他配置仍在项目的 `data/` 中，不要上传该目录。
6. 在“概览”点击一键刷新；各模块具体操作见 [README](../README.md) 和 [仪表盘与邮件提醒](仪表盘与邮件提醒.md)。首次学校操作先查询和预览，并核对实际学校记录。

更新时先从菜单退出、备份自己的 `data/`，再拉取源码并重新执行安装命令。不要用另一台电脑的账号文件覆盖本机钥匙串。

## 手机只读面板

在“设置与更新”启用局域网访问并按提示重启，复制手机面板地址到同一局域网的手机。面板只读，桌面端必须保持运行。

也可自行托管仓库的 `mobile/` 目录（包括 `connection.mjs`），在面板中填写自己的桌面 API 地址和访问密钥，再点连接。密钥来自本机 `data/api-token.txt`；不要填写到不信任的网站。当前连接的地址与密钥成对保存到当前浏览器标签页会话中，改地址会断开并清除旧密钥，重定向不会携带密钥跳转。

跨网络访问需要自行配置可信的 HTTPS 隧道或反向代理；HTTPS 手机页面也应连接 HTTPS API，以免被浏览器阻止。没有默认的第三方托管手机站点，也没有原生 iOS 安装包。

## 验证范围与限制

[Core checks](https://github.com/zhangzhendan-Berkeley/UCAS-Desktop/actions/workflows/check.yml) 在 Windows 和 macOS 执行依赖安装、Python / Node 回归、离线界面、浏览器页面与任务停止检查；Mac 额外使用独立临时钥匙串项目验证保存、读取和删除，不触碰用户账号。各提交的实际结果以对应运行记录为准。

贡献者在 PR 中报告了 Apple Silicon / Python 3.12 的本机运行结果。自动检查不登录真实学校账号、不报名、不选课、不签到，因此不能证明学校在线接口在每个账号下都可用。验证码、校园网络和上游页面变化仍需用户验证。

当前支持 Windows 和 macOS；尚未提供 Linux 账号存储适配。
