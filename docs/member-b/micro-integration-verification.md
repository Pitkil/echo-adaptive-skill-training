# 成员 B 真实微表征服务联调记录

## 1. 联调范围

- 当前版本复核日期：2026-08-25（Asia/Shanghai）
- 完整业务路径联调基线日期：2026-08-20（Asia/Shanghai）
- ECHO 分支：`member/b-micro-signal`
- 检测服务：`echo-wavlm-prototype-v2`
- 服务模式：`real`，不是 Mock
- 模型：冻结的 `microsoft/wavlm-base-plus` 离线权重，由 `models/micro_detector/SHA256SUMS.txt` 校验
- Docker 镜像：`echo-micro-detector-real:competition`
- 离线镜像归档：`offline-images/echo-competition-images.tar`，由同目录 `SHA256SUMS.txt` 校验
- 原型阈值：0.51
- ECHO 接口：`POST /v1/micro/mentor-batches`、任务查询和批次汇总查询
- 数据环境：隔离的临时 SQLite 数据库
- 音频：从受控、已授权评测目录读取；仓库不保存音频、身份信息、密钥或完整任务编号
- 授权引用：`owner-confirmation-2026-08-19`，适用范围见
  `docs/member-b/micro-data-authorization.md`

2026-08-25 使用已锁定依赖构建并启动上述镜像，检测服务 `/health` 返回
`status=ok`、`mode=real`、`detector_version=echo-wavlm-prototype-v2`。向真实容器提交一段无个人信息的
1 秒合成静音 WAV 后，任务从 `queued` 进入 `completed`，`audio_duration_ms=1000`、事件数为 0、
错误为空；脱敏任务 trace 为 `733b5c4ebd28`。这条合法空结果经过 ffmpeg、WavLM 和原型检索的真实
离线推理链路，不是 Mock 或预置响应。

当前代码的微表征服务、汇总、评测和契约测试共 28 项通过。第 2 至第 6 节记录 2026-08-20 已完成的
ECHO 六路径完整业务联调基线；v2 没有改变 HTTP 契约或 ECHO 业务规则，当前版本通过上述真实容器任务
及同一套契约回归测试复核。以下完整业务任务均通过 ECHO 讲师批量入口提交，ECHO 再通过正式检测
契约上传音频和同步事件。

为兼顾复查与脱敏，完整批次号和任务号仅保存在 Git 忽略的本地证据中；文档使用编号的
SHA-256 前 12 位作为稳定引用：

| 证据 | 脱敏 trace |
| --- | --- |
| 已确认说话人批次 | `9f80d9cbe59d` |
| 已确认说话人任务 | `8e8fb1dcef83` |
| 未确认说话人任务 | `f4f68ec1c387` |
| 两文件批次 | `feb7f5931198` |
| 服务降级任务 | `a86538985cdf` |

## 2. 两段录音的真实批量任务

一次批次提交两段 30 秒录音，`accepted=2`。第一段命中同一讲师、同一业务范围内的既有任务，
第二段创建新的真实检测任务。两个任务最终均为：

- 检测状态：`completed`
- 事件同步状态：`synced`
- 录音时长：30000 ms
- 同步错误：无
- 任务错误：无

批次汇总为：

- `hesitation`：2 次
- 信号总数：2
- 犹豫和思考停顿总时长：3000 ms
- 待确认数量：2
- 已忽略数量：0
- 前半段：0 次
- 后半段：2 次
- 变化：+2

复用任务没有造成事件或课次汇总重复累计。

## 3. 已确认说话人路径

输入使用 `speaker_mapping_confirmed=true` 并绑定同组织学习者。状态从
`processing/pending` 变为 `completed/synced`，返回两个可定位事件：

| 类型 | 开始时间 | 结束时间 | 证据状态 |
| --- | ---: | ---: | --- |
| hesitation | 19000 ms | 20500 ms | pending |
| hesitation | 26500 ms | 28000 ms | pending |

两个事件均保留绑定学习者编号，但检测置信度低于 ECHO 的自动确认阈值 0.75，所以保持
`pending`，不会作为已确认证据交给 C，也不会直接修改 U/A/R。
面向学习者或讲师的事件响应使用“检测到犹豫信号，待人工确认”这类固定行为摘要；真实转写
缺失时 `transcript` 保持为空，不把摘要伪装成学习者原话。

## 4. 未确认说话人路径

使用相同可检出录音，提交时不传 `learner_id`，并设置
`speaker_mapping_confirmed=false`。状态同样从 `processing/pending` 变为
`completed/synced`，返回相同的两个可定位事件；数据库中两个事件的 `learner_id` 均为
`null`，证据状态均为 `pending`。

结果只进入匿名课次汇总，不进入任何学习者个人画像，符合说话人隔离要求。

另使用第二段录音验证合法空结果：任务仍为 `completed/synced`，事件数为 0，信号总数为 0，
没有伪造检测事件，趋势仍基于真实 30000 ms 录音时长计算。

## 5. 重复提交

同一讲师在相同组织、学习者、课次、模块、知识点和来源范围内重复提交同一段音频。第二次提交
返回原 ECHO 任务编号，没有创建第二个检测任务；批次汇总仍为 2 个事件，没有重复累计。

## 6. 服务降级

将检测地址临时切换到本机不可达端口后，使用另一段已授权录音创建任务。后台提交结束后的最终
数据库状态为：

- 状态：`awaiting_detector`
- 外部检测任务编号：无
- 事件同步状态：`pending`
- 错误原因：目标端口拒绝连接
- 音频和任务事实：保留，可安全重试

过程中没有使用 Mock 响应冒充成功，也没有伪造事件。查询接口可能先把待重试任务原子重排为
`queued`，后台重试失败后会重新落回 `awaiting_detector` 并保存最新错误原因。

## 7. 结论

完整业务联调基线已覆盖讲师两文件批量、说话人已确认、说话人未确认、合法空结果、重复提交和
服务不可用六条路径；当前 `echo-wavlm-prototype-v2` 又完成真实容器健康检查、实际离线推理任务和
28 项契约回归测试。事件时间、任务状态、同步状态、课次汇总和降级原因均可复查。本记录只证明
产品接入链路和业务边界，不代表现有模型的识别效果已经达标；模型指标以
`docs/member-b/micro-evaluation.md` 的真实评测为准。

检测服务任务结果持久化到 Git 忽略的 `data/micro-detector-real/jobs.json`。服务重启后已完成任务
仍可查询；重启时尚在排队或处理的任务会明确变为 `failed` 并提示安全重提，不会永久停留在
伪处理中。
