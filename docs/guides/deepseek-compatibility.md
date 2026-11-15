# DeepSeek 接口兼容说明

客户端入口为 `synthesis_agent/client.py:OpenAICompatibleClient.complete`，使用 OpenAI-compatible Chat Completions tool calls。

配置地址 hostname 为 `api.deepseek.com` 时：

- 设置 `thinking={"type":"disabled"}`，配合 `tool_choice="required"`。
- 使用 `max_tokens`，值来自 `Config.max_completion_tokens`。
- 不发送 `parallel_tool_calls`。

其他 hostname 保留 `max_completion_tokens` 与 `parallel_tool_calls=false`；不会自动识别第三方代理。Plan、Contract、messages 和工具定义不因兼容分支改变。

HTTP 错误仅提取有大小限制的 JSON `error.type/code/message`，脱敏后报告；不输出原始 body、认证头或未知错误结构。重定向被禁用。任意未标记秘密不能保证被识别。

协议和脱敏测试见 `tests/test_sandbox_client.py`；结果见 `verification.md`（历史验证记录，当前工作区已不存在）。旧 before/after 完整请求快照已清理，请求字段以代码与测试为准。
