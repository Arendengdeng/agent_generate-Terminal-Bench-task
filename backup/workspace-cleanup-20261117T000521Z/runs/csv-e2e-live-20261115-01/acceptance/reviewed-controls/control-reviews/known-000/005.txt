# Test Agent Reliability Baseline Experiment — protocol

- 对象：当前独立 Test Agent；历史 CandidateTask `runs/archive/candidates/acceptance-csv-01`。20 轮固定同一 Contract、Instruction、INITIAL environment、历史模型公开配置和当前原文 V1 Prompt。无 Prompt 修订，无生产代码改动，无历史测试改动。
- 冻结：`frozen/manifest.json` 保存逐文件 SHA-256；`frozen/source/` 保存运行时源文件；`preflight.json` 保存当前 Git 状态、实际 Docker 镜像元数据；模型 API 不提供可固定的后端权重版本、seed 或 temperature，故结果只代表本次端点及配置。
- 生成：4 个并发工作线程，各轮新建 TestAgent、client、messages、FileSet 和输出目录；每轮 `collect` 使用全新 Docker 容器；20 轮无生成重试、无 Oracle 反馈。同一系统 Prompt 和输入不代表模型采样统计上严格独立（服务端相关性未知）。
- 凭据加载预检错误保留于 `setup-attempts/credential-loader-error/`：最初的实验脚本未去除 `.env` 的 `export ` 前缀，20 次请求均在模型响应前 401。修正后从空白轮次重新开始；这些不是有效配置下的实验样本，不进入主分母，也没有删除证据。
- 面板：9 种合法实现 × 3 次重复，24 种违规实现 × 1 次，每轮 51 次（总 1020 次）。在生成完成前后准备面板，静态审查时补充了超域拒绝、无末尾换行和非法 UTF-8 输出三个定向探针；未将面板或发现反馈给 Test Agent，面板并非预注册随机样本。每个实现源代码可审查；25 组独立输入/显式预期先在独立容器核验标签，9种合法对照随后追加内嵌CR/LF至27组复核（依赖违规另加一次 `-I -S` 见证）。有限执行验证结合源代码语义审查支持标签，不声称穷尽证明所有合法输入。
- 9 种合法实现：默认 CSV、数据字段全引号、LF 行尾、DictReader 流式实现、逆序扫描/首次索引算法、成功 stdout 文本、成功 stderr 文本、拒绝超过 1000 条的超域输入、无末尾换行。所有表头保持原始 `email,name`，避免用表头引号争议定义确认缺陷。默认 CRLF 与 LF 均合法。空姓名是空字符串，不允许额外约定为 null/None/丢弃。首次出现顺序为强制要求，排序输出是违规实现。
- 违规面板覆盖大小写/strip/姓名内部空白与大小写/错误去重/排序/空姓名/Unicode 姓名/ASCII 非地址邮箱/1000 条边界/CSV 解析与转义/输入修改/退出码/缺失输出/非标准库依赖/非法 UTF-8 输出。标签依据和违反见证见 `panel/manifest.json` 与 `panel/certification/<id>/cases.json`。无 Oracle/NOP 面板结果代替这些实现。
- 执行：使用原生产 DockerSandbox、固定 verifier 镜像与原 wrapper；每次仅 `/app/clean.py` 进入 `/app`，不包含初始样例文件、Oracle 或其他实现。测试及 fixtures 全量复制到 `/tmp/tests`。全新容器、无网络、非 root、只读根文件系统，资源限制保持不变。仅评估阶段总套件命令预算扩大为 180 秒、日志上限 2 MB；生成配置不变，生成测试自己的 CLI 10 秒 timeout 保持原状。
- Soundness confirmed：经面板核验的合法实现得到 reward=0，记录失败 nodeid、具体断言、Contract 依据、stdout 回溯。`status=error` 单列 Robustness；若错误由不合法 fixture/不当导入约束触发，同时记录误拒绝风险，不伪称有效评分为 0。
- Discrimination confirmed：已确认违规实现完整套件 `status=completed, reward=1`。error/null 不视为通过或成功杀死；Soundness 有缺陷的套件拒绝违规实现，也不能据此证明有辨别力。
- Completeness confirmed：可执行违规见证与全套件错误接受共同确认相应明确语义要求漏检。其他未覆盖边界、弱 R4 检查先标 suspected。对自身已拒绝合法实现的套件额外记录“在基准通过的 node 上无新增失败”诊断，但不作为整套接受或确认完整性缺陷。
- Robustness confirmed：任务格式错误等本应得到断言失败的行为引发未处理测试异常，wrapper 为 error/null；或已执行的 fixture 缺陷。对 timeout、潜在环境依赖等仅有静态风险无执行见证的事项标 suspected。重复 3 次只检查已取样合法面板的可重复性；无变化不证明不会 flaky。
- 静态审查：逐轮阅读全部生成 Python 和 fixtures；导出每个 assert、pytest.fail、raise 的行号、所在函数及源码，检查是否为 Contract 的逻辑后果、fixture 是否合法、R1–R4 coverage 是否真实；生成 `review/assertions.json` 与 `review/source-numbered.md`。缺少反例不得仅因启发式命中提升 confirmed。
- 统计：按轮 presence 计数，同轮同类多个断言/实现/重复不重复累计轮次比例。类别可重叠，因此不能把分类次数相加得到缺陷轮次。主分母 20；生成成功分母另报。确认与疑似单独统计。至少一个确认缺陷的轮次比例只由 confirmed findings 导出。小样本只报告观察频率和 Wilson 区间，不外推其他任务、Prompt/模型版本。
- 人工复核：`human-review.csv`，字段含 proposed_status、reviewer、decision、notes；所有自动发现保留复核入口，疑似项未获裁定则保持 suspected。当前审查由执行实验的 Codex 完成，并非独立人工审计。

补充认证说明：CR/LF补充核验中，认证脚本曾因 read_text 默认换行转换错判合法输出。修复为 read_bytes().decode 后原9种合法对照全部通过27组；原面板及所有评分执行未修改。中间错误认证、未采用替代实现与错误预判的refine_panel脚本均保留作预检审计，不纳入评分测试缺陷或主样本。最终标签以 panel/final-certification-summary.json 为准。
