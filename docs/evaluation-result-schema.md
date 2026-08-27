# ECHO 50 组正式评测结果结构与判定口径

## 1. 适用范围

本规范用于 `docs/member-d/eval_50_cases.json` 的 50 组冻结案例。运行器只记录真实 API
请求和响应，不得把 `expected`、人工参考答案、Mock 固定输出或模型补写内容复制到
`actual_output`。

每次运行使用独立 `run_id`。修复后必须创建新的运行目录，不能覆盖历史失败结果。

## 2. 目录结构

```text
data/competition-evaluation/<run_id>/
  run_manifest.json
  environment-health.json
  human-review-template.csv
  raw/
    case-001.json ... case-050.json
  results/
    case-001.json ... case-050.json
  reports/
    metrics.json
    cases.csv
    failures.json
    evaluation-report.md
```

`data/` 是本地原始运行目录，不进入 Git。最终参赛包仅复制脱敏后的 manifest、逐案例结果、
报告和必要截图；不得包含访问令牌、密码、`.env`、数据库、原始音频或真实个人信息。

## 3. 逐案例必填字段

- 身份与输入：`case_id`、`learner_type`、`module`、`knowledge_point`、
  `scenario_type` 和 `request`。
- 环境关联：`run_id`，具体 commit、配置、版本和输入哈希由 `run_manifest.json` 固定。
- 业务状态：`user_id`、`session_id`、`module_id`、`knowledge_point_id` 和评测前画像。
- 实际输出：真实意图、主要动作、ECHO 回复、降级原因、资源、判分和状态变化。
- 四 Agent 记录：`analysis`、`generation`、`validation`、`next_action` 分开保存；每项含
  输入摘要、输出、状态、失败原因、开始结束时间和是否由系统持久化。
- 证据：资料名称、官方链接、章节、版本、文档编号和切片编号。
- 人工复核：两名复核人的独立结果；不一致时增加第三人裁决。
- 指标字段和失败原因：没有完成复核的布尔字段使用 `null`，不得默认记为通过。

## 4. 状态枚举

- `completed`：真实 API 调用完成，且本案例没有发现运行或结构缺口。
- `completed_with_degradation`：API 返回了实际结果，但依赖降级、动作不符、引用缺失或
  四 Agent 记录不完整。
- `failed`：无法建立用户、调用 API、定位课程或完成该案例。
- Agent 状态：`observed`、`failed`、`not_exposed`、`not_run`。
- 人工复核状态：`pending_two_reviewers`、`completed`、`needs_adjudication`。

降级案例仍保留在 50 组分母中。降级只说明系统诚实报告了异常，不代表内容或闭环指标通过。

## 5. 五项指标

### 5.1 幻觉率

`两名人工复核确认的不正确或无官方证据支持的可核验事实声明数 / 全部可核验事实声明数`

目标 `< 5%`。两名复核人分别标注声明数和证据位置；存在分歧时采用第三人裁决结果。

### 5.2 难度适配率

`人工确认实际难度与冻结期望难度匹配的适用案例数 / 全部适用案例数`

目标 `>= 85%`。缺少有效学习画像、输出为空或只返回系统错误的案例不能记为匹配。

### 5.3 核心知识覆盖率

`人工确认覆盖全部必需核心知识点的适用案例数 / 全部适用案例数`

目标 `>= 90%`。判据来自每个冻结案例的 `judgment.knowledge_coverage`。

### 5.4 引用可追溯率

`可打开且来源、章节、版本可定位的 Microsoft 官方引用数 / 应提供的引用数`

目标 `100%`。允许域名仅为 `learn.microsoft.com` 和
`github.com/microsoft/semantic-kernel`。没有证据的正式资源必须保持草稿并判为引用失败。

### 5.5 闭环记录完整率

`四 Agent 记录、最终决定、资源或判分、状态更新均存在的案例数 / 50`

目标 `100%`。运行器根据 API 外部观察拼出的记录不等同于系统持久化记录；
`persisted_in_system=false` 时本项不通过。

## 6. 人工复核规则

1. 两名复核人独立查看 `raw/case-XXX.json`、`results/case-XXX.json` 和可打开的官方来源。
2. 分别填写 `human-review-template.csv`，不得互相覆盖。
3. 内容错误、难度、覆盖或引用数量不一致时，由第三人记录裁决和理由。
4. 将最终复核结果写回逐案例 JSON 后运行独立计分器；计分器不得再次调用模型。
5. AI 可以帮助整理声明和链接，但不能作为唯一复核人，也不能填写虚假的人员身份。

## 7. 可复现命令

```powershell
python scripts/run_competition_evaluation.py `
  --run-id formal-YYYYMMDD-01 `
  --base-url http://127.0.0.1:8010

python scripts/score_competition_evaluation.py `
  --run-dir data/competition-evaluation/formal-YYYYMMDD-01 `
  --require-formal
```

运行 5 组 smoke test 时可以重复传入 `--case-id`。断点续跑使用相同 `run_id` 和
`--resume`；已有逐案例文件不会被覆盖。
