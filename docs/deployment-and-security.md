# 部署与安全

完整的从零部署、初始化、健康检查、故障排查、备份恢复和 Smoke Test 步骤见
[`deployment/runbook.md`](deployment/runbook.md)。本文只保留安全边界和常用启动入口。

## 启动

```powershell
Copy-Item .env.example .env
# 为 SIMPLEMEM_API_KEY 生成并填写至少 32 字节的随机密钥
docker compose up --build
```

上述命令只启动 ECHO。需要联调微表征接口时，显式启动不含模型的 Mock 8030 服务：

```powershell
docker compose -f docker-compose.yml -f docker-compose.micro-mock.yml --profile micro-mock up --build
```

覆盖配置将 ECHO 的容器内检测地址设为 `http://micro-detector:8030`，并等待 Mock 的 `/health`
健康检查通过。Mock 服务只验证跨服务契约，并通过 `/health` 的 `mode: mock` 明确标识；固定检测事件不能作为
真实诊断或评测结果。真实检测
服务后续保持同一接口，使用独立重依赖镜像和外部数据卷。

真实微表征检测使用私有仓库中由 Git LFS 管理的冻结离线推理制品。首次 Clone 后执行：

```powershell
git lfs install
git lfs pull
powershell -ExecutionPolicy Bypass -File scripts\verify_micro_model.ps1
docker compose -f docker-compose.yml -f docker-compose.competition.yml up --build
```

`models/micro_detector/` 只保存 WavLM 推理权重、三类行为原型、许可说明和校验清单。FAISS 索引在运行时
根据三个原型向量内存构建，不提交持久化索引。训练音频、生成 embedding、缓存和个人数据不得进入 Git。
组委会交付由 `scripts/export_competition.ps1` 从冻结提交生成，脚本会将 Git LFS 指针替换为已校验的真实权重。

需要启用检测服务事件回调时，在 ECHO 与 8030 服务中配置相同的 `MICRO_CALLBACK_SECRET`，
8030 使用 `X-Micro-Service-Key` 请求头调用回调。该值为空时回调入口保持关闭；不得使用普通
学习者或导师登录令牌代替服务身份。生产部署应通过密钥管理系统注入，不写入 Git。

ECHO 对宿主机默认使用 `8010`；Docker 容器内监听 `8000`。PunditRAG 导入/查询、SimpleMem、
微表征分别默认使用 `8000`、`8001`、`8020`、`8030`，不要把 ECHO 容器内端口与 PunditRAG
导入端口混淆。
SimpleMem 服务位于 `services/simplemem`，默认监听 `8020`，使用独立 SQLite 数据库和
Docker volume。部署环境应设置非空 `SIMPLEMEM_API_KEY`，ECHO 与 SimpleMem 必须使用相同值。
未设置密钥时 SimpleMem 默认拒绝启动；基础 Compose 只在容器内部网络公开 `8020`，不发布到
宿主机。仅本机联调且明确接受无鉴权风险时，可以使用回环地址覆盖配置：

```powershell
docker compose -f docker-compose.yml -f docker-compose.simplemem-dev.yml up --build
```

该覆盖配置只把 `8020` 绑定到 `127.0.0.1`，并为 ECHO 与 SimpleMem 配置相同的固定开发服务密钥，
不得用于共享或生产环境。直接无鉴权启动仍需显式设置 `SIMPLEMEM_ALLOW_INSECURE_DEV=true`，且服务
会拒绝任何非回环 `SIMPLEMEM_HOST`。
完整服务不可用时保留事实记录并返回降级原因，不伪造成功状态。

## 权限

- 学习者：本人会话、作答、画像、资源和授权语音。
- 讲师/导师：授权范围内的培训录音、知识库和学习证据。
- 系统管理员：成员身份、服务配置、审计和数据生命周期。
- Demo：管理界面中的脱敏展示模式，不是独立账号角色。

公开注册只创建学习者账号，不提供公开提权接口。首次部署通过交互式脚本创建管理员：

```powershell
docker compose exec echo-api python /workspace/scripts/bootstrap_admin.py --username admin
```

已有账号需要提升时追加 `--promote-existing`。系统始终禁止降级组织内最后一名有效管理员。

## 安全底线

- 生产环境必须替换 JWT 密钥并启用 HTTPS。
- 原始音频进入受控对象存储，不进入 Git。
- 未授权音频不分析；撤回后停止用于后续诊断。
- 多人录音未确认说话人时不绑定个人。
- 上传必须限制 MIME、扩展名、大小和解析超时。
- 外部检索结果按不可信输入处理。
- 权限变更、知识库发布、数据导出和删除必须留审计记录。

## 演示冻结

第 4 周第 6 天冻结镜像、环境变量模板、知识库版本、模型版本、50 组评测数据和演示脚本。
第 7 天只做提交检查与录制备份。
