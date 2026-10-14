# 简历正文组织与表达

本 Reference 是 HOW 的唯一 Owner。它只消费已经确定的 Resume Architecture 与 Reality Guard 边界，严格执行 W1 → W6；不得重选经历、改变 `work_classification`、center proposition、selected evidence、combination、bullet 数量、entry order 或 content budget。

直接输入为 `resume-model-v1.handoff.tailoring_decisions`。Writing 按 locator 读取 selected evidence 及理解它所需的最小上下文；上下文中的其他事实不会自动获得选材资格。候选新增事实只有在 Architecture 已选入且 `source: pending-confirmation` 时才可成文。缺少会迫使 Writing 重做 WHAT 的字段，或事实不足以支撑命题时，返回 Tailor；出现身份、归因、数字或 Result 问题时返回 Reality Guard。

每个发生改写的 bullet 必须按以下顺序通过，不能先写句子再补检查。

## W1｜STAR / Work Chain（仅 substantive experience bullet）

STAR / Work Chain 只适用于承担经历证明、工作内容证明或项目/实践证明的 `substantive experience bullet`。这类 bullet 在逻辑上必须能够恢复：

`Situation / Task → Action / Judgment → Deliverable / Result`

允许 Situation 隐含、Task 与 Action 合并；没有终局 Result 时，以真实 Deliverable 或 Stage Result 收束；不显式出现 S/T/A/R 字样。

不机械套 STAR 表面格式，但必须形成完整可理解的工作链。禁止只剩 Action 清单、能力词、事项列表，或一串动作看不出工作关系。STAR 是事实记录和逻辑检查方式，不是“一个 STAR 自动成为一个 bullet”的结构算法。

课程列表、奖项、技能、资格、语言、单纯事实展示项、极短稳定配置与纯教育信息不强制 STAR。

## W2｜Target-facing Language

在 Architecture 已确定的 WHAT 内，使用目标岗位、目标公司和目标行业能够识别的成熟职业语言。不得机械继承 Facts 原句、旧标签或原始场景最显眼的词。

可以使用准确的 JD 原词、成熟近义词、上位职业概括和行业表达，只要不改变 Experience Identity、客观 Action、责任、数字或 Result。抽象概括必须由 selected evidence 落地；不得用“复杂、体系、机制、治理、闭环”等空泛评价代替真实工作。

## W3｜Matching Granularity

围绕当前 center proposition，将 Architecture 已选的 1–2 个 proof anchors 自然嵌入工作链，处理语序、主从、例示和压缩。Writing 不重新选择另一组更“好写”的颗粒度。

若 Architecture 选择过多、过少或无法自然成文，Return to Tailor；Writing 不得自行换 anchors。

## W4｜Relation & Parallelism

对 selected evidence 运行 Relation Check，识别并忠实表达：

- parallel；
- dependency；
- action-judgment；
- action-deliverable；
- action-result；
- generalization-after-cases；
- 其他真实主从、因果、阶段或范围关系。

不得把 selected evidence 全部平铺。并列项必须回答同一个分类问题并采用同一分类标准；场景、对象、问题、Action、材料和 Result 不是天然同级。

### 顿号机械规则（仅 substantive experience bullet）

经历正文的同一位置最多出现 2 个顿号。一旦需要第 3 个顿号，Writing Gate 必须失败，且不得仅把它改成逗号、分号、“并”、“以及”或“同时”。必须重新判断颗粒度、Relation 或 evidence 数量，或 Return to Tailor。本规则不适用于奖项、技能、课程、资格或其他天然枚举型字段。

### 确定性连续标点检查（全部正式输出）

`validate_resume_content` 独立拦截连续顿号、顿号与句读标点相邻形成的空并列项、正文开头/结尾的空顿号项，以及明显连续重复的中文句读标点。该检查与“单一分句最多两个顿号”同时存在，不互相替代。在本轮授权节点内先修复再校验；错误位于局部修改范围外时只报告，不改写该节点。

即使标点机械合法，并列项仍必须共同服务唯一 `center_proposition`，并清楚呈现业务对象、个人 Action / Judgment 与有价值的 Deliverable / Result。无法形成工作主线时，Writing 重组主从关系，或 Return to Tailor 重选 Minimum Sufficient Evidence；不得只替换标点或连词规避机械规则。

## W5｜Label & Terminology

正文主线稳定后才生成短标签。

- 一个 bullet 一个工作主轴；
- 经历 bullet 统一写为 `**短标签：**正文`：使用中文全角冒号 `：`，冒号属于 `label`，正文属于 `text` 或 `runs`；冒号与正文之间不得插入空格；
- 短标签禁止使用“与 / 及 / 或”连接两个概念；
- 正文可以正常使用“与 / 及 / 或”，但仍须通过 Relation Check；
- 标签必须是成熟自然的工作概括；
- 不用能力评价代替工作；
- 不把材料对象、项目背景、局部争点或程序步骤随意升级为标签；
- 法律名称、法律关系、案由、合同/交易结构、程序、文书和交付优先使用成熟准确术语。

