# 参与改进

欢迎反馈首次安装卡点、来源失效、界面问题和清晰可复现的错误。提 issue 时说明系统、Python 版本、操作步骤、期望与实际结果；移除密钥和个人数据。

默认不增加核心第三方依赖。新采集器需要说明数据来源、访问方式、失败行为，并添加离线 fixture 测试。运行 `python3 -m unittest discover -s tests -v`。

不要把私人使用中的 config、reports、data 或 Hermes 文件加入 Git。PR 中只放必要代码与公开测试素材。
