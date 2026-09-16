# iPhone 使用与原生签名评估

## 已实现：可添加到主屏幕的只读状态面板

1. Windows 应用打开「设置与更新」。
2. 勾选「允许同一局域网的手机查看任务状态」，保存并从托盘退出、重新打开应用。
3. 让 iPhone 和电脑连接同一个可互访的网络。点击「复制手机面板地址」，自行把地址传给手机，在 Safari 打开。
4. Safari → 分享 → 添加到主屏幕。
5. 页面可以查看任务状态；电脑应用需持续运行。访问地址包含个人读取密钥，请只用于自己的设备。

未修改 Windows 防火墙。如果手机打不开，先确认电脑与手机可互访；校园 Wi-Fi 可能隔离设备。可使用自己的可信局域网。若需设置防火墙，只开放专用网络上的本应用 TCP 8765 端口。

这不是原生 IPA：当前没有离线后台自动化能力，也没有把 Windows 的 Edge / Selenium 环境移植到 iOS。手机页面和 API 已通过本机测试，尚未使用iPhone 实机验证。

## 原生 iOS 安装为什么没有直接交付

当前仓库只提供 Windows 客户端与手机网页。仓库没有 iOS 构建工程、Apple provisioning 配置或已签名 IPA，不提供原生 iOS 安装包。

原生个人安装可使用 Apple 官方的 Xcode Personal Team：在 Mac 上用自己的 Apple Account 登录 Xcode，为自己的设备构建安装。Apple 官方说明免费个人团队的 provisioning profile 在签发 7 天后过期，需要重新构建和安装；还有 App ID 和设备数量限制。[Apple 官方账户说明](https://developer.apple.com/help/account/basics/about-your-developer-account)

Xcode 的受支持系统要求是 macOS。将来若有 Mac，可以基于已经保留的 `/v1/health`、`/v1/modules`、`/v1/jobs` 开发 SwiftUI 客户端，而不把学校接口和账号处理再复制一遍。[Xcode 官方系统要求](https://developer.apple.com/xcode/system-requirements)

普通自建的 TLS / 代码签名证书不能替代 Apple 的 iOS 应用 provisioning 和签名流程。本次未索取 Apple ID 密码、未注册开发者账号，也未购买证书或开发者服务。
