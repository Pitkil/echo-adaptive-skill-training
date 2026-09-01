# 服务接口契约

所有服务使用 UTF-8 JSON、ISO 8601 时间、`trace_id` 和版本化 `/v1` 路径。

## 基于多路召回与混合向量的可追溯 RAG 检索引擎

ECHO 对学习者和管理端继续提供版本化 `/v1` 接口，但
`apps/api/integrations/punditrag.py` 必须适配 PunditRAG 的两个原生服务：

- 导入服务（默认 `http://127.0.0.1:8000`）：`/knowledge-bases`、`/upload`、
  `/status/{task_id}` 和 `/knowledge-bases/{kb_id}/documents`。
- 查询服务（默认 `http://127.0.0.1:8001`）：`/query` 和 `/health`。

导入和查询使用独立超时预算：`PUNDITRAG_TIMEOUT_SECONDS` 供可能耗时较长的材料导入，
`PUNDITRAG_QUERY_TIMEOUT_SECONDS` 供在线检索，默认 60 秒。检索重试必须在调用方总请求预算内
完成，不能让客户端超时后服务端继续占用业务数据库写事务。

业务数据库中的整数 `knowledge_base_id` 不能直接当作 PunditRAG 的 `kb_id`。
主系统必须把 PunditRAG 返回的字符串 `kb_id` 保存到 `KnowledgeBase.external_ref`，
上传和检索均使用该映射。未建立映射时，材料上传流程先在 PunditRAG 创建知识库并保存映射。

### 检索

ECHO 内部检索调用会转换为 PunditRAG `POST /query`：

```json
{
  "query": "如何评估混合检索？",
  "session_id": "trace-001",
  "scope_mode": "knowledge_base",
  "kb_ids": ["PunditRAG 返回的 kb_id"],
  "document_ids": [],
  "is_stream": false,
  "enable_web_search": false
}
```

`enable_web_search` 固定为 `false`，避免把未审核网页混入官方课程证据。PunditRAG
响应中的 `sources` 由适配器转换为 ECHO 的检索结果；PunditRAG 生成的 `answer` 不作为
ECHO 的最终回复或标准答案。

每个结果必须包含非空 `text`。为了让出处真正可查，元数据必须包含：

- `knowledge_base_id`、`module_id` 和相关 `knowledge_point_ids`
- `source_title`：资料名称
- `source_url`：Microsoft 官方链接
- `source_section`：相关章节
- `chunk_id`：切片编号
- `version` 或获取日期
- `score`：本次检索相关程度

缺少官方链接、章节、版本或本地材料登记记录的结果可以用于内部排查，不能作为正式资源的引用。
正式链接只接受 `learn.microsoft.com`，或 `github.com/microsoft/semantic-kernel` 官方仓库路径。

### 文档入库

ECHO 对外接口为 `POST /v1/knowledge-bases/{knowledge_base_id}/documents`，内部转换为
PunditRAG `POST /upload`。

ECHO 表单字段：`document`、`module_id`、`source_title`、`source_url`、
`source_section` 和 `source_version`。主系统生成 `trace_id`，把文件以 PunditRAG 所需的
`files` 字段上传，并保存返回的 `document_id` 与 `task_id`。

PunditRAG 接受上传只表示异步任务已排队，不能立即标记为 `indexed`。主系统通过
`GET /status/{task_id}` 同步 `pending`、`processing`、`completed` 或 `failed`；只有
`completed` 可显示为已索引。外部服务不可用时保留本地文件和明确降级原因，但不得伪造
外部文档编号、任务编号或成功状态。

## 固定测评编排

`GET /v1/modules/{module_id}/assessment-progress` 是学习者端测评入口的唯一状态来源。
服务端按前测、知识点练习覆盖、阶段测验、巩固重测和后测的顺序返回：

- `state`、`title`、`description`：当前阶段及可直接展示的说明；
- `next_action`：唯一下一步动作；
- `button_label`、`command_text`、`button_enabled`：前端唯一操作按钮；
- `phases`：各用途的题量、已答数量、正确率和最近作答时间。

