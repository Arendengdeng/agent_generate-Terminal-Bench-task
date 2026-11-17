# API 客户端可靠性回归

完成脱敏异常链、URLError.reason/类型/errno、open/read_body/parse_response 阶段及耗时、timeout 和代理标志日志。请求/响应头、API Key 和代理凭证不进入新增日志。HTTP 原始异常不再出现在默认格式化 traceback 的异常链中；脱敏链仍保留于 api_attempt.details.exception。

真实客户端仅对明确的临时传输错误最多重试 1 次，退避 0.5 秒；HTTP（包括 401/402/429/5xx）、证书验证、永久 DNS 和解析错误不重试。重试经共享预算计数，耗尽时不发请求；客户端处理后的异常不会触发现有外层的叠加重试。三个 Agent 调用点仅接入传输计数和 usage，未改 Controller、Contract、测试及 Challenge 业务判定。

失败请求无 usage 时记录 unknown 和尝试编号；已知 token 是小计，非全部费用估算。可选 max_total_tokens 对每次请求做保守预留，未知请求保留其预留量，重试不会把未知消耗算为 0。

全套离线回归：245 项，230 通过、15 外部测试跳过；最终传输故障注入 10/10 通过，覆盖超时/读取失败后成功、重试耗尽、共享预算、HTTP 状态、永久 DNS/TLS、解析错误、脱敏及 Synthesis/Challenge 重试计数和工具不重放。本轮单元回归真实模型调用为 0。新增测试源为 tests/test_client_reliability.py；后续真实 Pipeline 的结果单独保存，不能与 Mock 回归混用。
