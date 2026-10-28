# 太空死灵作家助手 · Necron Scriptorium

一个轻量、本地优先的 Windows AI 小说写作客户端。它把书籍管理、章节编辑、结构化设定、前文精选、审稿和人物小传放在同一个桌面窗口里，并直接支持 Kimi 开放平台与 Kimi Code。

> **定位**：不是功能最多的全自动小说工厂，而是一个 **16 MB 左右、无需 Node.js、无需 Docker、开箱即用的单文件写作客户端**。你可以把它视为复杂 AI 小说工作台的轻量替代方案。

## 功能

- Windows 原生桌面窗口（WebView2 + pywebview），不弹浏览器地址栏和控制台。
- 书籍、章节、正文编辑、字数统计与自动保存。
- 删除书籍前自动导出整本 TXT 备份，随后切换到下一本书。
- 历史版本和恢复；AI 替换正文前自动保留旧版本。
- 批量导入 TXT/Markdown，兼容起点导出的“第X章”格式并自动拆章。
- 章节级前文精选：默认最多 5 万字，优先最近章节与手动指定章节，按相关度补充。
- 结构化设定库：角色、背景、势力、地点、物品。
- 角色档案：姓名、别名、性别、性格、标签、背景、人物小传。
- 人物小传一键扩写，生成后自动保存。
- AI 功能：开书、大纲、人物、写本章、续写情节、续写正文、审稿、去 AI 味、拆书。
- 先情节、后正文的两阶段续写。
- AI 状态按书独立记忆：功能、工作流、写作要求、输入框高度、AI 输出、滚动位置和参考选择在刷新或切换书籍后分别保留。
- 本地优先：书稿、设定和设置都保存在本机 SQLite 数据库。
- 支持 Kimi 开放平台与 Kimi Code 两套接口。

## 快速开始

要求：Windows 10/11、Python 3.10+、Microsoft Edge WebView2（Windows 11 和大多数 Windows 10 已预装）。

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python desktop.py
```

`desktop.py` 会启动原生窗口。数据默认保存到：

```text
%USERPROFILE%\Documents\NovelStudioData
```

也可以用浏览器模式调试：

```powershell
python app.py
```

## 打包为 EXE

```powershell
python -m venv .desktop-build\venv
.desktop-build\venv\Scripts\activate
pip install -r requirements-build.txt
python build_desktop.py
```

产物位于 `dist\太空死灵作家助手.exe`。图标源文件位于 `assets/icon.ico`。

## 配置模型

点击右上角 **API 设置**，选择 Key 所属的接口：

| 接口 | API 地址 | K3.1 Pro 模型 ID |
|---|---|---|
| Kimi 开放平台 | `https://api.moonshot.cn/v1` | `kimi-k3.1-pro` |
| Kimi Code | `https://api.kimi.com/coding/v1` | `k3.1-pro` |

开放平台按 Token 计费，Kimi Code 使用会员额度。两种 Key 不能混用。

> API Key 只保存在本机 `NovelStudioData\studio.db`，不会写入日志或上传。它不是操作系统密钥链加密存储，因此不要分享这个数据库文件。

## 可选 skills

源码仓库**不包含第三方 skills**，避免未经确认再分发。没有安装 skills 时，程序使用 `novel_studio/skill_engine.py` 中的原创精简写作规则，AI 功能仍可使用。

如果需要更完整的方法库，请自行阅读对应项目许可证后，把 skill 文件夹放入 `skills/`：

| Skill | 上游项目 | 许可证 |
|---|---|---|
| `story-long-write`、`story-long-analyze`、`story-review`、`story-deslop`、`character-designer` | [zenstory-ai/oh-story-claudecode](https://github.com/zenstory-ai/oh-story-claudecode) | MIT |
| `chinese-novelist-skill` | [PenglongHuang/chinese-novelist-skill](https://github.com/PenglongHuang/chinese-novelist-skill) | MIT |
| `webnovel-writer` | [lingfengQAQ/webnovel-writer](https://github.com/lingfengQAQ/webnovel-writer) | GPL-3.0 |
| `novel-creator-skill` | [leenbj/novel-creator-skill](https://github.com/leenbj/novel-creator-skill) | 上游未发现明确许可证，仓库不提供 |

详见 [NOTICE.md](NOTICE.md) 与 [skills/README.md](skills/README.md)。

## 数据与安全

- 书稿只保存在本机，不经过本项目的服务器。
- AI 请求直接发送到用户配置的模型接口。
- 删除章节前会在 `NovelStudioData\已删除章节` 留 TXT 备份。
- 自动分章、AI 替换和手动留版本都会先备份旧正文。
- 本项目不包含遥测。

## 当前限制

- 桌面封装目前面向 Windows。
- 前文选择是基于最近章节、手动选择和文本相关度的轻量算法，不是向量数据库 RAG。
- 不包含多 Agent 自动导演、知识图谱或全自动整本生产。
- 目前是单人本地应用，没有账号系统、云同步或协作功能。
- 依赖用户自己的模型 API Key 和额度。

## 技术栈

- Python 3 标准库：HTTP 服务、SQLite、流式 API 客户端。
- HTML/CSS/JavaScript：本地写作界面，无前端构建步骤。
- pywebview + Edge WebView2：Windows 原生窗口。
- PyInstaller：单文件 EXE。
- Kimi OpenAI-compatible Chat Completions API。

## 声明

这是一个非官方项目，与 Games Workshop、Kimi、月之暗面均无隶属或背书关系。Warhammer 40,000、Necron 及相关名称属于其各自权利人。本仓库不包含官方 Logo、插画或其他受版权保护的素材，界面仅为黑金属与墓绿配色的原创致敬设计。

## License

原创代码采用 [MIT License](LICENSE)。第三方 skills 不随本仓库分发，并继续遵循各自许可证。
