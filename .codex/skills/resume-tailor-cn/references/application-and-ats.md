# ATS lexical seeds 与最终 coverage

本 Reference 只维护 ATS 的词面入口、自然覆盖和结构化文本复核。它不拥有 Target Business Model、Business Mapping、`work_classification`、Facts、Experience Selection 或 Writing。

## 修改前：lexical seeds

从具体 JD 提取：硬性条件、岗位/职能名称、核心职责、高权重业务/行业/专业术语、工具/流程/对象/交付、加分项和一般软性要求。JD 原词、成熟近义词及中英文对应表达交给 Target Business Model 与 Business Mapping；ATS 不判断 semantic、hierarchical、adjacent、Business Affinity 或 Reverse Projection。

Generic Target Base 没有具体 JD 时不生成具体 ATS requirement、score 或伪共同 JD。Target Family 对每个真实 JD 分别提取 seeds，再做 resume-level coverage。

## 修改后：keyword coverage

在 Architecture 与 Writing 完成后，检查有真实事实支持的重要要求是否以招聘者能识别的形式可见，并验证 Resume Model 可结构化提取。一个高权重术语通常有一处自然事实承接即可；确无事实时保留缺口，不堆词。

Cross-surface 检查 Experience、Research、Skills、Self-summary、Entry field 与 Bullet label 的可见性和重复。只有明确硬门槛或现有位置明显隐蔽，且新增位置的 visibility 增量高于页面成本时，才保留跨 Surface 重复。

调用链为：

`ATS lexical seeds → Target Business Model / Business Mapping → Resume Architecture → Writing → ATS coverage`

ATS 查出高价值遗漏时返回 Business Mapping 或 Architecture，不自行检索事实、重做 classification、升级责任或注入关键词。

## 诊断与边界

如用户要求，可给启发式 coverage 诊断，但必须说明它不是企业 ATS 分数、过筛率或录取概率。诊断应列自然覆盖、结构风险和真实缺口，不反向驱动关键词堆砌。

最终检查硬性条件、核心职责、专业术语、标题/标签/正文一致性、重复、未覆盖缺口、稳定字段无漂移、模型文本可解析性及招聘公告明确的文件/命名要求。
