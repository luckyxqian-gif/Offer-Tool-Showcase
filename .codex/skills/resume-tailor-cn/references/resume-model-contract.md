# Resume Model 与交接

## 定位

`resume-model-v1` 是内部、格式无关的完整简历内容。它不向用户展示，也不增加用户操作步骤。最终 HTML 中实际使用的文字必须与当前 final confirmed Resume Model 一致；用户在 HTML 中保存的后续编辑仍可成为更新后的最终源文件。

内容模型不得包含字号、间距、页边距、坐标、CSS 类名或页面压缩参数。它可以包含个人资料和照片引用，但只能存在于当前任务临时文件或用户交付文件中，不能保存进通用 Skill。

## 顶层字段

- `schema_version`：固定为 `resume-model-v1`。
- `handoff`：必填的内容版本、Base、变更、锁定、Tailor → Writing 决策和用户确认元数据；未通过校验时不得生成 HTML。
- `personal`：姓名、联系方式行、照片数据或照片路径。
- `education`：教育行。
- `skills`：奖项技能 bullet。
- `practice`：法律实践经历。
- `research`：科研成果项目。
- `self_summary`：简历用严格一行自我评价字符串；可为空字符串。非一行的网申或面试自我表达不得写入。
- `provenance`：可选的来源引用，仅内部使用；不得用它为未完整确认的文字取得渲染资格。
- `section_order`：可选，四个内容栏目键的显示顺序；默认 `education, skills, practice, research`。
- `section_titles`：可选，四个栏目键对应的已确认显示标题；未提供时使用母版默认标题。
- `section_plan`：可选的展示分组；仅在需要跨事实类型组合栏目或在同类条目间交叉排序时使用。它只引用四个事实数组中的条目，不复制或改变经历身份。

## Handoff 确认元数据

`handoff` 必须包含：

- `content_version`：用户实际审阅的完整文字版本号，不得使用“本轮预览”等模糊值。
- `content_origin`：必填的适用性标识，只能是 `tailored` 或 `direct-confirmed`。`tailored` 表示内容经 `resume-tailor-cn` 定向生成，必须携带下文完整 `tailoring_decisions` 和 Gate 状态；`direct-confirmed` 只用于不经岗位定向、由用户直接确认的完整内容。它只区分 contract 适用性，不是第二套 Tailoring Plan，也不得用来规避定向模型校验。
- `base_path`：本轮用户明确指定且有效的 Active Base，或用户指定的当前成品 HTML。仓库不附带个人 Canonical Base；没有用户明确指定的基线时，不得从历史文件或模板推导个人事实。
- `base_sha256`：编制该内容版本时的基线 SHA-256，使用 64 位小写十六进制。
- `change_set[]`：相对 Base 的完整变更清单；每项包含 `node`、`action` 和 `reason`，`action` 只能是 `modify`、`add`、`delete`、`merge` 或 `move`。`reason` 使用简洁自然语言保留该项的 requested change 与 intended effect，目的可验证时同时保留 acceptance condition；不为此新增平行 schema。无变更时使用空数组。
- `locked_nodes[]`：已被完整替换文案、“原样保留”或“其他内容保持不变”锁定的稳定节点路径。
- `global_content_constraints[]`：`content_origin: tailored` 时必填的当前有效全局内容决定快照，无记录时为空数组。每项至少包含 `constraint_id`、可定位的 `subject`、固定 `decision_source: user-explicit`、固定 `scope: all-future-job-versions`、`status`（`active` 或 `restored`）和 `source_ref`；可机械定位时增加 `mechanical_locator.node_id` 或 `forbidden_texts[]`。`restored` 必须同时记录 `restored_by: user-explicit` 与 `restoration_ref`。普通 JD 取舍不得写入此数组。
- `tailoring_decisions`：`content_origin: tailored` 时必填的 Tailor → Writing 最小决策；复用当前 handoff，不另建平行 Tailoring Plan。仅从 DOCX / HTML 恢复基线、且尚未进入定向写作的 `recovered` 模型可以暂时没有 `content_origin` 和该字段；它不能作为 renderer 输入。
- `confirmation`：包含 `status`、`version`、`source` 和 `scope`。正式确认还必须包含固定 `confirmed_by: user-explicit` 与可追溯的非空 `source_ref`；模型自报、Gate PASS 或仅写一个任意非空 `source` 均不成立。Tailor → Writing 阶段的内部工作模型使用 `status: draft`，只能承载 decisions 和待确认正文，绝不能交给 renderer。正式生成输入只有 `status: confirmed`、`scope: complete-current-version`、`version` 与 `content_version` 一致，且上述用户确认来源字段完整时，才能生成 HTML。局部认可、自动微压缩派生状态或历史版本确认均不能替代整版确认。任何 `pending-confirmation` evidence 或可见 `[待确认]` 标记都表示仍有未解决候选新增事实，即使 status 被误设为 confirmed 也必须失败关闭。

