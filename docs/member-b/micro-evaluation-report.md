# 成员 B 微表征真实识别效果报告

## 1. 评测信息

- 数据版本：`micro-evaluation-130-v1`
- 检测器版本：`echo-wavlm-prototype-v2`
- 检测模式：`real-precomputed-embeddings`（真实输出，不是 Mock）
- 二元观察数：390
- 脱敏录音案例数：130
- 评测口径：binary presence per 30-second sample and event type
- 单段录音时长：30 秒
- 检测阈值：0.51

## 2. 总体指标

| 汇总方式 | Accuracy | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| Micro | 0.8513 | 0.1875 | 0.0625 | 0.0938 |
| Macro | 0.8513 | 0.0625 | 0.0345 | 0.0444 |

Macro 中没有预测正例的类别，其 Precision 按 0 计入平均，避免隐藏模型完全漏检的小类别。

## 3. 分类型混淆矩阵与指标

| 类型 | 样本数 | 正样本 | TP | TN | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| guessing（猜测） | 130 | 5 | 0 | 125 | 0 | 5 | N/A | 0.0000 | 0.0000 |
| hesitation（犹豫） | 130 | 29 | 3 | 88 | 13 | 26 | 0.1875 | 0.1034 | 0.1333 |
| thinking_pause（思考停顿） | 130 | 14 | 0 | 116 | 0 | 14 | N/A | 0.0000 | 0.0000 |

## 4. 误检与漏检事实

共 58 个错误观察：FP 13，FN 45。

实际误检类别：`hesitation`；实际漏检类别：`guessing`、`hesitation`、`thinking_pause`。未观察到的类别不会写成常见错误。

### 可复查失败样例

| 类型 | 失败 | 脱敏案例 | 时间范围 |
| --- | --- | --- | ---: |
| hesitation | false_positive | `micro-0001` | 19000–20500 ms |
| thinking_pause | false_negative | `micro-0003` | 19290–20951 ms |
| thinking_pause | false_negative | `micro-0005` | 14901–15992 ms |
| hesitation | false_negative | `micro-0009` | 20628–21323 ms |
| thinking_pause | false_negative | `micro-0012` | 24819–25662 ms |
| hesitation | false_negative | `micro-0023` | 7265–9025 ms |
| hesitation | false_positive | `micro-0028` | 14500–16000 ms |
| hesitation | false_positive | `micro-0029` | 16000–17500 ms |
| hesitation | false_negative | `micro-0057` | 16265–17044 ms |
| guessing | false_negative | `micro-0067` | 20421–21633 ms |
| guessing | false_negative | `micro-0070` | 3566–4663 ms |
| guessing | false_negative | `micro-0082` | 3797–5586 ms |

## 5. 原因分析

以下是待验证假设，不是由当前统计直接证明的事实：

1. 当前检测阈值可能无法同时保证召回率和误检率，需要在独立验证集检查，不能用本评测集调参。
2. 检测器版本与评测数据可能存在分布差异，需要模型负责人核对训练来源和 embedding 版本。
3. 片段级“是否出现”口径会隐藏事件边界误差；应另用事件级匹配评测定位该问题。

## 6. 验收结论

真实检测链路和评测脚本可复现，但当前 Recall 与 F1 明显不足。Accuracy 受大量负样本影响，不能单独作为达标证据。成员 B 不重新训练模型；模型负责人应使用独立验证集检查版本和阈值，冻结新版本后再用本数据复测。
