# 数据与路由合同

输入：源 JSONL 的 source_id、path，及可选 task、source_url、split_group。固定半开区间 [start_s,end_s)，不依赖场景切换；帧时间来自片段实际 PTS。2 FPS 与 8 FPS 都从同一个 8 FPS 缓存选取；视频编码帧率和选择容差意味着不是严格每 0.125 秒一帧。模型所需补齐帧重复最后 PTS，不伪造额外时间。

## 独立字段

| 字段 | 值 |
|---|---|
| overlay_present | true / false / null |
| overlay_types | subtitle, title_text, text_watermark, logo, sticker, effect, mosaic, other |
| action_present | true / false / null |
| overlay_impact | none / blocks_key_action / uncertain / not_applicable |

无操作必须 impact=not_applicable，但仍判断叠加存在与类型。操作可以由工具完成，手未出镜并不自动等于无操作；当前模型仍有边界误差。evidence 中 frame_id 必须存在，坐标是完整帧归一化 [x1,y1,x2,y2]，真实时间由程序映射。

## v4 分流优先级

1. 两遍结果缺失／结构或推理失败 → review / technical_failure。
2. 叠加存在不一致或不确定 → review / sampling_disagreement。
3. 叠加类型集合不一致 → review / overlay_type_disagreement，即使动作不存在也保留复核。
4. 两遍均无操作且叠加判断一致 → not_applicable。
5. 两遍有操作、叠加一致、impact=none → accept。
6. 两遍认为 blocks_key_action，还需要相近时间的匹配证据框和独立核查三个条件全部 true，才输出 reject / verified_overlay_blockage_candidate。
7. 其他情况 → review。

reject 是遮挡候选，不是删除指令。未确认的来源候选保留在完整视频复核中；来源核查失败会保存 status，但不会自动把两遍结果改成技术失败。生产消费应单独监控 origin_status。未命中区域规则不等于没有叠加。

## 缓存与重试

输入帧、视频、OCR 与规则文件 SHA-256，提示词和源代码、权重内容指纹都参与身份检查。配置变化使用新 run root。单个 root 单写者，发布输出拒绝覆盖。
模型输出每次最多三次结构修复，记录级技术失败最多重跑一次。对已达到重试上限的技术失败不无限重试，保留 raw_output、error、attempt 和复核路由。
无人工标签时 human_label=null；不能把模型回答或助手筛选当成独立真值。
