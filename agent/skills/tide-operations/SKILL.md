---
name: tide-operations
description: 管理当前 Tide Community 的关注名单、RSS 来源和报告。用户要求新增公司、新增来源、运行简报或排查采集时使用。
---

先读取当前项目 `agent/AGENT.md`。使用任务给出的 Python 运行项目根目录 `tide.py`。
`status` 查看配置，`add-symbol` 新增公司，`discover` 验证来源，`add-source` 写入，`report` 采集。
使用程序返回值验证操作，不直接编辑数据库，不读取密钥，不访问其他项目。