从 DOCX 或当前 HTML 提取出的模型不自动获得 `confirmed` 状态。提取只恢复基线；如果需要全面重建，必须完成完整性对比、形成带版本号的完整文字版本并获用户确认。对当前 HTML 的局部节点续改不经过全量 builder，仍须将未点名节点视为锁定。

## Tailor → Writing 最小决策

`handoff.tailoring_decisions` 顶层必须包含：

- `task_mode`：只能是 `single-jd`、`target-family` 或 `generic-target-base`。
- `target_semantic_input`：非空对象，至少包含与 task mode 匹配的 `kind` 和可供 Review 识别当前语义锚点的非空 `summary`。`kind` 对应为 `jd-business-semantic-model`、`target-family-semantic-matrix` 或 `generic-target-semantic-model`。完整建模、来源和限制仍由 `resume-tailor-cn` / `jd-and-selling-points.md` 定义；renderer 只校验类型与非空性，不伪造语义审核。
- `execution_gates`：包含 `target_semantic`、`retrieval`、`architecture`、`writing`、`review` 五个状态。draft 流程可暂存 `FAIL_RETURN_<OWNER>` 以便回退；作为 renderer 输入时五项必须全部为 `PASS`。Render Gate 由 builder 的失败关闭、Make Resume 真实 QA 与 final-deliverable 状态共同完成，不在渲染前伪写一个“Render PASS”。
- `decision_diff[]`：可获得成熟 Base 旧 decisions 且本轮进入 Change Set 的节点需要比较时使用的辅助记录；每项包含 `node`、`changed_decisions[]` 和 `reason`。`changed_decisions` 可为空数组，表示节点虽修改 wording / label，但旧 WHAT 决策全部继承。没有可恢复的旧 decisions 时不伪造本字段。其语义审核归 Tailor / Review，renderer 只校验结构。

`handoff.tailoring_decisions.entries[]` 按最终经历顺序保存本轮保留 entry 的 WHAT：

- `entry_node`：稳定 entry 标识；不得使用会随排序变化的数组索引。与对应内容对象的 `node_id`、`change_set.node` 和 `locked_nodes[]` 使用同一标识体系。
- `inclusion`：该经历本版的保留状态，例如展开、压缩或 Entry-only；不在此扩展 edit mode。
- `priority`：该经历在当前 JD 下的相对优先级，沿用 Tailor 当前的核心 / 次要 / 补充判断。
- `proving_task`：该经历在当前 JD 下主要呈现哪些真实专业工作；不要求跨 entry 唯一或不可替代。
- `content_budget`：Tailor 决定的定性表达预算，只控制句子长短、细节展开程度、非核心修饰压缩和表达密度；可记录计划 bullet 数与展开程度，不使用 token 或精确字符预算。它不得覆盖 proving task、center proposition、selected / must-keep evidence、combination decision、bullet 数或 experience inclusion。预算与 must-keep 内容冲突时 Writing 必须退回 Tailor。
- `field_intent`：本轮新生成或修改该 entry 中间 `field` 时必填的自由文本 WHAT，说明字段要传达的角色/工作领域、经历性质或整段功能定位及真实边界；不是最终成句。为便于机械校验，field 修改须以 `<entry_node>.field` 作为 `change_set.node`；新增 entry 且最终 field 非空时也必须提供。未修改、继续锁定的成熟 Base field 可不提供。
- `bullets[]`：Tailor 已决定生成的 bullet；其数量就是 Writing 必须执行的 bullet 数。

每个 `bullets[]` 项包含：

