# Validator / QA 与 make-resume 交接

本 Reference 只做结果验证，不是第二个 Tailor、Business Mapping、Reality Guard 或 Writing。它不得修改 WHAT/HOW、重选事实、重算 Minimum Sufficient Evidence、重写正文、改变 Classification、修复页面或补 contract 字段。

## Fail-closed 协议

每轮只产生：

- `PASS`：所有适用检查通过；
- `FAIL_RETURN_<OWNER>`：仍有失败项，返回唯一 Owner。

每个失败项只记录失败对象、具体原因和唯一 Owner。修复后从受影响的最早 Gate 重跑；Review 不给出替代 evidence 或具体重写方案。

## 验收重点

Review 不接管完整推理，但必须用当前输入与实际预览结果检查：

1. 当前有效 Candidate Facts 是否已全文读取，而非由标题扫描或关键词命中替代；
2. JD、Company、Industry 与 Organization Context 是否独立完成，未被候选人现有经历反向降级；
3. 是否充分发现已有经历中的高价值 Business Affinity 和业务联系；
4. 是否主动检查可能遗漏的相关工作及具有具体业务依据的专业推演空间；
5. 是否存在独立的 bullet 内低相关证据残留：某段经历总体相关，但列举的业务对象、法律问题、Action、Judgment、Deliverable 或 Result 对当前 JD 缺少增量价值，并挤占同簇更高价值事项；
6. 是否因 Base 旧主轴、旧例示或旧事实组合而低估真实经历，或只做少量措辞替换；
7. 是否将职业化解释误判为未经确认的新增事实，或反向把待确认新增工作升级成已确认事实；
8. Architecture 是否按当前 JD 充分展开核心证明，且 entry、work classification、center proposition、selected evidence、proof anchors、content budget 与 standalone bullet 决策具有实质匹配价值；
9. Architecture 已选 WHAT 是否在正文完整落实，且未夹带本轮未选的 Base evidence；
10. 是否完整落实用户明确提出的结构、保留、删除、展开和锁定要求；
11. 当前有效的用户全局删除约束是否已加载；Architecture、唯一完整预览与最终正文中是否发生节点、原文或同义概念复活；没有明确恢复指令时不得恢复；
12. 适用节点的 W1 → W6 是否执行；STAR 和“单一分句最多两个顿号”只检查 substantive experience bullet；连续顿号、空并列项和异常重复标点则检查全部正式可见文字；语义性并列堆砌不得靠替换标点规避；
13. deterministic validator、ATS coverage、Resume Model contract 与 Render QA 是否通过，且不存在“机械校验通过但最终简历仍缺少明显岗位匹配价值”的结果。

Review 不要求连接档位、mapping 强弱标签、过细 retrieval 状态、完整推理 ledger、逐 atom 零遗漏证明或过细 discovery provenance。Facts 全文阅读的验收是当前运行已实际覆盖全文并能在 Mapping / Architecture 中正确调用各段经历，不新增模型自我声明的 `facts_read: PASS` 字段。

Review 不复核已确认 Facts 的来源、归属或独立因果。成果价值与选材由 Architecture 决定；用户锁定的数字和成果不得被下游 Owner 静默删除。

## Architecture 与 Writing 对照

以 `resume-model-v1.handoff.tailoring_decisions` 为交接记录，对照 entry、bullet、field intent、selected evidence、must-keep evidence、combination、结构、排序、预算、Change Set 和 locked nodes。

- handoff / WHAT 缺失或漂移：Tailor；
- 客观事实、来源、归因、责任、数字、Result 或敏感信息失败：Reality Guard；
- WHAT 正确但 W1–W6、Relation、Coverage、标签、术语或压缩失败：Writing；
- ATS 关键词覆盖复核失败：ATS 或其应返回的上游 Owner；
- 模型合法但 HTML 未忠实消费：Make Resume。

