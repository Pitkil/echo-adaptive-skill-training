# ECHO 50 组正式评测冻结摘要

本文只记录可以进入 Git 的评测口径、版本和结果摘要。逐案例实际输出、原始 HTTP 记录、人工复核 CSV、数据库关联标识和赛事交付 ZIP 均属于运行/交付数据，保存在 `data/` 与本地交付目录，不提交仓库。

## 正式结论

正式运行 `real-model-full-20260831-01-reviewed` 已满足报告发布条件：50 组冻结案例全部完成，两名人工复核人完成 50/50 独立复核，五项项目指标全部达到阈值。

| 指标 | 分子/分母 | 正式结果 | 阈值 | 判定 |
|---|---:|---:|---:|---|
| 幻觉率 | 0/132 | 0.00% | `< 5%` | 通过 |
| 难度适配率 | 47/50 | 94.00% | `>= 85%` | 通过 |
| 核心知识覆盖率 | 46/50 | 92.00% | `>= 90%` | 通过 |
| 引用可追溯率 | 131/131 | 100.00% | `100%` | 通过 |
| 闭环记录完整率 | 50/50 | 100.00% | `100%` | 通过 |
| 案例级内容错误率 | 3/50 | 6.00% | 仅报告 | 不参与上述五项阈值 |

案例级内容错误率与声明级幻觉率是不同口径：前者判断一个案例是否完整满足冻结标准；后者统计可验证声明中错误或无官方支持的声明，不得混用。

## 冻结版本

| 项目 | 值 |
|---|---|
| 正式运行 | `real-model-full-20260831-01-reviewed` |
| 代码提交 | `31f573107e6e50f6ca4a1b241223f1ac487ff389` |
| 冻结案例 SHA-256 | `cf0cd9fc0cd170b5d176cf571b702c5f734e462a05b26176fd948d9f92b94fb1` |
| 随机种子 | `20260826` |
| 温度 | `0.2` |
| 请求超时 | `240` 秒 |
| 自动重试 | `0` 次 |

正式运行时 Git manifest 记录了 5 个未跟踪目录，均为本地交付或 QA 目录；正式代码以表中 commit 为基线，没有已跟踪代码差异。

## 真实环境

正式运行健康检查返回 `status=ok`、`unavailable_count=0`，以下依赖均为真实可用状态：

- ECHO API 与业务数据库。
- PunditRAG 导入服务与查询服务。
- SimpleMem `1.0.0`。
- 真实微表征服务，`mode=real`。
- ASR `1.0.0`，`mode=faster-whisper`。

本批 50 组冻结输入不包含音频。微表征与 ASR 健康状态用于证明完整运行环境可用，不进入无音频案例的指标分母，也不伪造语音检测结果。

## 数据与复核

- 50 组案例覆盖 P1/P2/P3 三类画像、M1/M2/M3 三个模块、三类个性化资源、动态调整和异常边界。
- 正式题库共 63 道。
- 正式知识库清单 v1.7 共 20 份 Microsoft 官方材料，导入记录为 20/20 完成。
- 基础知识库交付切片包含 15 份官方材料和 291 条切片样本。
- 复核人 1：`reviewer-1`，完成时间 `2026-08-31T14:10:00+08:00`。
- 复核人 2：`reviewer-2`，完成时间 `2026-08-31T14:45:00+08:00`。
- 两份复核 CSV 的七个计分字段完全一致，无需第三人裁决。

人工复核源文件 SHA-256：

- `reviewer-1.csv`：`10b8f49ce1d82b02d5030e98fcfb037af2d56c557ece2e90cf1ea6194844754c`
- `reviewer-2.csv`：`0c58c985a87f71647deae8563d9b2273cfe665617dab7e727053df1d598fd6bc`

## 正式计分复现

先把两份人工复核导入原始运行的独立副本，不得覆盖原始运行目录：

```powershell
python scripts\import_human_reviews.py `
  --source-run-dir data\competition-evaluation\real-model-full-20260831-01 `
  --target-run-dir data\competition-evaluation\real-model-full-20260831-01-reviewed `
  --review-file <reviewer-1.csv> `
  --review-file <reviewer-2.csv>
```

再执行正式计分：

```powershell
python scripts\score_competition_evaluation.py `
  --run-dir data\competition-evaluation\real-model-full-20260831-01-reviewed `
  --require-formal
```

发布前必须确认：

- `case_count == 50`
- `result_count == 50`
- `completed_human_review_count == 50`
- `pending_human_review_count == 0`
- `formal_ready == true`
- `all_thresholds_passed == true`

## Git 与赛事交付边界

仓库只提交运行器、计分器、结构定义、测试和本摘要。下列文件只进入最终赛事作品包，不进入 Git：

- 50 组 `raw/` 与 `results/`。
- 双人复核原始 CSV。
- 正式 DOCX/PDF、图表和机器可读指标副本。
- 专业知识库原始材料与切片交付副本。
- 文件清单、SHA-256 和最终 ZIP。

该边界避免把运行数据、上传材料、数据库关联信息和本地交付制品混入代码仓库，同时保留赛事评审所需的完整输入、中间决策、最终输出与复现证据。
