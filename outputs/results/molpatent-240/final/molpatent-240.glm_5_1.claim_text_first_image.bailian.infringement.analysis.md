# GLM First-Image Infringement Evaluation

- Input: `C:\Users\de'l'l\Markush\data\molpatent-240.infringement_input.json`
- Output: `C:\Users\de'l'l\Markush\outputs\results\molpatent-240\final\molpatent-240.glm_5_1.claim_text_first_image.bailian.infringement.json`
- Model: `glm-5.1`
- Base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- Records: 197

## Summary

| Metric | Value |
| --- | --- |
| status counts | ok: 197 |
| confidence counts | high: 117, low: 53, moderate: 24, very_low: 3 |
| evaluable | 195 |
| unlabeled | 2 |
| unpredicted | 0 |
| errors | 0 |

## Metrics

| Metric | Value | Formula |
| --- | --- | --- |
| Accuracy | 0.6410 | (TP + TN) / total = 125 / 195 |
| Precision | 0.7667 | TP / (TP + FP) = 46 / 60 |
| Recall | 0.4510 | TP / (TP + FN) = 46 / 102 |
| Specificity | 0.8495 | TN / (TN + FP) = 79 / 93 |
| False positive rate | 15.05% | FP / negatives = 14 / 93 |
| False negative rate | 54.90% | FN / positives = 56 / 102 |

## Confusion Matrix

| Truth / Prediction | Predicted true | Predicted false |
| --- | --- | --- |
| True | 46 | 56 |
| False | 14 | 79 |

## False Negatives

| index | patent_id | selection_type | expected | pred | confidence | error |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | WO2020252229A2 | 1 | True | False | low |  |
| 2 | US9655879 | 1 | True | False | low |  |
| 10 | WO2024062043A1 | 1 | True | False | low |  |
| 22 | WO2022046606A1 | 1 | True | False | low |  |
| 23 | US10183949 | 2 | True | False | high |  |
| 25 | US10285986B2 | 2 | True | False | low |  |
| 29 | WO2024026368A1 | 2 | True | False | moderate |  |
| 35 | US10010539 | 1 | True | False | high |  |
| 38 | US9750738 | 1 | True | False | low |  |
| 39 | US9988397 | 1 | True | False | high |  |
| 48 | US9512105 | 1 | True | False | low |  |
| 53 | US10016420 | 2 | True | False | low |  |
| 54 | US10016420 | 2 | True | False | high |  |
| 55 | US11746094 | 1 | True | False | low |  |
| 57 | US9895330 | 1 | True | False | low |  |
| 61 | US10028967 | 1 | True | False | low |  |
| 63 | US11168070 | 1 | True | False | very_low |  |
| 65 | US20240002351A1 | 1 | True | False | low |  |
| 68 | US10196354 | 2 | True | False | moderate |  |
| 75 | US20190008803A1 | 2 | True | False | low |  |
| 81 | US9233979 | 1 | True | False | low |  |
| 84 | US9856219 | 2 | True | False | moderate |  |
| 88 | US10285986B2 | 2 | True | False | low |  |
| 92 | US9937139 | 2 | True | False | high |  |
| 93 | WO2009117421A2 | 1 | True | False | low |  |
| 94 | US10183009 | 2 | True | False | low |  |
| 97 | US10010539 | 2 | True | False | high |  |
| 100 | US9750738 | 2 | True | False | high |  |
| 104 | WO2020247701A2 | 1 | True | False | very_low |  |
| 105 | US20240109886A1 | 2 | True | False | moderate |  |

## False Positives

| index | patent_id | selection_type | expected | pred | confidence | error |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | US20230303562A1 | 3 | False | True | moderate |  |
| 66 | WO2020252229A2 | 3 | False | True | high |  |
| 69 | US9884043 | 3 | False | True | high |  |
| 73 | US8039496 | 4 | False | True | high |  |
| 76 | US9884048 | 3 | False | True | high |  |
| 82 | US12006316 | 4 | False | True | high |  |
| 102 | US9988397 | 3 | False | True | moderate |  |
| 111 | US20150224105A1 | 4 | False | True | high |  |
| 123 | US20230108114A1 | 3 | False | True | high |  |
| 132 | WO2024062043A1 | 3 | False | True | high |  |
| 133 | US9763922 | 4 | False | True | high |  |
| 155 | US10968217 | 3 | False | True | high |  |
| 159 | US9988397 | 3 | False | True | high |  |
| 176 | US20170266167A1 | 3 | False | True | high |  |
