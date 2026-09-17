# 参考工作、来源与许可

本项目集成已有工作，并新增 Windows 界面、系统托盘、任务调度、凭据管理、结果校验和扩展接口。各上游项目的成果属于其原作者；本项目不声称原创这些学校接口、课表规划器或平台自动化方案。

## 社区贡献者

- [@zihenghe04](https://github.com/zihenghe04)：[PR #1 — macOS 运行支持](https://github.com/zhangzhendan-Berkeley/UCAS-Desktop/pull/1)，提供钥匙串、浏览器、字体、进程、安装说明、手机页面与测试适配。原作者提交保留在 Git 历史中；后续集成修复不改变其贡献归属。

## 直接采用与适配

完整固定提交见 [`modules.json`](modules.json)，日期为 2026-09-16 核验时的快照，并非长期可用保证。

| 项目与作者 | 使用范围 | 固定版本 | 已见许可信息与公开方式 |
|---|---|---|---|
| [lccipher/UCAS-Course-Sign-in](https://github.com/lccipher/UCAS-Course-Sign-in) | iClass 登录、课表、时间校准、签到协议；据此编写 Python 连接器，增加严格结果判定及有界调度 | `3bb182708b6d` | AGPL-3.0；集成层采用 AGPL-3.0-only，原仓库由安装器单独获取以便追溯 |
| [WindFromKadath/UCAS-Course-Selector](https://github.com/WindFromKadath/UCAS-Course-Selector) | 选课规划器、2026 秋季课表、筛选、冲突判断、导出 | `d7d12d48853b` | MIT；单独下载到 `vendor/`，保留原 LICENSE。通过集成层调整布局与数据目录 |
| [FYTJ/ucas-humanity-lecture-bot](https://github.com/FYTJ/ucas-humanity-lecture-bot) | 人文讲座候选、报名、配额和 OCR 工作流 | `8ec05b402577` | 该快照未发现独立 LICENSE；作为需显式选择的外部依赖，不将完整源码纳入本仓库，不宣称其采用 AGPL |
| [wendychan03/ucas-mooc-helper](https://github.com/wendychan03/ucas-mooc-helper) | 2026 春季英语慕课视频、PDF 处理函数 | `65d849d79c2a` | package.json 标注 ISC；上游作者字段为空，没有据此臆造版权声明。安装时下载并生成本地适配文件，生成文件不提交到本仓库 |
| [G9B0ND/UCAS-COURSE-SELECTION-SCRIPT](https://github.com/G9B0ND/UCAS-COURSE-SELECTION-SCRIPT) | 新版 xkgo 查询、验证码及预选列表核验 | `7ddd1c2e4aa9` | 该快照未发现独立 LICENSE；作为需显式选择的外部依赖，不包含完整源码，不宣称其采用 AGPL |

### 应保留的间接作者归属

- wendychan03 的 README 明确致谢原作者 [kejaly/ucas_english_mooc](https://github.com/kejaly/ucas_english_mooc)。本项目使用的慕课处理逻辑沿用这一来源。
- G9B0ND 的 README 声明来源为 [lizhuoq/UCAS-Course-selection-script](https://github.com/lizhuoq/UCAS-Course-selection-script)。本项目同时保留对原工作的致谢。

## 调研入口与交叉参考

- [Course Planner](https://courseplanner.cysdy.cn/)（页面署名 ITP 草原上的鱼）：2026-09-17 参考课程分类配色、查询筛选、详情及备选的交互组织。对应桌面功能在 `ucasdesk/catalog.py`、`ucasdesk/planner.py` 和 `ucasdesk/ui.py` 中独立实现；未复制网站代码、样式文件、图标或课程数据。既有课表仍来自下述规划器上游。
- [Littlefish12138/UCAS-on-Github](https://github.com/Littlefish12138/UCAS-on-Github/tree/main/教务系统相关)：本次项目发现和筛选入口；目录快照 `b0b85436da1fab4f0152a6f050558c9b875dfc9c`。
- [Littlefish12138/UCAS_Mooc_Helper](https://github.com/Littlefish12138/UCAS_Mooc_Helper)：调研军事理论课程自动化；未接入研究生英语测验。
- [tang-ontheway/ucas-mooc-helper](https://github.com/tang-ontheway/ucas-mooc-helper)：同平台脚本对比，未同时运行。
- [MosRat/ucas-iclass-checkin](https://github.com/MosRat/ucas-iclass-checkin)：iClass 文档和架构交叉核对，未复制其图标或界面。
- [wirsbf/TraintimePda-UCAS](https://github.com/wirsbf/TraintimePda-UCAS)、[tbjuechen/sep-api](https://github.com/tbjuechen/sep-api)：统一课表、讲座数据接口调研，未作为默认执行模块。

## 本仓库新增与修改

- `ucasdesk/`：PySide6 原生界面、Windows DPAPI、任务日志、定时调度、系统托盘、重复启动唤醒、API 和更新暂存。
- `adapters/`：统一的 JSON 标准输入入口、独立浏览器会话、停止与重试策略、结果核验。
- `patches/lecture-local.patch`：针对上述固定版本的 Windows Edge、SEP 新工作台、会话复用、目标行重新定位、保守结果判断适配；补丁中的原有上下文仍归原作者。
- `patches/lecture-register.test.ts`：本项目新增的失败反馈与明确成功状态测试。
- `patches/lecture-sep-workbench.patch`、`patches/lecture-portal.ts`：新版 SEP → 选课系统 → 指定讲座分类的会话跳转、隐藏菜单定位、Referer 保留及日志隐私处理；没有保存任何账号专属入口票据。
- `patches/lecture-table.patch`：按“讲座名称”列读取标题、跳过表头，避免把系列专题当作具体场次。
- `adapters/lecture_schedule.mjs`：科研讲座当前页的只读时间表查询；可在界面填入时间，签到场次仅从本人轻新课堂课表严格匹配或由二维码提供。
- `scripts/setup.py`：从原仓库下载固定版本；在用户本地提取 `deal_video/deal_pdf`，将视频等待超时和 PDF 未确认改为明确失败。
- `assets/app.svg`：本项目绘制的 U 与勾号图标，不是学校官方校徽。

## 许可边界

本仓库自行编写的集成代码采用 **GNU AGPL v3（AGPL-3.0-only）**，见 [LICENSE](LICENSE)。该声明不改变第三方作者的权利或其原始许可；外部仓库、补丁中的上游代码、课表数据及安装后获得的依赖分别按其原始条款处理。

源码默认安装不下载两项许可未明确的外部模块。阅读相应原仓库后，如需在本地启用，使用 `--with-external-modules`；便携版对应“设置与更新 → 一键启用讲座预约与抢课”。这不是本项目授予的再分发许可。不要把安装后的整个 `vendor/`、浏览器环境或第三方代码打包后当作本项目的 AGPL 安装包发布。

公开便携 ZIP 使用独立构建目录，只附带明确标注许可的规划器、慕课源码、通用运行时与依赖，保留上游声明、动态库和应用源码。两项外部模块在用户点击启用时直接从固定上游提交下载，核对 `runtime/modules-downloads.json` 中 SHA256，安装不依赖 Git；未将两项完整源码打入 ZIP。Python / Node 的固定版本与校验值在 `portable-version.json`，Qt 补充许可与源码地址在 `runtime/licenses/Qt/`。

PySide6/Qt、Playwright、Selenium 等依赖保留各自许可证，可在安装包元数据及其原项目查看。本仓库不重新授权这些依赖。

如上游作者发现归属错误或希望调整集成方式，请通过 Issue 提供项目链接和具体文件，便于修正。
