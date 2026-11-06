# 云端执行与迁移

在云端安装代码并准备输入、模型和输出目录。CPU/OCR 与模型环境可分离，用 CPU_PYTHON、OCR_PYTHON、MODEL_PYTHON 指定解释器。scripts/serve.py 只使用标准库，不需要 Torch，也可以直接打开既有完整交付。

DSW 到 DLC 常有不同挂载前缀。相对模型符号链接只有在两个目录都被挂载且相对布局一致时有效。不能只挂载 run root 的一部分，导致链接悬空。已有 run root 必须保留 input/模型内容身份；迁移应校验，不能猜路径后静默重写历史输出。

DLC 使用 coco-submit-aliyun-dlc-job 的当前 CLI 和 preflight / quota 门禁；通过其环境要求后，把以下命令作为 job 的工作负载（变量由你的 job 环境提供）：

```bash
cd "$CODE_ROOT"
python3 scripts/measure_stage.py --out "$RUN_ROOT/metrics/inference.json" -- \
  "$MODEL_PYTHON" scripts/run_dataset.py --root "$RUN_ROOT" --devices "$DEVICE_COUNT" --run batch
```

不包含账号、quota、job ID 或一次实验镜像默认值。未声明挂载、设备数和可用 runtime 时只做计划，不提交任务。每个 worker 独占一张可见卡；CUDA_VISIBLE_DEVICES 可限制实际可见设备，再按可见卡数设置 --devices。

历史观测单卡 PyTorch allocated 峰值约 28.86 GiB，不是最低显存要求，也不包含所有运行时内存；新环境应先用 --limit 1 新批次验证，调度资源由当前平台确定。输入 500/600/610 条均不是 CLI 硬编码限制。

measure_stage.py 采样 /proc 中子进程会话的 RSS，总和可能重复计算共享页面；CPU 是已等待子进程累计时间，墙钟包括命令启动。它不是 OSS 网络流量或云账单。最终推理时刻在 outputs/batch/execution.json，峰值 allocated 在每条原始 attempts 中；GPU/PPU 小时需结合实际申请卡数和 provider 生命周期另行统计。

一键 SSH 命令见 README。8766 是云端端口，18766 是浏览器所在电脑的本地端口。端口已被不同批次占用会拒绝启动；使用新端口核验后再自行切换转发，避免打断旧批次。