学习者前端不得自行解锁或选择用途。`GET /v1/quizzes/next` 和 `POST /quiz/submit`
必须再次执行相同的服务端阶段校验，不能相信客户端传入的 `purpose`。阶段测验完成率达到
100% 且正确率不低于 70% 才可解锁后测；未达标时必须先产生一条更新的练习作答记录，
再允许阶段重测。题库缺失时返回明确的内容待配置状态，不得用动态生成题冒充正式固定题。

## SimpleMem

本仓库的可部署实现位于 `services/simplemem`，默认监听 `8020`。服务使用 SQLite 持久化记忆、
合并来源和变更审计；检索会先强制应用组织、用户、项目和模块作用域，再按词项相关度、
完整短语、可靠程度和检索意图排序。服务默认要求非空 `SIMPLEMEM_API_KEY`，所有 `/v1` 请求必须
使用 `X-SimpleMem-API-Key`；`/health` 保持公开供编排器检查。只有显式设置
`SIMPLEMEM_ALLOW_INSECURE_DEV=true` 的回环开发进程可以无密钥启动，生产 Compose 不向宿主机
发布 `8020`。

误区记忆只有在查询词项或完整短语命中内容、知识点编号或元数据值后才能参与排序，可靠程度和意图加权不能
单独让零相关误区进入结果。学习偏好可以在 `echo_guidance` 与 `resource_generation` 中作为明确的
跨主题兜底；干预效果只可以在 `echo_guidance` 中跨主题兜底。

### 三类记忆

- `misconception`
- `learning_preference`
- `intervention_outcome`

### 三种检索意图

- `learner_diagnosis`
- `echo_guidance`
- `resource_generation`

接口：

- `POST /v1/memories`
- `POST /v1/memories/search`
- `POST /v1/memories/{memory_id}/authorize`
- `PATCH /v1/memories/{memory_id}`
- `DELETE /v1/memories/{memory_id}`
- `POST /v1/memories/consolidate`
- `GET /health`

请求必须包含组织、用户、培训项目和模块。查询和合并必须进行权限过滤。
每条记忆还要保存记忆类型、内容摘要、形成依据、形成时间、所属模块和可靠程度。
一次偶然表现不能直接写成长期记忆；合并后必须保留原始来源编号。

长期记忆形成规则固定为：

- 每条记忆至少包含两个语义不同的证据。错误作答按 `attempt_id` 去重，偏好观察按
  `preference_key + session_id` 去重，干预按 `intervention_id` 去重；仅更换 `reference_id`
  不得重复计数。
- `scored_attempt` 明确包含 `attempt_id`、`question_id`、`knowledge_point_id`、
  `is_correct`、`score` 和 `misconception_key`。`misconception` 必须绑定知识点，并由至少
  两次属于该知识点、确实答错且支持同一 `misconception_key` 的作答形成。
- 偏好证据明确包含 `preference_key`、`result_confirmed`、`result_value` 和 `session_id`；
  `learning_preference` 的全部证据必须指向同一偏好、结果已确认且结论不矛盾。
- 干预证据明确包含 `intervention_id`、`intervention_type`、`result_confirmed`、
  `result_value` 和 `session_id`；`intervention_outcome` 必须由至少两次同类、已确认且结论
  一致的干预形成。
- 候选记忆不得混入不属于该记忆类型的证据。平均可靠程度只根据通过类型与一致性校验的
  支持证据计算；低于 `0.65` 时不写入，最终记录也只保留这些支持证据。

### 幂等写入与语义冲突

`POST /v1/memories` 是幂等 upsert，而不是无条件新增。请求必须带两个正式字段：

- `idempotency_key`：作用域、记忆类型、语义领域和归一化内容的 SHA-256；
- `conflict_key`：作用域、记忆类型和语义领域的 SHA-256，不包含结论内容。

响应固定返回 `status`（`created`、`updated`、`unchanged` 或 `conflict`）、
`idempotency_key` 和 `memory_id`。同一活跃记忆的 `idempotency_key` 再次请求只能返回 `updated`
或 `unchanged`，不得新增记录；若该键属于已经删除或合并的非活跃记录，服务返回 HTTP 409 和
冲突记录编号，不得报告成功或自动重新激活。更新记忆后仍永久保留历史幂等键归属，旧请求不能
通过先换键再删除的方式重新创建。同一 `conflict_key` 下出现不同 `idempotency_key`
时返回 `conflict` 和 `conflict_memory_ids`，新结论不得同时成为活跃记忆。