- `bullet_node`：稳定 bullet 标识，与最终 bullet 内容对象的 `node_id` 一致。
- `work_classification`：Tailor 基于完整 entry facts 确定的自由文本工作分类，不是固定 enum。
- `standalone_basis`：该事项或事实簇在当前版本中独立成 bullet 的定性依据。
- `center_proposition`：该 bullet 唯一的主要工作事实或专业工作重点，不是最终成句或抽象能力评价。
- `selected_evidence[]`：Tailor 已按 Minimum Sufficient Evidence 决定、必须由正文实质承载的信息，不是让 Writing 再筛选的候选池；不要求每项 evidence 在正文中逐项、显式、独立出现，也不与独立动作或短语一一对应。Writing 可以合并、建立主从或在不损失法律和事实意义的情况下压缩，但不得删除核心意义、改变事实、泛化到失去招聘信息价值或重新选材。
- `must_keep_evidence[]`：具体锚点本身不得因压缩而丢失或泛化的锁定数字、具体事项、关键法律事实或其他由用户或上游锁定的内容所对应的 `evidence_key`；必须是当前 `selected_evidence[]` 的子集，普通 selected evidence 不重复标记。
- `combination_allowed`：布尔值。`true` 仅表示 Tailor 已确认当前多个 selected evidence 共同证明同一个 center proposition，Writing 可以自然融合这些已批准 evidence；不授权 Writing 增加证据或重新判断其他组合。`false` 时原则上只能有一个 substantive selected evidence；其他局部信息只能解释该 evidence，不能形成独立证明事项。两个事实分别证明不同命题时，Tailor 必须建立不同 `bullet_node`，不能把它们放在同一 bullet 后标为 `false`。

每个 `selected_evidence[]` 项使用以下最小定位对象：

- `evidence_key`：只需在当前 bullet 内唯一，供 `must_keep_evidence[]` 引用；不是全局 fact ID。
- `source`：事实来源，例如用户运行时提供的权威事实材料、本轮 Active Baseline 或用户本轮确认。候选新增事实在 draft 中使用保留值 `pending-confirmation`；对应可见 wording 必须标记 `[待确认]`。用户确认后改为本轮用户确认来源并移除标记；用户否认后删除或修订相应 evidence 与 wording。
- `section_path[]`：从来源文件稳定标题到具体事项的多级路径；Base 则使用稳定内容节点路径。
- `item_anchor`：路径内可唯一定位的条目标签、编号或短原文锚点，必须落到具体 Action、判断、交付或 Result，不能只写宽泛主题。
- `fact_scope`：该引用允许 Writing 使用的事实边界简述；不得扩展原始来源。

外部事实材料没有全局 stable fact ID 时，复用其稳定多级标题和条目标签。若标题路径仍对应多个事实，`item_anchor` 必须使用编号或足以唯一命中的短原文。Writing 只定向读取定位事实及正确理解它所必需的最小局部上下文；其他事实不自动进入 selected evidence。定位失败、证据不足、上下文冲突或必须加入新 evidence 时 Return to Tailor。

`tailoring_decisions` 在进入 Writing 前形成，并在 Writing、Review、用户确认和最终 Resume Model 中保留；回退到更早 Gate、用户确认或否认候选新增事实时，只由对应 Owner 更新受影响的 evidence、wording、Change Set 与版本，其他已确认节点不得漂移。写作阶段的同一模型保持 `confirmation.status: draft`，用户确认完整文字版本且全部候选新增事实解决后才更新为 `confirmed` 并写入 `scope: complete-current-version`；renderer 对 draft、局部确认、`pending-confirmation` evidence 和残留 `[待确认]` 继续失败关闭。Writing 只能更新对应 `node_id` 的 `field / label / text / runs`，且 `field` 只能在已交接 `field_intent` 时更新；WHAT 无法成文时返回 Tailor 修改 handoff。

正式文字预览与最终渲染必须分别对实际内容模型运行共享的 `validate_resume_content(model, stage, baseline)`。预览返回的 `status + stage + content_version` 是当次调用结果，不持久化为第二套 Gate 或 receipt schema。`execution_gates` 是上游语义 Owner 的状态声明，即使全为 `PASS`，也不能替代预览或渲染时对当前内容版本的实际机械校验。基线模型可用时，validator 只对已有稳定 `node_id` 的 entry field 和 bullet 做 Change Set / locked nodes 差异复核；这不是事实语义对齐或第二份 Facts。

## 内容结构

`personal`：

- `name`：必填。
- `contact_lines`：按最终显示顺序保存 0–4 行完整文字。
- `photo_data_url`：可选，具体生成时注入的 JPEG、PNG 或 WebP data URL。
- `photo_path`：可选，仅供生成器读取并转换为 data URL；不得直接留在最终 HTML 中。

`education[]`：

- `school`：学校及学校标签。
- `program`：专业、学科标签及学位。
- `rank`：排名。
- `date`：日期原文。

以上字段既可为普通字符串，也可为由 `{text, bold}` 组成的 run 数组。默认只把学校字段加粗，除非已确认模型明确保留其他语义加粗。

