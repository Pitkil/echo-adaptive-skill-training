# 部署与安全

## 启动

```powershell
Copy-Item .env.example .env
docker compose up --build
```

上述命令只启动 ECHO。需要联调微表征接口时，显式启动不含模型的 Mock 8030 服务：

```powershell
docker compose --profile micro-mock up --build
```

Mock 服务只验证跨服务契约，并通过 `/health` 的 `mode: mock` 明确标识；固定检测事件不能作为
真实诊断或评测结果。WavLM、FAISS、模型权重和索引不进入 ECHO 镜像，也不进入 Git。真实检测
服务后续保持同一接口，使用独立重依赖镜像和外部数据卷。

ECHO API 默认使用 `8000`。基于多路召回与混合向量的可追溯 RAG 检索引擎、SimpleMem、微表征服务分别使用独立地址。
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
