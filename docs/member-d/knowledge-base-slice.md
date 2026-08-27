# Semantic Kernel 专业知识库切片

本目录登记知识库的可审查元数据；下载的官方材料、生成的切片和 PunditRAG 索引属于运行或
受控交付数据，默认写入 `data/official-kb-slice/`，不直接进入 Git。

## 来源边界

- 只接受 `learn.microsoft.com`。
- GitHub 内容只接受 `github.com/microsoft/semantic-kernel`。
- 模型生成内容、题目答案、隐藏提示词和网页搜索结果不得写入切片。
- 打包完整原文前必须复核对应页面或仓库的许可条款；不能再分发时仅提交合法切片、元数据、
  哈希和可复现获取说明。

## 构建

```powershell
python scripts/build_official_kb_slice.py build
python scripts/build_official_kb_slice.py validate
```

构建程序读取 `official_materials_manifest.json`，下载并保留原始 HTML，提取标题、正文、列表和
代码块，生成稳定的 `chunk_id`、材料 manifest、`chunks.jsonl` 和 `SHA256SUMS.txt`。网络、页面
结构或来源校验失败时命令以非零状态结束，不会把失败材料标记为成功。

## 入库状态

`prepared` 只表示材料已下载、切片和校验；它不等于 PunditRAG 已索引。必须通过 ECHO 的
`POST /v1/knowledge-bases/{knowledge_base_id}/documents` 上传，并保存外部 `kb_id`、
`document_id`、`task_id`。只有 PunditRAG 任务完成并由 ECHO 同步为 `indexed` 后才算入库成功。

当前真实入库证据以 `material_import_verification.md` 为准。
