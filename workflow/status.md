# Workflow handoff

阶段：人类操作视频的叠加质量标注／分流；交付可复用 owner 代码。robot contract、canonical、训练 adapter 为 not_applicable，本流程没有机器人 state/action 转换。

Owner: https://github.com/CoCoMatrix/video_overlay_pipeline
实现分支: feat/portable-overlay-workflow
模式: shadow_only，保留 v4 路由；不自动删除数据。

## 已完成证据

- 22 项 CPU 合同／规则／HTTP 测试通过，Python 编译与 CLI help 通过。
- 云端真实 5 秒片段准备：38 帧，OCR 107 个检测框，规则分析完成。
- 已有模型全内容哈希与 OCR 固定 SHA-256 检查通过；公共 Qwen revision 已查询核实。
- 原始 610 条预测重新聚合，0 条路由差异；核心 contract、region gate、rules 字节不变。
- 从真实旧预测导出独立 Web，11 个引用资产 HTTP 200、视频 Range 206、FFmpeg 完整解码、JavaScript 语法通过。
- 机器证据见 docs/validation.json，核心源码身份见 workflow/source-manifest.json。
- README 范例来源：base_dq_pipeline@dcc636ceca26afdf1cec69542300b279cdc7e83a、
  ego_dq_pipeline@837c0e67301d7b1bc64ff38583b4544265ae49f1、
  coco-skills@d482a32268586a96681a8b51b8dfa22ee4286e93。

## 未验证层级

未在新包装入口重新执行 GPU/PPU 推理、完整公开大权重下载或跨平台安装。没有浏览器完整播放测试；HTTP/解码检查不替代交互验收。历史 610 条结果不能当作新包装版本重新推理的结果。

现有 DSW 网页和原始实验目录保持独立。实际数据路径、验证产物、最终 source commit 和发布回执保留在操作者云端私有运行目录，不把个人部署值变成团队默认。

唯一下一步：使用自己的云端环境、输入与权重，在新 run root 上执行 --limit 1，再运行 canary + 推理并核验输出；通过后扩大批次。语义准确率仍需独立人工标注及按来源隔离测试。
