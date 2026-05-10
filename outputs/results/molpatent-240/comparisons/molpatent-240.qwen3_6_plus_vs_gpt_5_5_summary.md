# molpatent-240 qwen3.6-plus vs GPT-5.5

| Model | Total | Evaluable | Error / Non-evaluable | Accuracy | Precision | Recall | Specificity | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen3.6-plus | 197 | 194 | 3 | 81.96% | 86.81% | 77.45% | 86.96% | 81.87% |
| GPT-5.5 | 195 | 68 | 127 | 89.71% | 96.43% | 81.82% | 97.14% | 88.52% |

GPT-5.5 在成功返回的样本上指标更高，但本次运行有 127 条不可评测记录，其中 121 条为 `401 maximum fee exceeded`，覆盖率只有 34.87%；qwen3.6-plus 基本完成全量评测，可评测覆盖率 98.48%，因此这批结果里 qwen3.6-plus 的整体可用性更好。