### 修改、删除和合并

修改或删除前，主系统必须调用 `POST /v1/memories/{memory_id}/authorize`。SimpleMem 必须先
查出该 `memory_id` 的原始组织、用户、项目和模块，再与请求作用域逐字段比较；任一不一致返回
HTTP 403，且不得执行 `PATCH` 或 `DELETE`。仅回显调用方传入的作用域不构成授权。

`PATCH` 和 `DELETE` 的响应必须返回 `status`、`memory_id`、组织、用户、项目和模块编号。
更新只接受 `updated` 或 `unchanged`，删除只接受 `deleted`；响应为空、记忆编号不一致、状态错误
或作用域不一致时，主系统必须按 `degraded` 处理，不能记录为成功。

`POST /v1/memories/consolidate` 的响应固定包含 `merged_memory_id`、至少两个去重后的
`source_memory_ids`、至少两个去重后的 `evidence_refs`，以及组织、用户、项目和模块编号。
缺字段或返回其他作用域时，主系统必须按 `degraded` 处理，不能接纳合并结果。

主系统内的生命周期服务统一返回 `completed`、`rejected` 或 `degraded`。规则不满足时返回
`rejected`，SimpleMem 未配置、超时或返回越权数据时返回 `degraded`。业务数据库事实必须先提交，
因此任何 SimpleMem 降级都不能回滚答题记录或改变 U/A/R。

空白检索词、非正数作用域编号、非法知识点编号或超出 `1-30` 的返回数量属于无效请求，生命周期
服务直接返回 `rejected`，不得把无效请求发送给 SimpleMem。同一作答、偏好观察或干预编号出现
互相矛盾的数据时也必须拒绝形成长期记忆，不能采用“保留第一条”的方式掩盖冲突。

生命周期服务本身不持有数据库会话。成员 A 在主系统接入时必须把每次 `degraded` 结果写入业务
数据库的记忆审计表，至少持久化 `memory_record`、失败原因、操作名、发生时间和 `request_id`，
供补偿重试和追踪；仅记录应用日志不满足该要求。

## 微表征检测

### ECHO 调用检测服务

检测服务默认地址为 `MICRO_REPRESENTATION_BASE_URL`，提供：

开发联调可显式启用
`docker compose -f docker-compose.yml -f docker-compose.micro-mock.yml --profile micro-mock up --build`。
覆盖配置让 ECHO 通过容器网络访问 Mock，并等待其健康检查通过。健康检查会返回 `mode: mock`，
固定事件只用于接口联调，不得作为真实学习诊断证据或比赛评测结果。未启用该 profile 时，
ECHO 保留任务事实并按外部服务不可用路径明确降级。

- `POST /v1/detection/jobs`：创建单段音频检测任务。
- `GET /v1/detection/jobs/{job_id}`：查询任务状态。
- `GET /v1/detection/jobs/{job_id}/events`：读取标准化事件。

任务状态固定为 `queued`、`processing`、`completed` 或 `failed`。创建任务和状态查询响应
必须包含非空 `job_id` 和任务状态；失败时同时返回 `error_message`。
检测器能够确定录音时长时，同时返回正整数 `audio_duration_ms`。`completed` 响应缺少该字段时，
ECHO 可以保存事件，但课次汇总必须把前后半段趋势标为不可用并说明原因，不能用最后一个事件
的时间代替录音时长。

ECHO 保存的本地音频通过 `multipart/form-data` 流式上传，文件字段名为 `audio`，其余字段与
`MicroDetectionRequest` 一致，但不得把 `file:///` 本机绝对路径发送给检测服务。检测服务
能够访问的 `http` 或 `https` 音频地址可以使用 UTF-8 JSON 请求提交。

检测服务只返回结果，不能直接写 ECHO 业务数据库。检测服务响应和事件中的 `job_id` 始终表示
`detector_job_id`；ECHO 路由中的 `{job_id}` 表示 `echo_job_id`，两者不得混用。检测编号在任务
和事件中统一限制为最多 100 字符。