`skills[]` 与经历的 `bullets[]`：

- `node_id`：参与本轮定向写作时必填的稳定 bullet 标识；必须与 `tailoring_decisions` 中的 `bullet_node` 一致。未参与本轮写作的旧内容可继续依赖既有 locked node。
- `label`：可为空；经历 bullet 有值时是开头的加粗短标签，必须以中文全角冒号 `：` 结尾，不含尾随空白。
- `text`：标签后的完整正文；经历 bullet 有 label 时不得以前导空白起始。
- `runs`：可选；需要保留正文内部已确认的局部加粗时使用，存在时替代 `text`；经历 bullet 有 label 时，拼接后的正文同样不得以前导空白起始。

经历 bullet 的固定展示为 `<strong>短标签：</strong>正文`，冒号与正文之间不插入空格。Renderer 不添加分隔空格；HTML / DOCX 提取器继续在 label / body 边界去除编辑产生的多余空白。正文内部的正常空格、英文术语和数字单位不受影响。

`practice[]`：

- `node_id`：参与本轮定向写作时必填的稳定 entry 标识；必须与 `tailoring_decisions` 中的 `entry_node` 一致。
- `name`：公司或机构名称。
- `field`：entry-level display descriptor，可在事实与 handoff 范围内表达正式角色/工作领域、经历性质或整段功能定位。它不改变 practice 的真实任职/实践身份。
- `date`：日期原文。
- `bullets`：普通正文 bullet。

`research[]`：

- `node_id`：参与本轮定向写作时必填的稳定 entry 标识；必须与 `tailoring_decisions` 中的 `entry_node` 一致。
- `name`：项目名称。
- `field`：entry-level display descriptor，可在事实与 handoff 范围内表达项目属性/奖项、经历性质或整段功能定位。它不把 research 改成企业任职，也不改变项目底层性质。
- `date`：日期原文。
- `bullets`：允许为空；有说明时使用普通正文 bullet。

`self_summary`：

- 顶层字符串，空字符串表示当前模型不展示自我评价；
- 非空时由本 Skill 的“一行自我评价”阶段生成；renderer 将其作为“奖项与技能”内容末尾的一行渲染，使用行内粗体标签“自我评价：”，不得生成独立大标题或第五个栏目；
- 若真实渲染无法保持一行，必须退回上游压缩，不得由 HTML 层自行重写；
- `interview-self-presentation-cn` 生成的非一行自我评价、自我介绍和职业规划不属于简历模型。

`section_plan[]` 用于把展示分组与事实类型解耦：

- `id`：本轮唯一的栏目键；
- `title`：已确认的显示标题；
- `blocks[]`：按显示顺序排列，每块包含 `source` 与 `indices`；
- `source`：只能是 `education`、`skills`、`practice` 或 `research`，用于保留事实身份和对应布局；
- `indices`：引用相应顶层事实数组的零基索引。

使用 `section_plan` 时，四个事实数组中的每个条目必须且只能被引用一次；需要隐藏的内容应在内容确认阶段从最终模型中排除。普通简历继续使用 `section_order` 与 `section_titles`，不为简单改名或排序创建复杂计划。跨类型放在同一展示栏目只改变招聘者看到的证据组合，不把科研变成实习、把项目变成任职经历。

## 合并规则

从现有简历提取出的模型是事实与个人资料底座。`resume-tailor-cn` 已确认的内容覆盖对应栏目、经历、bullet、顺序和语义加粗；未被修改的个人资料、教育、照片和正文继续沿用来源简历。

不得用局部 rewrite 报告冒充完整 Resume Model。交给生成器前必须能从模型独立还原整份简历。

用户已经在成品 HTML 中修改并保存时，该 HTML 是下一轮的最新版编辑基线。局部续改直接修改当前成品的目标节点；需要全面重建时，先运行 `scripts/extract_resume_html.py`，从固定 v5 DOM 恢复文字、正文加粗 runs、栏目标题与顺序、联系方式、照片及 practice/research 原始身份，再合并用户明确要求的变化。不得从旧 JSON 重新生成并覆盖。用户手改产生的表达和结构选择优先，事实字段发生冲突时仍按真实性来源处理。

HTML 提取器不是通用 parser。它只接受本项目 renderer 生成的固定 v5 结构及其中受支持的轻量编辑；遇到未知结构、无法区分的栏目或不受支持的内联标记时失败关闭，不猜测、不静默丢字段。当前模型不支持实践/科研标题字段的局部 runs，因此全面重建只能保留这些标题字段的纯文字；如用户对标题内部做了特殊加粗，应保留当前 HTML 或先明确扩展模型契约。

