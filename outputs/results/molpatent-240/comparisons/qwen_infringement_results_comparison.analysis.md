# Qwen 侵权实验结果对比分析

- 生成日期：2026-05-03
- 对照数据集：`data/molpatent-240.infringement_input.json`
- 主评估口径：以 `expected_is_protected` 为真实标签，以 `result.is_infringing` 为预测；仅统计真实标签和预测均非空的记录。

## 1. 纳入分析的 Qwen 输出

| 文件 | 类型 | 是否可评估 | 说明 |
| --- | --- | --- | --- |
| `outputs/results/molpatent-240/comparisons/molpatent-240.qwen_max_first_image_infringement.json` | 全量真实运行 | 是 | 只给模型第一张专利图片 |
| `outputs/results/molpatent-240/comparisons/molpatent-240.qwen_max_claim_text_first_image_infringement_zh.json` | 全量真实运行 | 是 | 给模型 claim text + 第一张专利图片，中文输出 |
| `outputs/runtime/dry-run/qwen_claim_text_first_image_dry_run_workers3.json` | dry-run | 否 | 文件名带 qwen，但 summary 中 `model=glm-5.1`，且 `is_infringing=null` |
| `outputs/runtime/smoke/smoke_us10676478_qwen_max*.json` | 单条 smoke | 否 | 全部在 match fusion 阶段因 Qwen 参数错误失败 |
| `outputs/runtime/smoke/smoke_us10676478_caption.json` | 单条 smoke | 否 | 使用 `qwen3.5-max`，模型不存在或无权限 |

## 2. 总体对比

| 结果 | 总记录 | ok | error | 可评估 | Accuracy | Balanced Acc. | Precision | Recall | Specificity | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen first image | 197 | 197 | 0 | 195 | 47.69% | 50.00% | n/a | 0.00% | 100.00% | n/a |
| Qwen claim text + first image | 197 | 193 | 4 | 192 | 50.52% | 52.41% | 77.78% | 7.00% | 97.83% | 12.84% |

核心结论：加入 claim text 后，结果只比 image-only 好一点点，从 **47.69%** 提升到 **50.52%**。但两者都没有形成有效的正例识别能力，仍然高度偏向“不侵权”。

## 3. Qwen First Image 结果

`molpatent-240.qwen_max_first_image_infringement.json` 的运行完整性最好，197 条全部 `ok`，没有接口错误。但模型把 197 条全部预测为 `false`。

| 真实 / 预测 | 预测侵权 | 预测不侵权 | 合计 |
| --- | ---: | ---: | ---: |
| 真实侵权 | 0 | 102 | 102 |
| 真实不侵权 | 0 | 93 | 93 |
| 合计 | 0 | 195 | 195 |

| selection_type | 可评估 | 正确 | 准确率 | 真实正例 | 真实负例 | 预测侵权 | 预测不侵权 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 66 | 0 | 0.00% | 66 | 0 | 0 | 66 |
| 2 | 36 | 0 | 0.00% | 36 | 0 | 0 | 36 |
| 3 | 73 | 73 | 100.00% | 0 | 73 | 0 | 73 |
| 4 | 20 | 20 | 100.00% | 0 | 20 | 0 | 20 |

这个结果本质上是“默认不侵权”策略：负例全对，正例全漏。它不能作为侵权判断模型，只能说明第一张图通常不足以支撑判断。结果里的推理也反复出现“图中没有足够结构/权利要求信息”的模式。

运行耗时方面，该批次平均每条约 **8.95 秒**，总 `elapsed_sec` 约 **1762.39 秒**。

## 4. Qwen Claim Text + First Image 结果

这份就是刚才单独分析的中文输出结果。它比 first-image 多了一些正例命中，但代价是新增了接口错误和少量 FP。

| 真实 / 预测 | 预测侵权 | 预测不侵权 | 合计 |
| --- | ---: | ---: | ---: |
| 真实侵权 | 7 | 93 | 100 |
| 真实不侵权 | 2 | 90 | 92 |
| 合计 | 9 | 183 | 192 |

