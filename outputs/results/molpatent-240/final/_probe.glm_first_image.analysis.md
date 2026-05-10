# GLM First-Image Infringement Evaluation

- Input: `/root/Muti-Agent-for-Murkush-codex-project-cleanup-20260425/data/molpatent-240.infringement_input.json`
- Output: `/root/Muti-Agent-for-Murkush-codex-project-cleanup-20260425/outputs/molpatent-240.glm5_1_claim_text_first_image_infringement.json`
- Model: `glm-5.1`
- Base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- Records: 197

## Summary

| Metric | Value |
| --- | --- |
| status counts | ok: 197 |
| confidence counts | high: 61, low: 26, moderate: 110 |
| evaluable | 195 |
| unlabeled | 2 |
| unpredicted | 0 |
| errors | 0 |

## Metrics

| Metric | Value | Formula |
| --- | --- | --- |
| Accuracy | 0.7231 | (TP + TN) / total = 141 / 195 |
| Precision | 0.7727 | TP / (TP + FP) = 68 / 88 |
| Recall | 0.6667 | TP / (TP + FN) = 68 / 102 |
| Specificity | 0.7849 | TN / (TN + FP) = 73 / 93 |
| False positive rate | 21.51% | FP / negatives = 20 / 93 |
| False negative rate | 33.33% | FN / positives = 34 / 102 |

## Confusion Matrix

| Truth / Prediction | Predicted true | Predicted false |
| --- | --- | --- |
| True | 68 | 34 |
| False | 20 | 73 |

## False Negatives

| index | patent_id | selection_type | expected | pred | confidence | error |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | US9655879 | 1 | True | False | low |  |
| 25 | US10285986B2 | 2 | True | False | low |  |
| 35 | US10010539 | 1 | True | False | high |  |
| 36 | US10968217 | 1 | True | False | high |  |
| 38 | US9750738 | 1 | True | False | high |  |
| 48 | US9512105 | 1 | True | False | low |  |
| 53 | US10016420 | 2 | True | False | moderate |  |
| 54 | US10016420 | 2 | True | False | moderate |  |
| 57 | US9895330 | 1 | True | False | moderate |  |
| 65 | US20240002351A1 | 1 | True | False | moderate |  |
| 70 | US20230303562A1 | 1 | True | False | moderate |  |
| 75 | US20190008803A1 | 2 | True | False | low |  |
| 80 | US20170252328A1 | 1 | True | False | moderate |  |
| 92 | US9937139 | 2 | True | False | low |  |
| 93 | WO2009117421A2 | 1 | True | False | low |  |
| 97 | US10010539 | 2 | True | False | low |  |
| 100 | US9750738 | 2 | True | False | low |  |
| 104 | WO2020247701A2 | 1 | True | False | low |  |
| 110 | US10526323 | 1 | True | False | low |  |
| 122 | US11168070 | 2 | True | False | low |  |
| 168 | US9512105 | 2 | True | False | low |  |
| 171 | US10676478 | 1 | True | False | low |  |
| 172 | WO2023230609A1 | 1 | True | False | low |  |
| 173 | US10016420 | 1 | True | False | moderate |  |
| 174 | US20160095854A1 | 1 | True | False | low |  |
| 179 | US9758477 | 1 | True | False | moderate |  |
| 180 | US11168070 | 2 | True | False | low |  |
| 182 | US20230131535A1 | 1 | True | False | low |  |
| 186 | US20230295110A1 | 1 | True | False | moderate |  |
| 187 | US20230295110A1 | 2 | True | False | moderate |  |

## False Positives

| index | patent_id | selection_type | expected | pred | confidence | error |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | US20230303562A1 | 3 | False | True | high |  |
| 52 | WO2023230609A1 | 3 | False | True | moderate |  |
| 58 | US20210070703A1 | 3 | False | True | moderate |  |
| 66 | WO2020252229A2 | 3 | False | True | moderate |  |
| 82 | US12006316 | 4 | False | True | moderate |  |
| 90 | WO2024026368A1 | 3 | False | True | moderate |  |
| 96 | US9730936 | 3 | False | True | moderate |  |
| 102 | US9988397 | 3 | False | True | moderate |  |
| 107 | US9707212 | 3 | False | True | high |  |
| 123 | US20230108114A1 | 3 | False | True | high |  |
| 126 | US10196354 | 4 | False | True | moderate |  |
| 133 | US9763922 | 4 | False | True | moderate |  |
| 137 | US20170128460A1 | 3 | False | True | moderate |  |
| 139 | US9233979 | 3 | False | True | moderate |  |
| 145 | WO2022046606A1 | 3 | False | True | moderate |  |
| 153 | US9730936 | 4 | False | True | moderate |  |
| 158 | US9750738 | 4 | False | True | moderate |  |
| 159 | US9988397 | 3 | False | True | moderate |  |
| 167 | US10526323 | 4 | False | True | moderate |  |
| 176 | US20170266167A1 | 3 | False | True | high |  |
