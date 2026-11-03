# 安装独立 Hermes Agent

潮汐的采集、规则报告、AI 整理和网页不依赖 Hermes。Hermes 用于理解自然语言任务并调用潮汐工具，例如“帮我关注 AAPL”“查找微软官方 RSS 并接入”。

## 安装前

- Python 3.11+、Git、能访问 GitHub 和 Python 包源的网络。
- 支持 OpenAI 兼容 Chat Completions **工具调用**的模型服务。
- 安装及模型调用需要网络。网盘包不包含 Hermes 运行时、Python 安装器或任何模型额度。

## macOS / Linux 推荐路径

macOS 双击 `安装 Hermes.command`；或进入潮汐目录执行：

```bash
python3 scripts/install_hermes.py
```

安装器获取官方锁定提交 `c4b2beea778ceca1462b91282589338b5e80781f`，使用上游 uv.lock 在项目 `.tools/hermes-venv` 创建独立 Python 3.14 环境；必要时下载该解释器。不会调用全局 `hermes setup`，不会修改 `~/.hermes`，不会启用旧 profile，也不会复制你的旧凭证。

下载失败时查看终端错误。GitHub 与包源可达性要分别检查。只使用你信任的网络或包源；本项目不附带代理、不自动改网络设置。

完成后重新启动潮汐。在设置里填写 Base URL、模型名称、API Key，并勾选允许 Agent 使用终端与文件工具。

## 已安装 Hermes

默认检测 PATH 中的 `hermes`；也可以在设置里填写可执行文件绝对路径。项目专用 `.tools` 安装优先于其他路径。运行参数依赖 `chat -Q -q --provider --toolsets --max-turns`，旧版本可能不兼容。

即使复用可执行程序，也会使用 `data/hermes/profiles/tide-community` 的独立 HERMES_HOME。模型密钥来自本项目设置，不继承其他服务商密钥。

## Windows

基础潮汐网页、规则报告、RSS 和模型整理可以直接用 Windows Python。

本版 Hermes 安装器选择 WSL 路线：先按微软官方说明安装 WSL/Ubuntu，在 WSL 内准备 Python 3.11+、Git，将项目解压到 WSL 用户目录，执行上述安装命令，再在同一 WSL 目录运行 `python3 tide.py web`。Windows 浏览器访问输出的本地地址。

不要混用 Windows 的 Hermes 可执行路径和 WSL 的 Python 路径。本版不承诺 Hermes 原生 Windows 安装兼容性。

## 第一次 Agent 任务

打开「潮汐 Agent」，输入：

> 请添加 AAPL 到关注名单，并说明已匹配的来源。

完成后去「我的关注」核对结果。可靠的执行证据是实际配置和工具返回，不是 Agent 自己声称成功。

接着可以尝试：

> 请验证 https://blogs.microsoft.com/feed/，如果可用就接入并关联 MSFT。若已存在，不要重复创建。

## 权限和费用

独立 profile 是配置隔离，不是系统沙箱。Hermes 的终端和文件工具以当前系统用户权限运行。工作契约要求仅操作本项目，但不是强制文件系统隔离。不要让它处理恶意任务；更严格的隔离需另外部署容器或专用系统用户。

每个任务最多 8 轮、300 秒。时间限制和轮数限制不是费用硬上限，模型价格以服务商为准。遇到命令审批需求时，不会自动开启 yolo 模式绕过。

用户请求与工具结果会发送给所选模型服务商。会话在 data/hermes 下保留，不进入发布包。