ECHO 分别保存检测状态与事件同步状态。创建检测任务直接返回 `completed` 时立即读取事件；
任务为 `completed` 但事件同步状态不是 `synced` 时，后续查询继续重试。合法空事件结果也会
标记为已同步。外部任务完成后读取事件，并在整批事件通过组织、
模块、会话、知识点、来源和学习者范围检查后写入业务数据库。相同 `event_id` 重复返回时
不重复保存；数据库已有同编号事件时只有内容完全相同才视为幂等，内容变化时整批拒绝。
同一批中存在越权或冲突事件时整批拒绝，不允许部分写入。同步超时或服务
不可用时保留原任务状态和失败原因，后续查询可以重试。

### ECHO 主系统入口

ECHO 主系统对外入口：

- `POST /v1/micro/detection-jobs`：学习者单轮音频
- `GET /v1/micro/learners`：讲师或系统管理员读取同组织有效学习者的最小绑定选项（仅 `id`、`username`）
- `POST /v1/micro/mentor-batches`：讲师批量录音
- `GET /v1/micro/mentor-batches/{batch_id}`：批量任务和课次汇总
- `GET /v1/micro/detection-jobs/{job_id}`：任务状态
- `POST /v1/micro/detection-jobs/{job_id}/events`：检测服务使用独立服务密钥回传事件；请求可同时
  携带正整数 `audio_duration_ms`
- `GET /v1/sessions/{session_id}/micro-events`：会话证据

讲师批量上传响应包含稳定的 `batch_id`、去重后的 `job_ids` 和 `accepted` 数量。同一批次中
完全相同的录音只关联并统计一次。`GET /v1/micro/mentor-batches/{batch_id}` 仅允许批次创建者
和同组织系统管理员访问，返回每个任务的检测/同步状态，以及以下课次汇总：各类信号次数、
信号总数、犹豫与思考停顿的总时长、待确认数量，并按录音时间中点比较前后半段信号数量。
单轮音频入口只接受当前学习者自己的 `learner_voice`；讲师录音统一使用批量入口。
讲师录音的 `learner_id` 与 `speaker_mapping_confirmed` 必须同时存在或同时为空，不一致时拒绝请求。
前端确认说话人后必须从 `GET /v1/micro/learners` 返回的同组织有效学习者中明确选择一人；
未确认时清空 `learner_id`，录音只进入课次统计。

事件类型固定为犹豫、猜测、思考停顿、不确定、自我修正和其他。事件包含模块、知识点、
来源、开始和结束时间、可信程度、短转写、证据地址和说话人确认状态。

课次汇总包含各类信号次数、总停顿时间、前后半段变化、待确认数量和已忽略数量。
前后半段按每段录音自己的 `audio_duration_ms` 分界；缺少时长时返回明确的趋势降级状态，
不得根据最后一个事件时间推测录音长度。已忽略事件不计入信号次数、停顿时间和前后半段趋势。
同一录音重复提交时返回原任务编号，不重复分析和重复计入课次汇总。

未授权录音不创建任务。讲师多人录音未确认说话人时，`learner_id` 必须为空，
事件只能进入课次统计。已经确认但学习者与任务不一致时整批拒绝，不能静默降级为匿名事件。
置信度低于阈值时保持待确认状态。

## 语音转写（ASR）

ECHO 可选接入仓库内的轻量 `faster-whisper` 服务，默认模型为多语种
`Systran/faster-whisper-tiny`，CPU `int8` 推理。ASR 只负责把录音转换为文本，
不负责判断答案正确性，也不产生微表征事件。

- 服务地址：`ASR_BASE_URL`，Docker 内默认 `http://asr:8040`。
- `GET /health`：返回服务状态、模型标识和是否已加载；模型采用首次转写时懒加载。
- `POST /v1/asr/transcribe`：以 multipart 字段 `audio` 上传录音，可选 `language`，返回
  `text`、`language`、`duration_ms` 和 `model`。