Review 不自行合并 sibling bullets、修改标签、重选 evidence 或决定页面删减。相同 work classification 本身不是失败；只有 handoff 无法支持其独立命题或 evidence 只是换标签复用时返回 Tailor。

低相关证据残留是独立的 Architecture 失败。若 entry 和 center proposition 总体成立，但正文列举了不适合当前 JD 的代表法律问题或事项，Review 返回 `FAIL_RETURN_TAILOR`，要求 Architecture 在同一事实簇中重新选择 Minimum Sufficient Evidence；不删除整个 entry，不把真实事项交给 Reality Guard 否定，也不由 Review 或 Writing 直接改写。该判断必须随当前 Target 重新执行，不形成永久禁词。

Reality Guard 失败只返回该 Owner 修正客观主张、归因或 wording，不授权 Review 或 Reality Guard 删除真实数字、成果、entry、bullet 或 selected evidence。选材变化只能由 Resume Architecture 决定，并继续服从用户明确保留项与 locked nodes；确实无法在不虚构事实下同时满足时，标出具体冲突等待用户决定。

## Preview、Change Set 与确认

验证唯一版本号完整预览、变动标记、用户指令核销、change set、locked nodes、当前全局删除约束、confirmation 与 content version 一致。候选新增事实必须在对应 wording 标记 `[待确认]` 并保持 draft；职业化解释不得仅因 Facts 缺少同词被标为待确认。未进入 Change Set 的成熟节点不得漂移。局部认可只确认对应节点，不得把整份最新版写成 confirmed；只有用户实际确认完整当前版本时，`confirmation.scope` 才能是 `complete-current-version`。

局部修改只从受影响的最早 Owner 重跑相应节点与必要下游；Review 仍检查最终合同和全部继承状态，但不把机械复核既有 PASS 状态解释为重新执行全量 Target、Retrieval、Mapping 或 Architecture。

Active Baseline 中的事实正确但当前 Target Business Model 显示其主轴低估真实经历价值时，应检查该节点是否可以合法进入 Change Set。若它受用户明确指令或 Candidate Policy 稳定硬约束锁定，只能标为待确认，不得静默修改。已停用的 Market / SOE / Bank Canonical Base 不得被恢复为 baseline。

用户确认前 `confirmation.status: draft` 必须阻断 renderer；任一 `pending-confirmation` evidence 或可见 `[待确认]` 标记都阻断正式渲染。用户确认或否认后只更新对应候选内容，其他已确认节点继续受 Change Set / locked nodes 保护；confirmed 版本须与当前 content version 一致，且确认范围必须覆盖完整当前版本。

用户说“只改这里”“其余不变”时，Review 必须确认 Make Resume 以用户指定的最新 HTML 为基线，目标 DOM 节点清晰，并对非目标节点的内容、结构、日期、数字和正文加粗做了修改前后比较。范围外发现的问题只列出，不授权顺手修复；出现任何未授权漂移即 `FAIL_RETURN_MAKE_RESUME`。

## Resume Model contract

`make-resume-cn/references/resume-model-contract.md` 是 schema、字段类型、状态与跨字段不变量的唯一 Owner。Review 只调用或确认现有 deterministic validation 结果，不复制字段清单、不补 contract 字段、不修复 schema。Tailored execution gates 继续按现有 contract fail closed，不改变 renderer 接口。

## 一页与 Render QA

Tailor 决定内容预算、结构和 evidence；Writing 只在既定 WHAT 内压缩；Review 只验证；Make Resume 独占 HTML/CSS、A4、标题孤立、横向碰撞、换行、安全 spacing 与真实页面测量。

若 Change Set 的 acceptance condition 是减少一行、腾出空间或降低页面占用，Review 只核实 Make Resume 已对修改前后真实页面结果作比较并达成条件；不得以字符数、已合并或缩小视觉参数代替真实验收。

任一未解决问题阻断 final deliverable。
