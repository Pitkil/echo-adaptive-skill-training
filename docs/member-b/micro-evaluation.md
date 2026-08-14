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