`handoff` 是必填交接门槛；`provenance` 可额外记录来源引用，但不能替代 `handoff`、用户完整确认或改变正文事实。对本 Skill 的 renderer 而言，`tailoring_decisions` 是业务语义不透明的 metadata：renderer 可以校验其 schema 和可靠机械检查的 cross-field invariant，但不判断其分类、命题、证据或关系语义，不据此重选 evidence、改变 center proposition、bullet 数或责任程度，不合并、拆分事实，也不重新定向目标。浏览器和 renderer 不得自动修改正文；任何文字变化都形成新的 content version 与 Change Set，并在用户完整确认后渲染。只有 CSS、spacing、字体或排版位置变化时，不改 Resume Model。局部反馈只更新对应字段；如果需要全面重建模型，先从当前基线恢复完整内容。

## 完整性检查

生成前至少确认：

- `handoff.content_version` 非空，`content_origin` 合法，`base_path` 非空且不是已停用的三个旧 Canonical Base，`base_sha256` 合法，`change_set`、`locked_nodes` 和适用的 `global_content_constraints` 是数组；
- `content_origin: tailored` 时，`task_mode` 与 `target_semantic_input.kind` 匹配，Gate 1–5 全部为 `PASS`，`handoff.tailoring_decisions.entries[]` 完整；entry / bullet 节点全局唯一并与最终内容对象的 `node_id` 对应；每个定向 bullet 有非空 work classification、standalone basis 和且只有一个非空 center proposition，selected evidence 的 key 唯一且 locator 完整，must-keep keys 均属于 selected evidence，`combination_allowed` 为真正布尔值；
- preview 中 `source: pending-confirmation` 的 evidence 对应可见 wording 含 `[待确认]`；render 中不存在 `pending-confirmation` evidence 或可见 `[待确认]` 标记；
- Change Set 使用 `<entry_node>.field` 新生成/修改 field，或新增 entry 且最终 field 非空时，对应 entry decision 存在非空 `field_intent`；未修改的成熟 Base field 不强制补造。
- `handoff.confirmation.status` 为 `confirmed`、`scope` 为 `complete-current-version`、`confirmed_by` 为 `user-explicit`、`source_ref` 非空，且 `handoff.confirmation.version` 与 `handoff.content_version` 完全一致；
- 非空 `self_summary` 能在“奖项与技能”内容末尾以普通一行渲染；不得出现独立“自我评价”大标题，为空时不生成该行；
- 姓名存在；
- 四个栏目均有明确数组，即使其中某栏为空；
- 每个经历标题的名称、领域或属性和日期字段可区分；
- bullet 的标签与正文没有重复；
- practice / research 经历 bullet 的非空标签以全角 `：` 结尾，label 无尾随空白，text / runs 正文无前导空白；渲染结果中冒号与正文之间没有空格；
- 全部正式可见文字不得包含连续顿号、空并列项或确定性的异常重复标点；该检查独立于下一条顿号上限，并在 preview 与 render 均执行；
- `content_origin: tailored` 的 practice / research 经历正文执行机械 guard：短标签不含“与 / 及 / 或”；以逗号、分号、句号、感叹号、问号或换行分隔的单一分句内不得出现超过 2 个顿号。该顿号 guard 不适用于 skills 等天然枚举字段；判断是否用其他标点规避、标签是否实际包含两个工作主轴仍属于 Writing / Review 语义检查。
- `section_order` 只包含且完整包含 `education, skills, practice, research`，`section_titles` 不产生空标题；
- 使用 `section_plan` 时，栏目 id 不重复，所有 block 来源合法，索引不重复、不越界，并完整覆盖最终模型中的四类条目；
- 日期、数字、机构名称和责任动词保持来源原文或用户已确认版本；
- 照片缺失不会阻塞文本 HTML，但应在最终提示中说明。
- 与已确认基线比较，未获授权的栏目、顺序、联系方式、照片、教育排名、证书、资格、日期、数字、正文加粗和明确保留/删除项没有漂移；active 全局内容约束不得消失，被禁用的节点或文本不得复活。
- 局部 HTML 续改以 `data-node-id` 标识允许节点，并用 `validate_html_scope.py` 比较前后文件；非目标内容或结构漂移即失败。
- 从 HTML 恢复时，提取结果与当前成品逐项比对姓名、联系方式、照片状态、栏目标题/顺序、条目数量、正文文字与加粗；任一不一致都不得用于全面重建。