相比 first-image：

| 变化类型 | 数量 | 说明 |
| --- | ---: | --- |
| 保持正确 | 90 | 主要是真实负例继续判不侵权 |
| 从错变对 | 7 | 真实正例从 `false` 改成 `true` |
| 从对变错 | 2 | 真实负例从 `false` 改成 `true` |
| 保持错误 | 93 | 真实正例仍被判不侵权 |

从错变对的 7 条：

| index | patent_id | selection_type | confidence |
| ---: | --- | ---: | --- |
| 23 | US10183949 | 2 | moderate |
| 53 | US10016420 | 2 | moderate |
| 54 | US10016420 | 2 | moderate |
| 128 | US9884043 | 1 | high |
| 131 | US8039496 | 1 | high |
| 152 | US9980929 | 1 | moderate |
| 173 | US10016420 | 1 | moderate |

从对变错的 2 条：

| index | patent_id | selection_type | confidence |
| ---: | --- | ---: | --- |
| 33 | US9980929 | 3 | moderate |
| 69 | US9884043 | 3 | moderate |

运行耗时方面，该批次平均每条约 **21.68 秒**，总 `elapsed_sec` 约 **4271.45 秒**。也就是说 claim text 版本耗时约为 first-image 的 2.4 倍，但准确率只提升约 2.83 个百分点，召回率也只有 7.00%。

## 5. Dry-run 与 Smoke 结果

`qwen_claim_text_first_image_dry_run_workers3.json` 不是真实 Qwen 评测：

- summary 中 `model=glm-5.1`。
- 只有 5 条。
- `status=dry_run_ok`。
- `result.is_infringing=null`。

因此它只能说明缓存文本和第一张图片能被找到，不能说明模型效果。

`smoke_us10676478_qwen_max.json`、`smoke_us10676478_qwen_max_4096.json`、`smoke_us10676478_qwen_max_8192.json` 都在 match fusion 阶段失败，错误为：

`Range of max_tokens should be [1, 8192]`

`smoke_us10676478_caption.json` 使用 `qwen3.5-max`，失败原因为模型不存在或无权限。

这些 smoke 文件不能用于准确率评估，但它们暴露了 Qwen 适配层两个问题：`max_tokens` 上限需要控制到 8192 以内，模型名需要使用实际可用的 DashScope 模型名。

## 6. 效果判断

1. **first-image 单图路线效果很差**：准确率 47.69%，召回率 0%。它只是把所有样本都判成不侵权。
2. **claim text + first image 有轻微提升，但仍然不可用**：准确率 50.52%，召回率 7.00%。多命中 7 个正例，但仍漏掉 93 个正例。
3. **Qwen 当前更像负例过滤器，而不是侵权判断器**：负例特异度接近满分，但这主要来自默认 `false`，不是来自可靠的结构覆盖推理。
4. **加入 claim text 的性价比不高**：耗时约 2.4 倍，准确率只提升约 2.83 个百分点。
5. **工程适配仍有硬错误**：claim text 版本出现 4 条输入长度超限，smoke 中出现 `max_tokens` 超限，说明 Qwen 路径还需要单独配置上下文长度和输出 token 上限。

## 7. 后续建议

- 不建议继续把“第一张图直接问 Qwen”作为主路线，它没有正例召回。
- Claim text 路线需要先做权利要求裁剪：优先独立权利要求、Markush 通式、R-group 定义，避免把大量无关 claim 塞给模型。
- Prompt 里应强制输出中间结构化证据，例如 claim skeleton、R-group 表、query molecule 对应取代基、每个限制是否满足；否则模型容易在“不确定”时默认否定。
- Qwen 配置应单独设置：`max_tokens <= 8192`，文本输入长度控制在 DashScope 当前限制内，避免 30720 输入长度错误。
- 如果要保留 Qwen 作为候选模型，下一轮建议只跑一个小型高质量集，先验证召回是否能从 7% 提升到可接受区间，再决定是否全量重跑。
