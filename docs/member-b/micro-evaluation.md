# 成员 B 微表征评测说明

`micro-difference-cases.json` 冻结 10 组接口与产品差异案例，覆盖 P1、P2、P3、M1、M2、M3、
学习者语音、讲师录音、授权、说话人、重复提交、空结果和服务降级。案例不含真实音频，不能用于
检测准确率指标。

真实检测效果使用人工标注的候选时间窗 JSON 计算。输入必须包含：

- `dataset_version`：标注数据版本；
- `detector_version`：真实检测器或模型版本；
- `detector_mode`：必须不是 `mock`；
- `observations`：候选时间窗列表。

每个 observation 固定包含 `observation_id`、`case_id`、`event_type`、`expected`、`predicted`、
`source_ref`、`start_ms` 和 `end_ms`。`source_ref` 应指向受控数据集中的录音编号，不得把真实音频
提交到 Git。

运行：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_micro_detection.py `
  data\micro-evaluation\labeled-observations.json `
  --output data\micro-evaluation\metrics.json
```

报告包含总体和分事件类型的 Accuracy、Precision、Recall、F1，以及每个误检、漏检对应的案例、
录音编号和时间范围。Mock 输出会被脚本拒绝，避免把接口联调结果伪装成真实检测指标。

## SpeechProject 真实检测器

现有 `D:\SpeechProject` 原型通过 `services/micro_detector_real` 独立适配服务接入，不把 PyTorch、FAISS 或 WavLM 依赖加入
ECHO API 进程。首次使用前，需要在 SpeechProject 虚拟环境中缓存
`microsoft/wavlm-base-plus`。之后用以下命令启动：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_micro_detector.ps1
```

服务提供 `/health`、`POST /v1/detection/jobs`、任务状态查询和事件查询。默认启用离线模型模式，
避免演示时访问模型仓库。任务结果保存在 Git 忽略的 `data/micro-detector-real/jobs.json`；服务
重启后完成结果仍可查询，重启时未完成的任务会明确失败并由 ECHO 按降级规则安全重提。

受控评测数据位于被 Git 忽略的 `data/micro-evaluation/`。复用预计算 embedding 运行固定阈值
0.51 的真实评测：

```powershell
D:\SpeechProject\venv\Scripts\python.exe `
  scripts\run_micro_detector_evaluation.py

.\.venv\Scripts\python.exe scripts\evaluate_micro_detection.py `
  data\micro-evaluation\predictions\speechproject-v1-observations.json `
  --output data\micro-evaluation\reports\speechproject-v1-metrics.json `
  --markdown-output docs\member-b\micro-evaluation-report.md
```

`micro-evaluation-130-v1` 共 130 段 30 秒录音。按“每段录音 × 三种事件类型是否出现”形成
390 个二元观察。第一轮固定阈值结果为：Accuracy 0.8513、Precision 0.1875、Recall 0.0625、
F1 0.0938。分类结果如下：

正式脱敏报告见 [micro-evaluation-report.md](micro-evaluation-report.md)。报告同时给出 Macro 指标：
Accuracy 0.8513、Precision 0.0625、Recall 0.0345、F1 0.0444；未预测出正例的类型按 Precision 0
计入 Macro 平均，避免隐藏小类别完全漏检的问题。

| 类型 | Accuracy | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| hesitation | 0.7000 | 0.1875 | 0.1034 | 0.1333 |
| guessing | 0.9615 | 无预测正例 | 0.0000 | 0.0000 |
| thinking_pause | 0.8923 | 无预测正例 | 0.0000 | 0.0000 |

Accuracy 被负样本占比抬高，不能单独作为模型有效的证据。主要问题是猜测和思考停顿全部漏检，
犹豫同时存在较多漏检和误检；正负样本的最高相似度明显重叠。以上结果证明真实链路可以运行，
但现有原型的识别质量不能作为比赛达标结果。成员 B 不负责重新训练模型；模型负责人需另设验证集
校准阈值、检查原型构建数据和 embedding 版本一致性，再由 B 使用冻结版本复测，不能直接在这 130
段最终评测数据上调参。
