# MolPatent-240 侵权实验综合报告

- 生成日期：2026-05-05
- 本次更新：2026-05-05 19:32:22 +08:00
- 更新内容：将 Bailian GLM 从上一版快照更新为最终落盘结果 `molpatent-240.glm_5_1.claim_text_first_image.bailian.infringement.json`；同步更新核心指标、预测分布、selection type 分层和最终排序。
- 评估数据集：`data/molpatent-240.infringement_input.json`
- 主评估口径：以结果记录里的 `input.expected_is_protected` 为真实标签，以 `result.is_infringing` 或 `result.is_protected` 为预测；仅统计真实标签和预测均非空的记录。
- 数据集口径：197 条输入；其中原始数据集 195 条有真实标签，2 条标签缺失。
- Bailian 最终校验：197/197 `ok`，无缺失索引，无重复索引，无空判定字段；第 43、179 条模型格式异常记录已补齐。

## 1. 纳入比较的四个实验

| 实验 | 结果文件 | 输入信息 / 流程 | 模型 | 状态 |
| --- | --- | --- | --- | --- |
| Qwen claim text + first image | `outputs/results/molpatent-240/comparisons/molpatent-240.qwen_max_claim_text_first_image_infringement_zh.json` | claim text + 第一张专利图 | `qwen-max` | 已完成 |
| Legacy full pipeline 5bd4761 | `outputs/results/molpatent-240/legacy/molpatent-240.infringement_full_5bd4761_20260503_182500.json` | 旧完整 pipeline，含 Markush/匹配/requirements，并带 patentability 子任务 | legacy pipeline | 已完成 |
| GLM claim text + first image | `outputs/results/molpatent-240/final/molpatent-240.glm5_1_claim_text_first_image_infringement.json` | claim text + 第一张专利图 | `glm-5.1` | 已完成 |
| Bailian GLM final | `outputs/results/molpatent-240/final/molpatent-240.glm_5_1.claim_text_first_image.bailian.infringement.json` | claim text + LLM 选择主 Markush 图像 | `glm-5.1` | 已完成，197/197 |

## 2. 当前结论

完整结果里，**GLM claim text + first image** 仍然是最佳基线：Accuracy 72.31%，Balanced accuracy 72.58%，Recall 66.67%。它明显优于 Qwen claim text + first image，也优于 legacy full pipeline。

**Bailian GLM final** 已经是最终落盘结果。最终 Accuracy 为 64.10%，Balanced accuracy 为 65.02%，Precision 为 76.67%，Recall 为 45.10%，Specificity 为 84.95%。它整体优于 Qwen 和 legacy full pipeline，但低于历史 GLM claim text + first image。

Bailian 的主要特征是更保守：FP=14，低于历史 GLM 的 FP=20；但 FN=56，高于历史 GLM 的 FN=34。因此 Bailian 牺牲了正例召回，换来了更高的负例排除能力。

## 3. 核心指标总表

| 实验 | records | ok | error | 可评估 | TP | TN | FP | FN | Accuracy | Balanced Acc. | Precision | Recall | Specificity | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen claim text + first image | 197 | 193 | 4 | 192 | 7 | 90 | 2 | 93 | 50.52% | 52.41% | 77.78% | 7.00% | 97.83% | 12.84% |
| Legacy full pipeline 5bd4761 | 197 | 192 | 5 | 190 | 29 | 79 | 11 | 71 | 56.84% | 58.39% | 72.50% | 29.00% | 87.78% | 41.43% |
| GLM claim text + first image | 197 | 197 | 0 | 195 | 68 | 73 | 20 | 34 | 72.31% | 72.58% | 77.27% | 66.67% | 78.49% | 71.58% |
| Bailian GLM final | 197 | 197 | 0 | 195 | 46 | 79 | 14 | 56 | 64.10% | 65.02% | 76.67% | 45.10% | 84.95% | 56.79% |

说明：

- Qwen 的 4 条 `status=error` 没有预测，因此不进入主评估分母。
- Legacy full pipeline 的 5 条 `status=error` 没有预测；该结果里共有 7 条真实标签缺失口径，包含原始无标签记录和错误记录导致的缺失。
- GLM claim text + first image 和 Bailian GLM final 都是 197 条全部落盘成功；主评估分母为 195，因为原始数据有 2 条真实标签缺失。
- Bailian 最终 JSON 已重新生成对应分析报告：`outputs/results/molpatent-240/final/molpatent-240.glm_5_1.claim_text_first_image.bailian.infringement.analysis.md`

## 4. 预测分布与偏置

| 实验 | 预测覆盖 | 预测未覆盖 | 标签缺失 | 预测缺失 | 主要偏置 |
| --- | ---: | ---: | ---: | ---: | --- |
| Qwen claim text + first image | 9 | 184 | 2 | 4 | 极强未覆盖偏置 |
| Legacy full pipeline 5bd4761 | 40 | 152 | 7 | 5 | 偏向未覆盖 |
| GLM claim text + first image | 90 | 107 | 2 | 0 | 预测分布最接近真实标签分布 |
| Bailian GLM final | 61 | 136 | 2 | 0 | 偏向未覆盖，但弱于 Qwen/legacy |

GLM claim text + first image 的预测覆盖数为 90，最接近完整数据集中 102 条真实覆盖样本。Bailian 最终预测覆盖数为 61，比上一版快照的 51 更高，但仍明显低于历史 GLM，因此召回不足仍是主要问题。

## 5. Selection Type 分层

`selection_type=1/2` 基本是正例，分别对应专利实施例和按权利要求构造的分子；`selection_type=3/4` 基本是负例，分别对应取代基越界和核心骨架越界。