ECHO 创建微表征录音任务后，会并行排队 ASR 和微表征检测。转写结果保存在
`micro_detection_jobs` 的 `transcript` 字段，并带有 `transcription_status`、
`transcription_error` 和 `transcribed_at`。ASR 不可用时保留录音任务和明确降级原因，且不得把
摘要或错误信息伪装成学习者原话。
`video_checkpoint_id` 仅在学习者从冻结的视频口述检查点进入时填写。转写文本本身不直接更新
MIRT；学习者必须核对或纠错后调用
`POST /v1/video-checkpoints/{checkpoint_id}/oral-attempts`，提交 `job_id`、
`confirmed_transcript`、唯一 `attempt_id` 和可选 `session_id`。服务端验证录音归属与检查点绑定，
AI 只返回匹配的冻结要点编号，分数与是否通过由服务端计算；AI 不可用或结构无效时失败关闭，
不创建作答记录。相同 `attempt_id` 不重复更新 MIRT。模型权重只写入 Docker 的
`asr-model-cache` 卷，不进入 Git。

## 学习画像

`GET /users/{user_id}/learning-insight?module_id={module_id}`

响应固定包含：

- `ability_and_trend`：能力现状和变化趋势，包括每个模块的 U/A/R、最近 30 天正确率、用于画像
  分类的累计可评分作答正确率 `profile_accuracy`，以及与上一时间段相比的变化。
- `evidence_and_blind_spots`：有作答依据的知识盲区、已掌握知识点、相关题目、得分、时间、
  已确认微表征、长期记忆摘要和判断可靠程度。
- `path_and_resources`：推荐难度、下一知识点、推荐内容形式、推荐辅导方式、学习顺序、
  推荐原因和证据来源；同时包含 `learner_profile` 和 `primary_content_decision`。

`learner_profile` 只根据允许更新 MIRT 的已判分作答、U/A/R、累计正确率和有作答证据的盲区
归入 P1、P2 或 P3。分类使用的作答次数、正确率和证据必须来自同一组累计作答，不能因最近
30 天没有新作答而改变画像。少于两次可判分作答时 `type` 必须为 `null` 且
`evidence_status` 为 `insufficient`，不得根据长期记忆或微表征猜测能力类型。证据足够时返回
`evidence_count` 和 `evidence_refs`；每条引用至少包含作答编号、题目编号、知识点、得分、
是否正确和作答时间。三类画像向内容生成方提供不同的 `explanation_depth`、`step_detail` 和
`support_level`，固定样例见 `docs/member-c/learner-profile-samples.json`。

`primary_content_decision` 每轮只允许一个主要动作。未完成前测时返回
`action=complete_pretest`、`resource_count=0`；证据足够时返回 `action=generate_resource`、唯一
`resource_type`、`resource_count=1` 和 `selection_policy=single_most_needed`。三种资源是系统能力
范围，不表示每次同时生成三份。成员 A 的生成编排必须按该唯一决定生成和校验当前资源。

### 个性化资源与发布门禁

`POST /v1/resources/generate` 每次只生成一个 `resource_type`（`custom_note`、`practice_guide`
或 `staged_test`），并保存 `TurnExecution` 中四个后台 Agent 的输入摘要、输出、失败原因和
`persisted_in_system`。资源状态枚举为 `draft`、`pending_review`、`verified`；自动检查通过后
只能进入 `pending_review`，不得直接发布。

请求可带 `user_input`（最长 4000 字）描述学习目标、场景或约束。它是学习数据而不是系统指令：
系统会将其限制在当前课程、模块、知识点和已登记的官方材料范围内，用于检索查询、个性化生成
以及审计摘要；不得把它当作越权指令。课程 rubric 只提供检索提示和本轮语义复核要求，不以字面
关键词命中直接决定正式通过。引用编号、官方域名、JSON 结构、代码语法和阶段测试结构由程序
确定性校验；是否真正回答用户问题、同义表达是否覆盖要求、专业结论是否得到本轮官方证据支持，
由独立模型以结构化 JSON 复核。普通对话只检查本次问题触发的要求，不强迫回答同一知识点下所有
概念；完整学习资源才检查知识点核心覆盖。模型复核不可用或返回无效结构时记录
`lexical_fallback` 并失败关闭，不得用词表兜底冒充 AI 通过。新课程不会套用 Semantic Kernel 的
rubric，课程负责人应在启用专项检查前配置本课程要求。

