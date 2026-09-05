# 真实微表征部署 / Real micro-signal deployment

检测器使用 WavLM Base+ 提取音频特征，并与三个冻结行为原型比较：
`hesitation`、`guessing`、`thinking_pause`。ASR 是另一项服务；自我修正不属于当前真实检测器的输出类别。

The detector uses WavLM Base+ and three frozen prototypes: hesitation, guessing and thinking pause.
It does not score subject knowledge. SimpleMem and micro-signals inform coaching, while only eligible
scored answers update MIRT U/A/R.

## 1. 模型制品 / Artifacts

模型目录需要以下文件，完整清单与哈希见
[`SHA256SUMS.txt`](../models/micro_detector/SHA256SUMS.txt)：

- `wavlm-base-plus/model.safetensors` — WavLM weights, approximately 380 MB.
- `wavlm-base-plus/config.json` and `preprocessor_config.json` — model configuration.
- `behavior_prototypes.pt` — the three matching prototypes.

普通 Git LFS 指针不是权重。必须下载实际文件并完成 SHA-256 校验。
模型启动后只读取本地制品，不会自动联网补齐缺失文件。

WavLM 使用其上游许可证。原型文件的 [MODEL_CARD](../models/micro_detector/MODEL_CARD.md)
目前仅授权团队与赛事使用，尚未确认公开再分发许可；MIT 不自动覆盖该制品。
以下下载步骤用于有相应授权的部署者。若没有原型文件使用权限，基础服务仍可运行，
或使用 `micro-mock` 做接口联调；不能将 Mock 用于真实识别评测。

The prototype model card currently limits use to the team and competition; a public redistribution
licence has not been confirmed. The repository MIT licence does not override this restriction.
The download instructions below apply to authorised users with artifact access.

## 2. Windows

先把仓库克隆在 D 盘，例如 `D:\workspaces\echo-adaptive-skill-training`。
Docker 安装目录为 `D:\Docker\Docker`，磁盘映像位置为 `D:\DockerDesktopData`。
**不要在 C 盘仓库执行大文件下载**；Git LFS 工作副本及 `.git/lfs` 缓存都位于仓库所在磁盘。
没有 D 盘的其他电脑需选择实际存在且容量充足的非系统盘。

Run in PowerShell from the repository on the data drive:

```powershell
Set-Location D:\workspaces\echo-adaptive-skill-training
git lfs install
git lfs pull --include="models/micro_detector/**" --exclude=""
if ($LASTEXITCODE -ne 0) { throw "Git LFS download failed" }
powershell -ExecutionPolicy Bypass -File scripts\verify_micro_model.ps1
if ($LASTEXITCODE -ne 0) { throw "Model verification failed" }
```

已在其他 D 盘路径保存制品时无需重复下载。在 `.env` 填写这两个完整文件路径，
配置文件仍使用仓库版本；使用 SHA256SUMS 中的哈希逐一核验现有文件：

```dotenv
MICRO_MODEL_WEIGHT_PATH=D:/ECHOModels/micro_detector/wavlm-base-plus/model.safetensors
MICRO_MODEL_PROTOTYPE_PATH=D:/ECHOModels/micro_detector/behavior_prototypes.pt
```

## 3. macOS

安装 Git LFS（例如 `brew install git-lfs`），在仓库根目录执行：

```bash
git lfs install
git lfs pull --include="models/micro_detector/**" --exclude="" && \
  (cd models/micro_detector && shasum -a 256 -c SHA256SUMS.txt)
```

默认读取仓库模型文件，无需填写 Windows 路径。外置磁盘可在 `.env` 中配置两个绝对路径，
并允许 Docker Desktop 访问该目录。

The real-detector image targets `linux/amd64` because its pinned CPU dependencies use that platform.
Intel Macs use it directly; Apple silicon uses Docker's amd64 emulation and may be slower.
Native ARM inference and real-time performance have not been validated.

## 4. 启动与验证 / Start and verify

先按 README 填好模型 API、三个独立应用密钥和两个存储密码。确认 SHA-256 全部通过，
停止之前启用的 Mock（若存在），避免两个容器同时占用 8030：

```bash
docker compose --profile micro-mock stop micro-detector
docker compose -f docker-compose.yml -f docker-compose.micro-real.yml --profile micro-real config --quiet
docker compose -f docker-compose.yml -f docker-compose.micro-real.yml --profile micro-real up --build -d
```

The image builds from the pinned Python base and installs its own dependencies. It does not require
`punditrag-app:latest`. Empty model-path variables use the repository files. Job data defaults to the
`micro-real-data` named volume; Windows storage follows Docker Desktop's disk-image location.
Existing absolute `MICRO_REAL_DATA_DIR` values remain supported. Do not change a data directory
without backing up the existing jobs.

Windows:

```powershell
Invoke-RestMethod http://127.0.0.1:8030/health
Invoke-RestMethod http://127.0.0.1:8010/api/health
```

macOS:

```bash
curl -fsS http://127.0.0.1:8030/health
curl -fsS http://127.0.0.1:8010/api/health
```

8030 应返回 `status: ok`、`mode: real`。健康检查不能代替实际音频识别测试；
在应用中授权提交一段录音，核对任务完成、时间区间和事件类型后，才算完成推理走查。
没有音频的 50 组文本评测不衡量微表征识别精度。历史检测指标见
[微表征评测报告](member-b/micro-evaluation-report.md)。

## 故障排查 / Troubleshooting

验证记录（2026-09-05）：Windows Docker Desktop 上从独立 Python 基础镜像完成构建
（Debian 包使用 USTC 镜像，Python 依赖按锁定清单安装），未依赖本机 RAG 镜像。
在 `--network none` 下只读挂载 D 盘已校验制品，3 秒合成静音完成音频转换、WavLM 特征提取和
三类原型匹配，返回 3000 ms、0 个事件。此项仅验证推理链路，不计算识别精度。
macOS 路径已通过 Compose 解析检查，尚未在 Mac 硬件上执行构建和推理。

- Missing file / hash mismatch: complete Git LFS download; do not rename a pointer as a weight file.
- No prototype access: obtain the authorised artifact from its owner; do not substitute unrelated weights.
- Build download error: inspect network access to Docker Hub, Debian, PyPI and the PyTorch CPU index.
  For Debian CDN connection failures, set `MICRO_DEBIAN_MIRROR=https://mirrors.ustc.edu.cn`
  in `.env` and rebuild. Debian package signature verification remains enabled.
- Port 8030 occupied: stop the previous Mock or real container before switching configuration.
- Inspect logs: `docker compose -f docker-compose.yml -f docker-compose.micro-real.yml --profile micro-real logs --tail 100 micro-detector`.