下表中，type 1/2 表示正例召回率，type 3/4 表示负例排除率。

| 实验 | type 1 | type 2 | type 3 | type 4 |
| --- | ---: | ---: | ---: | ---: |
| Qwen claim text + first image | 4/66 = 6.06% | 3/34 = 8.82% | 71/73 = 97.26% | 19/19 = 100.00% |
| Legacy full pipeline 5bd4761 | 19/64 = 29.69% | 10/36 = 27.78% | 59/70 = 84.29% | 20/20 = 100.00% |
| GLM claim text + first image | 46/66 = 69.70% | 22/36 = 61.11% | 59/73 = 80.82% | 14/20 = 70.00% |
| Bailian GLM final | 32/66 = 48.48% | 14/36 = 38.89% | 63/73 = 86.30% | 16/20 = 80.00% |

主要观察：

- Qwen 对 `type 1/2` 正例几乎失效，但负例排除很强。
- Legacy full pipeline 相比 Qwen 能找回更多正例，但召回仍低，`type 1/2` 都不到 30%。
- 历史 GLM claim text + first image 对正例召回最好，但 `type 3/4` 的负例排除弱于 Bailian。
- Bailian final 介于 legacy 和历史 GLM 之间：正例召回优于 legacy，但低于历史 GLM；负例排除优于历史 GLM，但低于 Qwen 的极端保守结果。

## 6. 与历史 GLM 完整结果的对照

| 指标 | Legacy full pipeline 5bd4761 | GLM claim text + first image | Bailian GLM final |
| --- | ---: | ---: | ---: |
| 可评估 | 190 | 195 | 195 |
| Accuracy | 56.84% | 72.31% | 64.10% |
| Balanced accuracy | 58.39% | 72.58% | 65.02% |
| Precision | 72.50% | 77.27% | 76.67% |
| Recall | 29.00% | 66.67% | 45.10% |
| Specificity | 87.78% | 78.49% | 84.95% |
| FP | 11 | 20 | 14 |
| FN | 71 | 34 | 56 |

这张表最能说明路线差异：Bailian final 比历史 GLM 更保守，Specificity 提高 6.46 个百分点，FP 从 20 降到 14；但 Recall 下降 21.57 个百分点，FN 从 34 升到 56。当前最值得复盘的是 Bailian 的 FN，而不是错误/缺失落盘问题。

## 7. Bailian 最终结果状态

| 字段 | 当前值 |
| --- | --- |
| 输出文件 | `outputs/results/molpatent-240/final/molpatent-240.glm_5_1.claim_text_first_image.bailian.infringement.json` |
| 分析报告 | `outputs/results/molpatent-240/final/molpatent-240.glm_5_1.claim_text_first_image.bailian.infringement.analysis.md` |
| total | 197 |
| completed | 197 |
| ok | 197 |
| error | 0 |
| workers | 3 |
| request_timeout | 900 |
| text_source | `claim` |
| response_language | `zh` |
| image_selection_max_images | 60 |
| image_selection_min_score | 0.55 |
| started_at | `2026-05-05T02:31:39Z` |
| finished_at | `2026-05-05T09:14:05Z` |
| direct_repair_indices | `[179]` |

置信度分布：

| confidence | 数量 |
| --- | ---: |
| high | 117 |
| moderate | 24 |
| low | 53 |
| very_low | 3 |

落盘完整性校验结果：

| 检查项 | 结果 |
| --- | --- |
| records | 197 |
| status counts | `ok: 197` |
| missing indices | 0 |
| duplicate indices | 0 |
| empty required result fields | 0 |
| missing text/image artifacts | 0 |

## 8. 工程与模型判断

1. 移除 GLM 单图实验后，综合比较口径更贴近当前路线：Qwen claim text、legacy full pipeline、历史 GLM claim text、Bailian GLM final。
2. 历史 GLM claim text + first image 仍是当前完整结果中的最佳基线。
3. Bailian final 已经完成，但它不是历史 GLM 的直接胜出版本；它更像“更保守的 GLM 变体”，优势在负例排除，短板在正例召回。
4. Bailian 的图像选择流程没有导致落盘缺失；当前瓶颈更可能在主判定 prompt 的保守性、claim text 截断后的证据组织，或模型对 Markush 覆盖关系的保守解释。

## 9. 后续建议

1. 优先复盘 Bailian 的 56 条 FN，重点看 `type 1/2` 正例为什么被判为未覆盖。
2. 对比“历史 GLM 为 TP、Bailian 为 FN”的样本，判断差异来自图像选择、中文 prompt、保守判定规则，还是 Bailian 兼容接口模型行为差异。
3. 单独抽查 Bailian high-confidence 错误。当前 high 样本很多，如果 high 错误集中在某类 `selection_type` 或 `patent_id`，说明证据链提示需要增强。
4. 若继续优化 Bailian 路线，建议先调整正例召回相关 prompt，再评估 FP 是否可接受；当前 FP 已经比历史 GLM 少。

## 10. 当前排序

| 排名 | 实验 | 理由 |
| ---: | --- | --- |
| 1 | GLM claim text + first image | 完整结果最佳，Accuracy 72.31%，Recall 66.67%，F1 71.58% |
| 2 | Bailian GLM final | Accuracy 64.10%，Specificity 84.95%，但 Recall 45.10% 偏低 |
| 3 | Legacy full pipeline 5bd4761 | Accuracy 56.84%，Recall 29.00%，明显偏保守 |
| 4 | Qwen claim text + first image | Accuracy 50.52%，Recall 7.00%，基本不适合作为当前主路线 |