`GET /v1/resources` 返回最近一次 `verification_passed`、`verification_issues`、
`verification_details` 和完整 `verification_history`。检查明细至少覆盖事实声明与证据对齐、引用
编号和官方域名、代码语法、实操步骤的 action/expected 字段，以及阶段测试的理解/应用/推理维度。
检查失败时优先根据失败原因进行一次定向模型重生成并增加 `retry_count`；模型不可用时才使用
保守的确定性修复，并在检查记录中保留原因。每次结果独立保存。

讲师或系统管理员调用 `POST /v1/resources/{resource_id}/publish` 执行人工发布门禁；只有最近一次
自动检查通过的资源允许变为 `verified`。学习者无权发布。没有官方证据的资源保持 `draft`，不得伪造
引用或发布。

### 学习反馈与用户级删除

学习者确认学习偏好或干预效果时调用 `POST /v1/learning-feedback`。业务事实先写入数据库，再由
SimpleMem 生命周期服务尝试写入；响应和 `MemoryAudit` 必须记录 `completed`、`rejected` 或
`degraded` 及失败原因。可评分题目连续两次对同一知识点答错后，主系统自动形成
`misconception` 候选；第一次错误不得写入稳定误区。

`POST /v1/users/me/data-deletion` 使用 `request_id` 幂等，需显式 `confirm=true`。系统删除该用户
拥有的会话、消息、作答、U/A/R、资源、语音事件、上传文件和视频，并分别调用 SimpleMem
`DELETE /v1/memories/scope` 与 PunditRAG `DELETE /documents/{document_id}` 清理外部数据。共享的
正式课程材料不删除。响应状态为 `completed` 或 `completed_with_degradation`，后者必须返回外部
失败原因；`GET /v1/users/me/data-deletion/{request_id}` 可查询审计结果。

MIRT 更新接口只接受有效题目和唯一 `attempt_id`。重复编号必须返回原状态，不重复更新。
只有作答证据支持的知识点才能标为盲区。微表征和长期记忆不能直接修改 U/A/R。
大模型只负责把上述结果写成易懂文字；无证据时返回“暂不能判断”，模型不可用时使用固定模板。
成员 C 的 10 组跨会话长期记忆差异案例见 `docs/member-c/memory-difference-cases.json`，所有案例
均要求长期记忆和微表征不直接改变 U/A/R。

## 联调规则

微表征检测任务的提交失败分为两类：未配置、连接失败、超时、HTTP 429 和 HTTP 5xx
属于临时不可用，ECHO 保存最近失败原因并将任务保持为 `awaiting_detector`；请求参数错误、
HTTP 4xx（429 除外）、响应格式错误和业务范围不一致属于确定失败，任务进入 `failed`。
查询可重试任务或重复上传相同录音时，ECHO 可以原子地重新排队；并发请求只能触发一次外部提交。
无外部任务编号且超过 60 秒仍处于 `queued` 的任务视为提交租约过期，查询时可以原子回收并重新提交。
事件响应格式错误、事件编号冲突和业务范围不一致会终止自动同步并将任务标记为 `failed`。

录音去重范围固定为 `organization_id`、`learner_id`、`session_id`、`module_id`、
`knowledge_point_id`、`source_type` 和 `audio_sha256`，`created_by_user_id` 仅用于权限与审计。
视频口述检查点录音额外包含 `video_checkpoint_id`，避免同一音频在不同检查点间被错误复用。
跨讲师命中已有任务时不创建第二个检测任务，也不向后上传者公开原任务详情和检测事件。
`POST /v1/micro/detection-jobs` 固定返回 `job_id`、`status`、`source_type`、`is_duplicate`
和 `retry_scheduled`。跨讲师命中时 `job_id` 为 `null`、`status` 为 `already_submitted`；
该状态只表示脱敏后的提交结果，不是检测器任务状态。

1. 先提交契约样例和测试，再连接真实模型。
2. 超时、空结果和不可用必须返回明确降级原因。
3. 禁止传递数据库对象、本机绝对路径、密钥和完整令牌。
4. 外部服务不能直接写 ECHO 业务数据库。
5. 破坏性字段变化必须升级接口版本。