如果标签需要两个主轴或两个分类轴才能成立，Return to Tailor；不要靠换连接符掩盖。

## W6｜Compression

最后才压缩，顺序固定：

1. 删除重复；
2. 删除低增量程序动作；
3. 合并同类语言；
4. 缩短低价值背景；
5. 压缩措辞。

不得优先删除 JD 匹配锚点、核心判断、1–2 个证明颗粒度或高价值 Deliverable / Result。`content_budget` 不能授权 Writing 改变 WHAT；预算与 must-keep evidence 冲突时返回 Tailor。

## Selected Evidence Coverage

`selected_evidence[]` 是必须由正文实质承载的信息，不是候选池，也不要求一个 evidence 对应一个短语。每个 `evidence_key` 的核心意义须通过对象、依据、判断、Action、Deliverable、Result 或真实关系被承载；`must_keep_evidence[]` 中的锚点不得在压缩中消失。

Writing 可以融合同一命题下的 evidence、调整语序和概括，但不能自行添加 Fact C、改变事实层级、重做 Combination 或将具体事实泛化到失去招聘价值。Architecture 已批准的候选新增事实不是 Writing 自行添加的事实；Writing 应把它直接写成成熟、具体、便于用户判断的目标文案，并在对应具体表述标记 `[待确认]`。同条中的已确认内容照常保留，不因存在一个待确认细节而整体失效。

Writing 不得因旧 Base 原文通顺、事项真实或同属一段经历，就把未进入当前 `selected_evidence[]` 的旧例示、法律问题或业务对象继续带入新 bullet。若 Change Set 要求重开该 bullet，正文只消费 Architecture 本轮选定的 WHAT；发现旧文仍夹带未选事项时返回 Tailor 核对 handoff，而不是自行判断其招聘价值后删除或保留。

Writing 在消费 `selected_evidence[]` 前同时检查 `handoff.global_content_constraints[]`。如 Architecture 交接的 evidence 命中 active 全局删除约束，返回 Tailor 修正 WHAT；Writing 不得自行忽略、恢复或重新解释该约束。

## 唯一预览中的待确认文案

每轮只形成一份完整、最新的定向简历预览。候选新增事实不得另起“推演版”“保守版”或泛化能力问题清单；应按 W1–W6 与 Architecture 决策融入目标 bullet。标记范围以能准确圈定未确认的具体事项为准，避免把整条已确认工作全部标成待确认。

职业化解释无需标记 `[待确认]`。只有新增的具体 Action、对象、交付、结果、数字、责任或其他客观事件使用该标记。若无法区分职业化解释与候选新增事实，返回 Reality Guard 明确状态，不得一律保守降级。

## Entry field 与 sibling 边界

新生成或修改 entry field 时只根据 `field_intent` 命名，不改变人员身份、经历性质或底层 practice / research 类型。未修改的 Active Baseline field 逐字继承；已停用旧 Base 不提供可继承 field。

相同 `work_classification` 的 sibling bullets 不自动合并；Architecture 已确认不同命题和独立价值时分别成文。若只是同一工作换近义标签、同一 locator 重复使用或无法说明独立命题，Return to Tailor。

## Change Set 与锁定

成文前核对 `change_set` 与 `locked_nodes[]`。结构变化的已打开节点完整重跑 W1 → W6；未打开节点逐字继承。局部措辞或标签格式修改只处理实际受影响节点，不重新检索全部经历或重建完整 Target / Architecture；若局部修改触及工作主轴、选材、事实、数字或 Result，则返回相应最早 Owner。Change Set 含 `acceptance_condition` 时，Writing 只完成自己负责的可观察文字条件，页面条件留给 Make Resume。

## 法律与材料对象增量

必须区分“处理了什么材料”和“完成了什么工作”。材料对象只有在解释判断、风险、证据难点、取舍或交付时保留少量代表细节，不能取代工作主轴。

事实只支持起草申请、提交材料、检索类案或核对文件时，使用准确程序动作；没有方案选择、结构设计或机制建设 evidence 时，不写“设计路径、构建机制、建立体系”。

## Writing Gate

依次检查：W1 工作链完整；W2 目标语言成熟且不失真；W3 保留 1–2 个证明颗粒度；W4 关系准确且无第三个顿号；W5 短标签单轴且无“与 / 及 / 或”；W6 压缩未删除高价值锚点；selected evidence coverage 完整；locked nodes 无漂移。

任一失败不得交付未标明状态的 final wording。纯 HOW 问题返回 Writing；WHAT/handoff 问题返回 Tailor；客观事实与归因问题返回 Reality Guard。draft 中的候选新增事实只要成熟成文且明确 `[待确认]`，不构成 Writing Gate 失败；未标记或被写成既定事实则失败。
