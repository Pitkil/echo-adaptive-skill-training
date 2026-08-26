# ECHO 从零部署 Smoke Test 报告

## 状态

**尚未完成干净环境验收。** 未运行的项目不得标记为通过。

## 当前基线与探测（2026-08-26）

| 项目 | 结果 |
|---|---|
| 分支 | `member/b-micro-signal`（团队重新分配任务四） |
| Commit SHA | 最终验收时填写 |
| Python / Docker | 3.12.12 / 29.6.2 |
| PunditRAG 8000/8001 | connection refused，未入库/未检索 |
| SimpleMem 8020 | connection refused |
| 微表征 8030 | `status=ok, mode=real, version=echo-wavlm-prototype-v2` |

知识库构建已取得 15 份登记来源，失败 0、重复 0，生成 291 个切片并通过 manifest/chunk/hash
校验。PunditRAG 未启动，因此没有任何材料被声明为 `indexed`。

## 干净环境待执行

- [ ] 记录干净机器 OS、Python、Docker 和 commit SHA。
- [ ] 从 `.env.example` 创建配置，不使用隐藏值。
- [ ] 启动数据库、PunditRAG 双服务、SimpleMem、真实微表征和 ECHO。
- [ ] 初始化/迁移运行两次并验证幂等。
- [ ] 导入 63 题并核对 27/27/9、判分和重复提交。
- [ ] 通过 ECHO 导入 15 份材料并等待全部终态。
- [ ] 运行固定检索并核对来源、章节、版本和引用。
- [ ] 完成学习者闭环并检查四 Agent、资源和报告。
- [ ] 验证讲师/管理员权限和越权拒绝。
- [ ] 重启并验证会话、题目、能力、资源和材料恢复。
- [ ] 执行全部质量门禁并记录结果。
