# Video Overlay Pipeline

检查人类操作视频中的字幕、Logo、文字水印、贴纸及其他后期叠加，分别记录“是否有叠加、叠加类型、是否有操作、是否影响关键操作”。使用固定秒数切片、OCR 定位、区域规则和 Qwen3-VL，输出可追溯标签、复核队列、CSV 与视频 Web。

这是 **叠加标注与质量分流** 模块。默认只输出建议，不删除原视频；`accept` 只代表采样中未发现叠加阻挡。`not_applicable` 表示没有观察到相关操作，仍保留字幕／Logo 判断。当前不是自动剔除器，也不是机器人 state/action 转换器。

仓库只包含代码、配置、测试和文档。权重、视频、中间帧及批次结果留在云端。README 的组织方式参考 CoCo 的 [base_dq_pipeline](https://github.com/CoCoMatrix/base_dq_pipeline) 与 [ego_dq_pipeline](https://github.com/CoCoMatrix/ego_dq_pipeline)；交接遵循 [coco-skills](https://github.com/CoCoMatrix/coco-skills) 的身份、证据和未知项约定。

## 流程

```text
云端视频清单
  → 固定 5 秒、不重叠切片（不使用 SceneDetect）
  → 8 FPS 帧缓存，保存实际 PTS 和 SHA-256
  → 全画面 + 底部/顶部/左右区域 OCR 检测
  → 几何与持续性规则候选 + 四角独立检查
  → Qwen 判断实物文字 / 后期叠加 / 混合来源
  → 带局部证据图的 2 FPS 和 8 FPS 两遍判断
  → v4 路由 + 必要时独立遮挡核查
  → JSON / CSV / Web / 耗时与资源记录
```

| 阶段 | 输出与边界 |
|---|---|
| OCR | PP-OCRv5 mobile 检测框；不转录字幕内容，不把包装文字当成后期字幕 |
| 区域规则 | 底部横排文字、边侧/角落稳定文字候选；位置命中不等于 Logo |
| 来源核查 | `post_edit_overlay / physical_surface / mixed / no_text_or_logo / uncertain` |
| 双遍判断 | 叠加存在、类型、操作存在、遮挡影响及证据 |
| 分流 | 未遮挡、不适用、复核，以及经额外核查的遮挡候选；都不自动删除 |

当前保留 v4 的类型一致性规则：即使两遍都认为“有操作、无遮挡”，类型不同仍进入复核。规则不擅自取消这项阻塞。纯图形 Logo 可能没有 OCR 框，四角核查与完整视频语义判断用于补充，仍可能漏检。详见 [合同](docs/contract.md)。

## 环境

云端 Linux、Python 3.12、FFmpeg/ffprobe。CPU 负责切片和 ONNX OCR；Qwen 使用 CUDA 接口兼容的 NVIDIA GPU 或厂商 PPU，每个设备加载一份 8B 模型。

历史 PPU 运行使用厂商 Torch 2.9.0 / torchvision 0.24.0；必须保留厂商镜像的配套栈。NVIDIA 环境先按硬件安装兼容 Torch/torchvision。仓库不安装或替换 Torch。

```bash
git clone https://github.com/CoCoMatrix/video_overlay_pipeline.git
cd video_overlay_pipeline
# 默认分支 main 已包含完整流程，无需切换功能分支。
python3 -m venv --system-site-packages .venv-model
.venv-model/bin/python -m pip install -r requirements.txt
python3 -m venv .venv-ocr
.venv-ocr/bin/python -m pip install -r requirements-ocr.txt
export MODEL_PYTHON="$PWD/.venv-model/bin/python"
export OCR_PYTHON="$PWD/.venv-ocr/bin/python"
export CPU_PYTHON="$OCR_PYTHON"
export RUN_ROOT=/cloud/work/overlay/run-001
```

`/cloud/...` 是占位目录，替换为自己的 CPFS / 云盘挂载。OCR 依赖版本来自既有环境；新平台须验证包可用性及 ONNX 加载，不把历史 PPU 成功等同于所有 GPU 都已验证。环境与迁移说明见 [云端运行](docs/cloud.md)。

## 权重：二选一

使用同一个 `RUN_ROOT` 时只执行一种方案。两种模式都对模型内容和 OCR 权重记录 SHA-256，运行前重新检查模型身份；更换权重使用新 run root。

### A. 使用已有云端权重

```bash
"$MODEL_PYTHON" scripts/models.py existing \
  --root "$RUN_ROOT" \
  --model /cloud/models/Qwen3-VL-8B-Instruct \
  --ocr-model /cloud/models/ch_PP-OCRv5_det_mobile.onnx
```

通过相对符号链接复用，不复制大权重。DSW / DLC 必须同时挂载目标权重和 run root，并保持相对布局。已有模型会验证 Qwen3-VL 配置、分片完整性和完整内容指纹；已有副本**不自动声称**与公开 revision 相同。

### B. 从 Hugging Face 下载公开权重

```bash
"$MODEL_PYTHON" scripts/models.py huggingface \
  --root "$RUN_ROOT" --cache-dir /cloud/cache/huggingface
```

公开模型为 [Qwen/Qwen3-VL-8B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct)，revision 固定在 [configs/models.json](configs/models.json)。OCR 小权重从 RapidOCR 官方 ModelScope 版本地址下载并校验固定 SHA-256；也可加 `--ocr-model` 复用已有 OCR 文件。缓存写入云端，不进入 Git。下载只在准备阶段发生，实际推理使用 `local_files_only=True`。上游权重的使用条件以其模型卡为准。

## 执行

输入为 JSONL，每行一个已挂载的源视频，示例见 [examples/sources.jsonl](examples/sources.jsonl)。`source_id` 唯一，`path` 是本台云主机可读的文件路径；OSS URI 要先通过现有挂载或团队传输流程提供。不会递归扫描共享盘，也不会自动联网收集视频。

```bash
# 只读计划，按输入顺序取最多 500 个完整 5 秒窗口。
bash scripts/run.sh prepare --sources /cloud/data/sources.jsonl \
  --root "$RUN_ROOT" --limit 500 --dry-run
bash scripts/run.sh prepare --sources /cloud/data/sources.jsonl \
  --root "$RUN_ROOT" --limit 500

# CPU OCR + 规则；4 worker 是起点，按机器容量调整。
python3 scripts/measure_stage.py --out "$RUN_ROOT/metrics/ocr.json" -- \
  "$OCR_PYTHON" scripts/prepare_ocr_regions.py --root "$RUN_ROOT" --workers 4

# 在已经分配好的 GPU/PPU 节点执行。默认一张卡，不会提交云任务。
python3 scripts/measure_stage.py --out "$RUN_ROOT/metrics/inference.json" -- \
  "$MODEL_PYTHON" scripts/run_dataset.py --root "$RUN_ROOT" --devices 1 --run batch

bash scripts/run.sh report --root "$RUN_ROOT" --run batch --output "$RUN_ROOT/delivery"
python3 scripts/serve.py --data-dir "$RUN_ROOT/delivery" --port 8766 --wait
```

不足 500 个完整窗口时只生成实际可用数量；不重复凑数，尾部不足 5 秒丢弃。输出报告中的数量以实际 manifest 为准。编码时长可能有一帧误差。选择按源顺序，并非均匀抽样；来源多样性由调用方清单控制。

首批每张设备先完成 canary，合法输出和来源核查通过后再处理全量。单次输出最多 3 次结构修复尝试；技术失败最多进行一次记录级重试，仍失败就保留复核结果。JSON 文件落盘不意味着语义判断正确。

`report` 要求全部输入记录存在，并拒绝覆盖已有交付目录。代码、提示词、规则、模型或输入变化请使用新 root；同版本同输入可复用切片、帧、OCR 和非技术失败的推理结果。run root 同时只运行一个驱动。历史批次保留以便回滚。

## 从其他电脑打开 Web

在有云端 SSH 权限的 Mac / Linux / Windows PowerShell 执行（把账号、地址和两处目录换成实际值）：

```bash
ssh -t -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 127.0.0.1:18766:127.0.0.1:8766 user@cloud-host "python3 /cloud/code/video_overlay_pipeline/scripts/serve.py --data-dir /cloud/work/overlay/run-001/delivery --port 8766 --wait"
```

打开 [http://127.0.0.1:18766/](http://127.0.0.1:18766/)，保持 SSH 终端运行。断网后重新运行同一命令；`--wait` 会重启意外退出的云端 Web 进程，但不会自动恢复已经断开的 SSH。需要常驻重连可用自己环境中的 SSH / autossh / 系统服务。

服务仅监听云端 loopback，支持视频 Range/206。可按路由、来源、类型、原因筛选，查看视频、证据帧、来源局部图、双遍输出和完整记录。旧版 610 条交付也可以由该服务直接打开，无需重跑或改写其 HTML。不需要把视频下载到本机。

## 输出

```text
RUN_ROOT/
  model-receipt.json           权重内容身份与来源
  input-identity.json          输入 manifest / 计划身份
  src/ configs/               本轮代码与配置快照
  data-v3/manifest.jsonl       切片与原始来源、时间范围、分组关系
  data-v3/clips/ frames/       云端切片、PTS 帧与哈希
  ocr/config.json records/    OCR 身份、位置候选、耗时
  rules/config.json records/  区域候选及轨迹
  outputs/batch/              canary、逐条预测、局部图、执行时刻与重试记录
  metrics/                    墙钟、CPU 时间、进程 RSS；不是账单
  delivery/
    index.html dataset.json summary.json
    pipeline_data.csv resources.json
    videos/ thumbnails/ evidence/ origins/ records/
```

同一源及衍生片段使用 `split_group` 防止评估泄漏。接入下游时按 `clip_id` + 来源 SHA-256 + 时间范围关联，读取结构化标签，不必物理分成三个视频目录。冻结、损坏、突变等基础质量检查由独立模块负责。

发布 OSS 请复用团队 `coco-transfer-team-data`：同地域内网 endpoint、copy dry-run、内容校验和传输回执；不要用会删除历史文件的 sync。DLC 调度复用 `coco-submit-aliyun-dlc-job`，本仓库不带私人 quota、镜像或凭据。

## 验证与已知限制

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src scripts
```

[历史结果](docs/results.md)记录同 600 条 R1/R2 对比和追加到 610 条的路由；这些是已有云端结果，不是本次重新推理。39 条完整开发参考中的任一遍无叠加误报从 9/33 降至 5/33，**不是独立测试准确率**。类型分歧、短暂动作、实物字、局部覆盖与严重遮挡之间的区别仍需人工验证。

发布验证范围与未验证项在 [workflow/status.md](workflow/status.md)。建议先影子运行，按源／频道隔离测试并补独立人工标注，再决定是否启用过滤。
