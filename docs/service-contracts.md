# 服务接口契约

所有服务使用 UTF-8 JSON、ISO 8601 时间、`trace_id` 和版本化 `/v1` 路径。

## 基于多路召回与混合向量的可追溯 RAG 检索引擎

### 检索

`POST /v1/retrieval/search`

```json
{
  "query": "如何评估混合检索？",
  "knowledge_base_id": 1,
  "module_id": 2,
  "knowledge_point_ids": [5],
  "trace_id": "trace-001",
  "top_k": 5
}
```

每个结果必须包含非空 `text`。为了让出处真正可查，元数据必须包含：

- `knowledge_base_id`、`module_id` 和相关 `knowledge_point_ids`
- `source_title`：资料名称
- `source_url`：Microsoft 官方链接
- `source_section`：相关章节
- `chunk_id`：切片编号
- `version` 或获取日期
- `score`：本次检索相关程度

缺少官方链接或章节的结果可以用于内部排查，不能作为正式资源的引用。

### 文档入库

`POST /v1/knowledge-bases/{knowledge_base_id}/documents`

表单字段：`file`、`module_id`、`trace_id`。返回文档编号、任务编号和入库状态。

## SimpleMem

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
`idempotency_key` 和 `memory_id`。同一 `idempotency_key` 再次请求只能返回 `updated` 或
`unchanged`，不得新增记录。同一 `conflict_key` 下出现不同 `idempotency_key` 时返回
`conflict` 和 `conflict_memory_ids`，新结论不得同时成为活跃记忆。

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

开发联调可显式启用 `docker compose --profile micro-mock up --build`。该服务的健康检查会返回
`mode: mock`，固定事件只用于接口联调，不得作为真实学习诊断证据或比赛评测结果。未启用该
profile 时，ECHO 保留任务事实并按外部服务不可用路径明确降级。

- `POST /v1/detection/jobs`：创建单段音频检测任务。
- `GET /v1/detection/jobs/{job_id}`：查询任务状态。
- `GET /v1/detection/jobs/{job_id}/events`：读取标准化事件。

任务状态固定为 `queued`、`processing`、`completed` 或 `failed`。创建任务和状态查询响应
必须包含非空 `job_id` 和任务状态；失败时同时返回 `error_message`。

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
- `POST /v1/micro/mentor-batches`：讲师批量录音
- `GET /v1/micro/mentor-batches/{batch_id}`：批量任务和课次汇总
- `GET /v1/micro/detection-jobs/{job_id}`：任务状态
- `POST /v1/micro/detection-jobs/{job_id}/events`：检测服务使用独立服务密钥回传事件
- `GET /v1/sessions/{session_id}/micro-events`：会话证据

讲师批量上传响应包含稳定的 `batch_id`、去重后的 `job_ids` 和 `accepted` 数量。同一批次中
完全相同的录音只关联并统计一次。`GET /v1/micro/mentor-batches/{batch_id}` 仅允许批次创建者
和同组织系统管理员访问，返回每个任务的检测/同步状态，以及以下课次汇总：各类信号次数、
信号总数、犹豫与思考停顿的总时长、待确认数量，并按录音时间中点比较前后半段信号数量。

事件类型固定为犹豫、猜测、思考停顿、不确定、自我修正和其他。事件包含模块、知识点、
来源、开始和结束时间、可信程度、短转写、证据地址和说话人确认状态。

课次汇总包含各类信号次数、总停顿时间、前后半段变化、待确认数量和已忽略数量。
同一录音重复提交时返回原任务编号，不重复分析和重复计入课次汇总。

未授权录音不创建任务。讲师多人录音未确认说话人时，`learner_id` 必须为空，
事件只能进入课次统计。已经确认但学习者与任务不一致时整批拒绝，不能静默降级为匿名事件。
置信度低于阈值时保持待确认状态。

## 学习画像

`GET /users/{user_id}/learning-insight?module_id={module_id}`

响应固定包含：

- `ability_and_trend`：能力现状和变化趋势，包括每个模块的 U/A/R、正确率和与上一时间段相比的变化。
- `evidence_and_blind_spots`：有作答依据的知识盲区、已掌握知识点、相关题目、得分、时间、
  已确认微表征、长期记忆摘要和判断可靠程度。
- `path_and_resources`：推荐难度、下一知识点、推荐内容形式、推荐辅导方式、学习顺序、
  推荐原因和证据来源。

MIRT 更新接口只接受有效题目和唯一 `attempt_id`。重复编号必须返回原状态，不重复更新。
只有作答证据支持的知识点才能标为盲区。微表征和长期记忆不能直接修改 U/A/R。
大模型只负责把上述结果写成易懂文字；无证据时返回“暂不能判断”，模型不可用时使用固定模板。

## 联调规则

1. 先提交契约样例和测试，再连接真实模型。
2. 超时、空结果和不可用必须返回明确降级原因。
3. 禁止传递数据库对象、本机绝对路径、密钥和完整令牌。
4. 外部服务不能直接写 ECHO 业务数据库。
5. 破坏性字段变化必须升级接口版本。
