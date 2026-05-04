# MolPatent-240 侵权与专利性实验分析报告

- 生成时间：2026-04-26 14:59:15 UTC
- 结果文件：`outputs/results/molpatent-240/legacy/molpatent-240.infringement_full_with_llm_patentability.json`
- 分析样本数：197

## 1. 执行摘要

| 指标 | 数值 | 说明 |
| --- | --- | --- |
| 总记录 | 197 | JSON records 数量 |
| 成功记录 | 192 | 97.5% |
| 错误记录 | 5 | 2.5% |
| 有标签且有预测 | 190 | 96.4% |
| 总体准确率 | 50.5% | 正确 96 / 190 |
| 覆盖类召回 | 12.0% | TP 12 / 正例 100 |
| 覆盖类精确率 | 66.7% | TP 12 / 预测覆盖 18 |
| 负例特异度 | 93.3% | TN 84 / 负例 90 |
| 假阴性 FN | 88 | 真实覆盖但判为未覆盖 |
| 假阳性 FP | 6 | 真实未覆盖但判为覆盖 |

关键观察：
- 该批次主要瓶颈是覆盖类召回偏低：100 个真实覆盖样本中只找回 12 个，FN 为 88。
- 负例排除能力较强：90 个真实未覆盖样本中正确排除 84 个。
- `markush_structure.is_markush=false` 的成功记录有 192 个；若这不是预期行为，需要优先检查第一张图 Caption/MarkushGrapher 输出。
- 高置信样本并不完全可靠：high 置信中错误 30/63，错误率 47.6%。

## 2. 原始 summary 对照

| 字段 | 值 |
| --- | --- |
| total | 197 |
| completed | 197 |
| ok | 192 |
| error | 5 |
| patentability_ok | 192 |
| patentability_error | 0 |
| caption_from_first_image | 192 |
| caption_from_dataset | 0 |
| workers | 3 |
| caption_empty_retries | 3 |

## 3. 侵权判定性能

### 3.1 混淆矩阵

| 真实/预测 | 预测覆盖 | 预测未覆盖 | 合计 |
| --- | --- | --- | --- |
| 真实覆盖 | 12 | 88 | 100 |
| 真实未覆盖 | 6 | 84 | 90 |
| 合计 | 18 | 172 | 190 |

### 3.2 指标

| 指标 | 值 | 解释 |
| --- | --- | --- |
| Accuracy | 0.505 | 全部有标签且有预测的样本 |
| Precision | 0.667 | 预测为覆盖时有多少是真的覆盖 |
| Recall / TPR | 0.12 | 真实覆盖样本被找回的比例 |
| Specificity / TNR | 0.933 | 真实不覆盖样本被正确排除的比例 |
| F1 | 0.203 | 覆盖类的综合指标 |
| Balanced accuracy | 0.527 | 正负类召回的平均值 |

### 3.3 标签与预测分布

| 类别 | 数量 | 占比 |
| --- | --- | --- |
| 真实覆盖 | 100 | 50.8% |
| 真实未覆盖 | 90 | 45.7% |
| 真实标签缺失 | 7 | 3.6% |
| 预测覆盖 | 18 | 9.1% |
| 预测未覆盖 | 174 | 88.3% |
| 预测缺失 | 5 | 2.5% |

## 4. 按 selection_type 分层

| selection_type | 可评估 | 正确 | 准确率 | 错误 | 正例 | 负例 | 预测覆盖 | 预测未覆盖 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 64 | 9 | 14.1% | 55 | 64 | 0 | 9 | 55 |
| 2 | 36 | 3 | 8.3% | 33 | 36 | 0 | 3 | 33 |
| 3 | 70 | 64 | 91.4% | 6 | 0 | 70 | 6 | 64 |
| 4 | 20 | 20 | 100.0% | 0 | 0 | 20 | 0 | 20 |

## 5. 置信度校准

| 置信度 | 总数 | 可评估 | 正确 | 错误 | 可评估准确率 |
| --- | --- | --- | --- | --- | --- |
| high | 63 | 63 | 33 | 30 | 52.4% |
| moderate | 1 | 1 | 0 | 1 | 0.0% |
| very_low | 128 | 126 | 63 | 63 | 50.0% |
| 缺失 | 5 | 0 | 0 | 0 | n/a |

## 6. Caption / Markush / 匹配链路诊断

| 项目 | 分布 |
| --- | --- |
| caption_source | first_image: 197 |
| markush_structure.is_markush | False: 192, None: 5 |
| RDKit is_match | False: 98, True: 78, None: 21 |
| match_fusion confidence | high: 113, 缺失: 56, very_low: 19, moderate: 7, low: 2 |
| requirements confidence | very_low: 128, high: 63, 缺失: 5, moderate: 1 |

### 6.1 错误记录

| 错误信息 | 数量 |
| --- | --- |
| first image produced empty caption after 3 attempt(s) | 5 |

## 7. 专利性子任务分析

| 项目 | 统计 |
| --- | --- |
| patentability status | ok: 192, 缺失: 5 |
| prior_arts 数量 | 0: 5, 1: 192 |
| novelty_score | min: 0.3, p25: 0.6, median: 0.7, mean: 0.637, p75: 0.7, max: 0.85 |
| success_rate_estimation | min: 20%, p25: 60%, median: 65%, mean: 61.72%, p75: 65%, max: 80% |

### 7.1 分布区间

| 指标 | 区间 | 数量 |
| --- | --- | --- |
| novelty_score | 0.40-0.59 | 2 |
| novelty_score | 0.60-0.79 | 167 |
| novelty_score | <0.40 | 18 |
| novelty_score | >=0.80 | 5 |
| success_rate | 40-59% | 9 |
| success_rate | 60-74% | 166 |
| success_rate | <40% | 12 |
| success_rate | >=75% | 5 |

### 7.2 按侵权预测分组的专利性分数

| 预测覆盖 | 数量 | novelty 均值 | novelty 中位数 | novelty 最小 | novelty 最大 |
| --- | --- | --- | --- | --- | --- |
| 否 | 174 | 0.642 | 0.7 | 0.3 | 0.85 |
| 是 | 18 | 0.589 | 0.6 | 0.3 | 0.7 |

### 7.3 高频风险点

| risk_point | 出现次数 |
| --- | --- |
| The core skeleton and functional groups may be anticipated by the prior art | 5 |
| The core skeleton may be anticipated by the prior art | 4 |
| Core skeleton overlap with prior art | 4 |
| Potential overlap with the core skeleton of the prior art | 3 |
| The core skeleton and substituents may be anticipated by the prior art | 3 |
| The core skeleton and functional groups might be anticipated by the prior art | 2 |
| Structural similarity to the prior art | 2 |
| The core skeleton and common substituents may be anticipated by the prior art | 2 |
| The core skeleton is likely to be anticipated by the prior art | 2 |
| Broader R-group definitions in the prior art may cover the specific substituents in the proposed structure | 2 |
| Structural similarity to prior art | 2 |
| The core skeleton is likely to be anticipated by the prior art. | 2 |
| The core skeleton and functional groups are likely covered by the prior art | 2 |
| The core skeleton is likely anticipated by the prior art | 2 |
| The specific substituents may not be sufficiently novel to overcome the prior art | 2 |
| The core skeleton and functional groups may be anticipated by the prior art. | 2 |
| Potential overlap with indole or benzimidazole derivatives in the prior art | 1 |
| Lack of R-group definitions may limit the scope of protection | 1 |
| Lack of specific R-group definitions in the proposed structure makes it difficult to fully assess the scope | 1 |
| Similar functional groups and substitution patterns in the prior art | 1 |

### 7.4 高频建议

| suggestion | 出现次数 |
| --- | --- |
| Introduce additional unique substituents or functional groups | 13 |
| Introduce additional unique substituents or functional groups to differentiate the structure further. | 11 |
| Introduce additional substituents or functional groups to differentiate the structure. | 6 |
| Introduce additional unique substituents or functional groups to differentiate the structure | 5 |
| Modify the core skeleton to create a more distinct structure | 5 |
| Introduce additional unique substituents or functional groups to differentiate from the prior art. | 5 |
| Introduce additional substituents or functional groups to further differentiate the structure | 5 |
| Consider modifying the core skeleton to create a more distinct structure. | 4 |
| Introduce additional R-groups to broaden the scope of the claimed compounds. | 4 |
| Introduce additional substituents or functional groups to differentiate the structure further | 4 |
| Introduce additional R-groups to broaden the scope of the structure | 3 |
| Modify the core skeleton to introduce additional structural elements | 3 |
| Consider adding more specific R-group definitions to narrow the scope and differentiate from the prior art | 3 |
| Introduce additional substituents or functional groups to differentiate the structure | 3 |
| Incorporate unique functional groups or substituents | 3 |
| Consider adding R-groups to broaden the scope and introduce variability | 3 |
| Consider introducing additional unique substituents or functional groups to differentiate the structure further. | 3 |
| Introduce additional unique substituents or functional groups to differentiate the structure from the prior art. | 3 |
| Introduce additional R-groups to broaden the scope and differentiate from the prior art. | 3 |
| Introduce additional unique substituents or functional groups. | 3 |

## 8. 专利维度错误集中度

| patent_id | 总数 | 正确 | 错误 | 错误率 | 正例 | 负例 | 预测覆盖 | 预测未覆盖 | 运行错误 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| US10016420 | 4 | 1 | 3 | 75.0% | 3 | 1 | 0 | 4 | 0 |
| US10196354 | 4 | 1 | 3 | 75.0% | 3 | 1 | 0 | 4 | 0 |
| US20230295110A1 | 4 | 1 | 3 | 75.0% | 2 | 2 | 1 | 3 | 0 |
| US9750738 | 4 | 1 | 3 | 75.0% | 2 | 2 | 1 | 3 | 0 |
| WO2022038299A1 | 4 | 1 | 3 | 75.0% | 4 | 0 | 1 | 3 | 0 |
| US10285986B2 | 3 | 0 | 3 | 100.0% | 3 | 0 | 0 | 3 | 0 |
| US11168070 | 3 | 0 | 3 | 100.0% | 3 | 0 | 0 | 3 | 0 |
| US8039496 | 5 | 3 | 2 | 40.0% | 2 | 3 | 0 | 5 | 0 |
| US9624159 | 5 | 3 | 2 | 40.0% | 2 | 3 | 0 | 5 | 0 |
| US10183009 | 4 | 2 | 2 | 50.0% | 2 | 2 | 0 | 4 | 0 |
| US20230108114A1 | 4 | 2 | 2 | 50.0% | 2 | 2 | 0 | 4 | 0 |
| US20230131535A1 | 4 | 2 | 2 | 50.0% | 2 | 2 | 0 | 4 | 0 |
| US9763922 | 4 | 1 | 2 | 66.7% | 2 | 1 | 0 | 4 | 0 |
| US9856219 | 4 | 2 | 2 | 50.0% | 2 | 2 | 0 | 4 | 0 |
| US10010539 | 3 | 1 | 2 | 66.7% | 2 | 1 | 0 | 3 | 0 |
| US11746094 | 3 | 1 | 2 | 66.7% | 2 | 1 | 0 | 3 | 0 |
| US20170266167A1 | 3 | 1 | 2 | 66.7% | 2 | 1 | 0 | 3 | 0 |
| US20240109886A1 | 3 | 1 | 2 | 66.7% | 2 | 1 | 0 | 3 | 0 |
| US9512105 | 3 | 1 | 2 | 66.7% | 2 | 1 | 0 | 3 | 0 |
| US9707212 | 3 | 1 | 2 | 66.7% | 2 | 1 | 0 | 3 | 0 |

## 9. 典型错误样本

### 9.1 False Negative：真实覆盖但判为未覆盖

| index | patent_id | selection | 真实 | 预测 | 置信度 | SMILES | 原因摘要 | novelty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | WO2020252229A2 | 1 | 是 | 否 | very_low | CCc1cncc(NCc2cccnc2)n1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 2 | US9655879 | 1 | 是 | 否 | high | CC(C)(Cc1ccc(C(=O)Oc2ccc(C(=N)N)cc2F)s1)C(=O)Nc1cc(C(=O)O)cc(C(=O)O)c1 | The query molecule does not meet the claim requirements for R1, R2, and R3. Specifically, R1 is a substituted phenyl group, which is not covered by the claim. R2 and R3 are both... | 0.6 |
| 4 | US10196354 | 1 | 是 | 否 | very_low | O=C(O)c1ccc(-c2nn(C(=O)c3c(Cl)cccc3C(F)(F)F)c3cc(N4CCC4=O)ccc23)c(F)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 8 | US8039496 | 2 | 是 | 否 | very_low | N#C[C@@H]1C[C@@H](O)[C@H](COc2ccc(F)cc2)[C@H]1CCCc1ccc(C(=O)O)s1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 11 | US9763922 | 2 | 是 | 否 | very_low | CC(=O)N1CCc2c(c(N3CCc4ccccc43)nn2CCCCCCC)C1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.75 |
| 15 | US20170128460A1 | 1 | 是 | 否 | very_low | Cc1ncc(C(CNC(=O)c2ccc(Cl)cc2Cl)N2CCC(=O)CC2)cn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.3 |
| 22 | WO2022046606A1 | 1 | 是 | 否 | very_low | O=C1C(Cc2ccc(F)nc2)CCCN1c1nc(-c2ccncc2)n[nH]1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 23 | US10183949 | 2 | 是 | 否 | very_low | CC(C)(C)NC(=O)Cn1cnc(-c2ccc(Cl)cc2NC(=O)C(C)(C)C)c(Cl)c1=O | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 25 | US10285986B2 | 2 | 是 | 否 | very_low | [nH]1c2c(c(C)cc1=O)C(=O)c1c(SCC(C)C)cc(=O)n(CC(C)C)c1C2=O | ### Technical Analysis Details **Patent:** US10285986B2 **Target Molecule:** [nH]1c2c(c(C)cc1=O)C(=O)c1c(SCC(C)C)cc(=O)n(CC(C)C)c1C2=O **Markush Structure:** `<r>*</r>C1=CC(=O)N... | 0.7 |
| 28 | US9624159 | 2 | 是 | 否 | very_low | c1(C(=O)N)cc(CNc2c(F)ccc(OCC(=O)O)c2F)cc(-c2cccc(F)c2)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 29 | WO2024026368A1 | 2 | 是 | 否 | high | ClC1(Cl)CC(c2nc(C(CCCCC)c3ccncc3)c[nH]2)C1 | The query molecule has an R-group value for X (Cl) that does not match the claim requirement (X must be a bond or -C(R7)(R8)-). Additionally, the R-group value for Rb (C(CCCCC))... | 0.7 |
| 34 | US9730936 | 1 | 是 | 否 | very_low | Cc1cc(/C=C/C#N)cc(C)c1-c1cccc2c(N)nc(Nc3ccc(C#N)cc3)nc12 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 35 | US10010539 | 1 | 是 | 否 | very_low | C[C@H]1CC[C@@H](n2ncc(-c3ccccc3)n2)CN1C(=O)c1ccccc1-n1nccn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 36 | US10968217 | 1 | 是 | 否 | very_low | Cc1ccc(C(=O)N2CCc3nc(-c4ccccn4)ncc3C2)cn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.3 |
| 38 | US9750738 | 1 | 是 | 否 | high | CCC1CN(CCCc2ccccc2)CCN1c1cccc(OC)c1 | The R-groups R3, R2, and R1 do not match the specific structures required by the claim. Specifically, R3, R2, and R1 are not covered by the claim, as they do not match any of th... | 0.75 |
| 44 | US9707212 | 1 | 是 | 否 | very_low | O=c1[nH]c(-c2ccc(-c3c(C(F)(F)F)oc4cc(O)ccc4c3=O)cc2)ns1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |
| 48 | US9512105 | 1 | 是 | 否 | very_low | Cc1ccc(O)c(Oc2ccc(C(=O)N[C@H](CN3CCN(c4cccc(O)c4)[C@@H](C)C3)C(C)C)cc2)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 53 | US10016420 | 2 | 是 | 否 | very_low | O=C(NCCCn1ccnc1)c1ccc(NCCCc2cc(Cl)cc(Cl)c2)nn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.75 |
| 54 | US10016420 | 2 | 是 | 否 | very_low | O=C(NCCCn1ccnc1)c1ccc(NC(CC)CCc2cc(Cl)cc(Cl)c2)nn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.75 |
| 55 | US11746094 | 1 | 是 | 否 | very_low | c1(OC)ccc(Oc2ccc([N+](=O)[O-])c3n[se]nc23)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.75 |
| 56 | US20170266167A1 | 2 | 是 | 否 | high | COC[C@@H](NC(=O)Nc1cc2cnn(Cc3ccncc3)c2c(CO)n1)c1ccccc1 | The query molecule is not protected by the patent because the R2 and R3 values do not match the allowed definitions in the claim. Specifically, R2 (methanol) and R3 (4-methoxybe... | 0.7 |
| 57 | US9895330 | 1 | 是 | 否 | very_low | Cc1ccc(CC(=O)Nc2cc(-c3ccccc3-c3nnn[nH]3)ccc2-n2cccn2)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 60 | US9902701 | 2 | 是 | 否 | very_low | c1ccc(Br)c(F)c1C1=NN(CC(=O)N(C)c2cccc(Cl)c2)C(=O)CC1 | The R-group values provided by RDKit, when substituted into the Markush structure, match the query molecule exactly. Each R-group definition was verified to be consistent with t... | 0.6 |
| 61 | US10028967 | 1 | 是 | 否 | very_low | CC(=O)Nc1ccc(O)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.75 |
| 63 | US11168070 | 1 | 是 | 否 | very_low | Cn1cc(-c2cc3c(cc2C(F)F)N(c2ccc4sc(=O)n(C)c4c2)CCC3)cn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 68 | US10196354 | 2 | 是 | 否 | very_low | O=C(O)c1ccc(-c2nn(C(=O)c3c(Cl)cccc3C(F)(F)F)c3c(CC(=O))c(N4CCC4=O)ccc23)c(F)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 70 | US20230303562A1 | 1 | 是 | 否 | high | Cc1cccc(-n2nccc2-c2ccc3ncnn3c2)n1 | The query molecule is not protected by the patent because R2, which is hydrogen, does not meet the requirement of being a C6-10 aryl or 5- to 10-membered heteroaryl. All other R... | 0.7 |
| 74 | US9763922 | 2 | 是 | 否 | very_low | CC(=O)N1CCc2c(c(N3CCc4ccccc43)nn2(OC(F)(F)(F)))C1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |
| 75 | US20190008803A1 | 2 | 是 | 否 | very_low | Cc1cccc(CN(CCl)CC[C@@]2(c3ccccn3)CCOC3(CCCC3)C2)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.75 |
| 78 | US9439968 | 1 | 是 | 否 | very_low | CCCCCCCCCCCOC(=O)CCN(CCC(=O)OCCCCCCCCCCC)CCN1CCN(CCN(CCC(=O)OCCCCCCCCCCC)CCC(... | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |

### 9.2 False Positive：真实未覆盖但判为覆盖

| index | patent_id | selection | 真实 | 预测 | 置信度 | SMILES | 原因摘要 | novelty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 40 | WO2020247701A2 | 3 | 否 | 是 | high | c1(C(F)(F)F)ccccc1N(OCC)c1sn(-c2ccccc2)c(=O)c1C(=O)N1CCOCC1 | Each R-group value in the query molecule matches the definitions provided in the claim requirements. Specifically, R1 is a morpholine-4-carbonyl group, R2 is an ethoxy group, R3... | 0.6 |
| 51 | US10676478 | 3 | 否 | 是 | high | CCCCOc1nc(N)c2[nH]cc(Cc3cnc(CN(F)(F))s3)c2n1 | The query molecule matches the Markush structure, and the R-group value (F) is explicitly allowed as a substitution (R3) in the claim requirement text. There are no ambiguities,... | 0.6 |
| 98 | US20170182030A1 | 3 | 否 | 是 | high | Brc1cc(=O)[nH]c2c1C(=O)c1c(C)cc(=O)n(CC(C)C)c1C2=O | All R-group values in the query molecule match the definitions provided in the claim. Specifically, R1 is methyl (alkyl), R2 is isobutyl (alkyl), R3 is hydrogen, and R4 is bromi... | 0.7 |
| 101 | US9750738 | 3 | 否 | 是 | high | CCC1CN(CCCc2ccccc2)CCN1c1cccc(I)c1 | All R-group values are covered by the claim requirements. The R-group R is a C1-8 haloalkyl, Y3 and R2 are placeholders that fit within the structural context, R3 is a C2-8 alky... | 0.7 |
| 125 | US20240002351A1 | 3 | 否 | 是 | high | C(C)(Sc1nc2ccccc2c(=O)n1(Cl))C(=O)N(C)c1ccccc1 | The query molecule's R-group values are fully covered by the claim requirements. The R-group 'C' (methyl) is a simple alkyl group, which is included in the definitions of R1, R2... | 0.3 |
| 188 | US20230295110A1 | 3 | 否 | 是 | high | Cc1c(F)cnc(C(=O)NCC(=O)O)c1O | Each R-group value in the query molecule matches the definitions provided in the claim. Specifically, R1 (methyl), R2 (fluorine), R3 (hydrogen), R4 (hydrogen), R5 (hydrogen), an... | 0.7 |

### 9.3 高/中置信错误

| index | patent_id | selection | 真实 | 预测 | 置信度 | SMILES | 原因摘要 | novelty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | US9655879 | 1 | 是 | 否 | high | CC(C)(Cc1ccc(C(=O)Oc2ccc(C(=N)N)cc2F)s1)C(=O)Nc1cc(C(=O)O)cc(C(=O)O)c1 | The query molecule does not meet the claim requirements for R1, R2, and R3. Specifically, R1 is a substituted phenyl group, which is not covered by the claim. R2 and R3 are both... | 0.6 |
| 29 | WO2024026368A1 | 2 | 是 | 否 | high | ClC1(Cl)CC(c2nc(C(CCCCC)c3ccncc3)c[nH]2)C1 | The query molecule has an R-group value for X (Cl) that does not match the claim requirement (X must be a bond or -C(R7)(R8)-). Additionally, the R-group value for Rb (C(CCCCC))... | 0.7 |
| 38 | US9750738 | 1 | 是 | 否 | high | CCC1CN(CCCc2ccccc2)CCN1c1cccc(OC)c1 | The R-groups R3, R2, and R1 do not match the specific structures required by the claim. Specifically, R3, R2, and R1 are not covered by the claim, as they do not match any of th... | 0.75 |
| 40 | WO2020247701A2 | 3 | 否 | 是 | high | c1(C(F)(F)F)ccccc1N(OCC)c1sn(-c2ccccc2)c(=O)c1C(=O)N1CCOCC1 | Each R-group value in the query molecule matches the definitions provided in the claim requirements. Specifically, R1 is a morpholine-4-carbonyl group, R2 is an ethoxy group, R3... | 0.6 |
| 51 | US10676478 | 3 | 否 | 是 | high | CCCCOc1nc(N)c2[nH]cc(Cc3cnc(CN(F)(F))s3)c2n1 | The query molecule matches the Markush structure, and the R-group value (F) is explicitly allowed as a substitution (R3) in the claim requirement text. There are no ambiguities,... | 0.6 |
| 56 | US20170266167A1 | 2 | 是 | 否 | high | COC[C@@H](NC(=O)Nc1cc2cnn(Cc3ccncc3)c2c(CO)n1)c1ccccc1 | The query molecule is not protected by the patent because the R2 and R3 values do not match the allowed definitions in the claim. Specifically, R2 (methanol) and R3 (4-methoxybe... | 0.7 |
| 70 | US20230303562A1 | 1 | 是 | 否 | high | Cc1cccc(-n2nccc2-c2ccc3ncnn3c2)n1 | The query molecule is not protected by the patent because R2, which is hydrogen, does not meet the requirement of being a C6-10 aryl or 5- to 10-membered heteroaryl. All other R... | 0.7 |
| 83 | US20170304277A1 | 1 | 是 | 否 | high | CN1N=C2CCN(C(=O)[C@@H](CCc3ccccc3)NC(=O)C(C)(C)N)C[C@]2(Cc2ccccc2)C1=O | The query molecule has a phenyl group at all three R-group positions (R1, R2, and R3). While the phenyl group is acceptable for R2, it does not meet the definitions for R1 and R... | 0.7 |
| 88 | US10285986B2 | 2 | 是 | 否 | high | [nH]1c2c(c(C)cc1=O)C(=O)c1c(Cl)cc(=O)n(CC(C)C)c1C2=O | The query molecule does not meet the claim requirements for R1, R2, and R4. Specifically, R1 is Cl, which is not a (C1-20)alkyl group as required by the claims. R2 is butyl, whi... | 0.7 |
| 95 | US10183009 | 1 | 是 | 否 | high | CCCCn1cc(-c2ccc(C(C)(C)O)cc2)c2cc[nH]c2c1=O | The R1 and R3 groups do not meet the claim requirements. R1 is a 2,6-dimethyl-4-methoxyphenyl group, which is not covered by the claim. R3 is a hydrogen atom, which is also not ... | 0.7 |
| 98 | US20170182030A1 | 3 | 否 | 是 | high | Brc1cc(=O)[nH]c2c1C(=O)c1c(C)cc(=O)n(CC(C)C)c1C2=O | All R-group values in the query molecule match the definitions provided in the claim. Specifically, R1 is methyl (alkyl), R2 is isobutyl (alkyl), R3 is hydrogen, and R4 is bromi... | 0.7 |
| 100 | US9750738 | 2 | 是 | 否 | high | CCC1CN(CCCc2ccccc2)CCN1c1cccc(OCOC)c1 | The query molecule's R2 value (propylbenzene) is not covered by the claim requirements. The claim specifies that R2 can be hydrogen, methyl, ethyl, or other specific groups, but... | 0.6 |
| 101 | US9750738 | 3 | 否 | 是 | high | CCC1CN(CCCc2ccccc2)CCN1c1cccc(I)c1 | All R-group values are covered by the claim requirements. The R-group R is a C1-8 haloalkyl, Y3 and R2 are placeholders that fit within the structural context, R3 is a C2-8 alky... | 0.7 |
| 104 | WO2020247701A2 | 1 | 是 | 否 | high | c1(C(F)(F)F)ccccc1Nc1sn(-c2ccccc2)c(=O)c1C(=O)N1CCOCC1 | The R2 and R3 groups do not meet the claim requirements. R2 is a substituted benzene ring, which is not an aliphatic group, and R3 is hydrogen, which does not match the definiti... | 0.7 |
| 105 | US20240109886A1 | 2 | 是 | 否 | moderate | C1(C(=O)N)=C[C@H](n2ncc3c4cc[nH]c4ccc32)[C@@H](NC(=O)C(C)C)[C@H]([C@H](O)[C@H... | The query molecule does not meet the claim requirements for R1, R2, and R3. Specifically, R1 is C(N)=O, which is not covered by the claim. R2 is a substituted heteroaryl, but th... | 0.7 |
| 117 | US20170266167A1 | 1 | 是 | 否 | high | COC[C@@H](NC(=O)Nc1cc2cnn(Cc3ccncc3)c2cn1)c1ccccc1 | The molecule's skeleton matches the Markush structure, but the R-group analysis shows that R3 is not covered by the claim. Specifically, the benzyl ether group C(COC)c1ccccc1 is... | 0.7 |
| 124 | US20230108114A1 | 2 | 是 | 否 | high | Cc1ccc2c(c1)C(CC)N(C1CCN(C(=O)c3ccc(OCC(F)(F)F)nc3)CC1O)CC2 | The R2 and R3 values do not meet the claim requirements. Specifically, R2 and R3 are complex substituents that do not match the simple H or CH3 requirement. Since any R-group va... | 0.7 |
| 125 | US20240002351A1 | 3 | 否 | 是 | high | C(C)(Sc1nc2ccccc2c(=O)n1(Cl))C(=O)N(C)c1ccccc1 | The query molecule's R-group values are fully covered by the claim requirements. The R-group 'C' (methyl) is a simple alkyl group, which is included in the definitions of R1, R2... | 0.3 |
| 147 | US10285986B2 | 1 | 是 | 否 | high | [nH]1c2c(c(C)cc1=O)C(=O)c1c(C)cc(=O)n(CC(C)C)c1C2=O | The query molecule has an R2 value of isobutyl (CC(C)C), which is not covered by the specific combinations listed in Claim 11. While R1, R3, and R4 are covered, the presence of ... | 0.7 |
| 149 | WO2024026368A1 | 1 | 是 | 否 | high | ClC1(Cl)CC(c2nc(Cc3ccncc3)c[nH]2)C1 | The R-group values for X and Rb do not meet the claim requirements. Specifically, X is a substituted pyridine ring, which does not fit the allowed options of a bond or -C(R7)(R8... | 0.7 |
| 161 | US20240109886A1 | 1 | 是 | 否 | high | C1(C(=O)O)=C[C@H](n2ncc3c4cc[nH]c4ccc32)[C@@H](NC(=O)C(C)C)[C@H]([C@H](O)[C@H... | The query molecule is not covered by the patent because R2 and R3 do not meet the claim requirements. Specifically, R2 is a substituted pyridine ring, which is not mentioned in ... | 0.7 |
| 169 | US20220348549A1 | 1 | 是 | 否 | high | Clc1cccc2cnc(-c3cccc(Br)c3)nc12 | The query molecule matches the Markush structure, but the R5 group (methyl) is not covered by the claim requirements. The claim specifies a list of possible substituents for R5,... | 0.7 |
| 174 | US20160095854A1 | 1 | 是 | 否 | high | CCC1CN(CCCc2ccccc2)CCN1c1cccc(OC)c1 | The query molecule CCC1CN(CCCc2ccccc2)CCN1c1cccc(OC)c1 is not protected by the patent because the R-group values for R3, R2, and R1 do not match the specific structures (a)-(p) ... | 0.3 |
| 182 | US20230131535A1 | 1 | 是 | 否 | high | Cn1cc(C(c2ccncc2)c2c(O)ccc(Cl)c2Cl)cn1 | The query molecule is not protected by the patent because the values of X2, R1, and A do not meet the claim requirements. Specifically, X2 (O) and A (H) are not allowed, and R1 ... | 0.75 |
| 183 | US20230131535A1 | 2 | 是 | 否 | high | Cn1cc(C(c2ccncc2)c2c(O)ccc(C#N)c2Cl)cn1 | The query molecule does not meet the claim requirements for several R-groups. Specifically, X2, R1, R2, and A do not match the allowed substituents as defined in the claim text.... | 0.6 |
| 187 | US20230295110A1 | 2 | 是 | 否 | high | Cc1c(-c2cccc(F)c2)c(C#N)nc(C(=O)NCC(=O)O)c1O | The query molecule is not protected by the patent because the R2 group (fluorobenzene) does not meet the claim requirements. The claim specifies that R2 can be hydrogen, optiona... | 0.7 |
| 188 | US20230295110A1 | 3 | 否 | 是 | high | Cc1c(F)cnc(C(=O)NCC(=O)O)c1O | Each R-group value in the query molecule matches the definitions provided in the claim. Specifically, R1 (methyl), R2 (fluorine), R3 (hydrogen), R4 (hydrogen), R5 (hydrogen), an... | 0.7 |
| 190 | WO2022038299A1 | 1 | 是 | 否 | high | CC(C)OC(=O)Oc1cccc2[nH]cc(CCN(C)C)c12 | The query molecule matches the Markush structure with R (R1) as OC(C)C (ethyl ether), R3 (R2) as C (methyl), and R4 as [nH] (amine). While R and R3 are covered by the claim, R4 ... | 0.7 |
| 191 | WO2022038299A1 | 2 | 是 | 否 | high | CC(C)OC(=O)Oc1cccc2[nH]cc(CCN(CC)CC)c12 | The R3 and R4 groups in the query molecule do not match the allowed values specified in the claim. Specifically, R3 is nH (aziridine), which is not one of the allowed values (hy... | 0.6 |
| 193 | WO2022047583A1 | 2 | 是 | 否 | high | [N+](=O)([O-])c1ccc(O)c2c(CCNC(C)=O)c[nH]c12 | The R3a position in the query molecule is substituted with an oxygen atom, which is not covered by the claim requirements. The claim specifies that non-nitrated positions can on... | 0.8 |

### 9.4 低置信但判断正确

| index | patent_id | selection | 真实 | 预测 | 置信度 | SMILES | 原因摘要 | novelty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | US9655879 | 4 | 否 | 否 | very_low | CC(C)(Cc1ccc(C(=O)Oc2ccc(C(=N)N)cc2(C=O))cc1)C(=O)Nc1cc(C(=O)O)cc(C(=O)O)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |
| 7 | US8039496 | 3 | 否 | 否 | very_low | N#C[C@@H]1C[C@@H](O)[C@H](COc2ccccccc2)[C@H]1CCCc1ccc(C(=O)O)s1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.75 |
| 9 | US8039496 | 3 | 否 | 否 | very_low | N#C[C@@H]1C[C@@H](O)[C@H](COF)[C@H]1CCCc1ccc(C(=O)O)s1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 17 | US12006316 | 3 | 否 | 否 | very_low | Brc1cc2[nH]c3nc(-c4cn(C)nc4[3H])ccc3c2c([3H])n1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.85 |
| 18 | US20170304277A1 | 3 | 否 | 否 | very_low | Cc1cc(-n2ncc3cc(NC(=O)N[C@H]4CN(C)C[C@@H]4c4ccccc4)nc(Cl)c32)ccn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |
| 20 | US9856219 | 3 | 否 | 否 | very_low | O=C(O)c1ccc(-c2ccc3cc(O)cc(S(=O)=O)c3n2)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 21 | US20150174033A1 | 3 | 否 | 否 | very_low | FC(=O)CCc1ccc2c(c1)OCO2 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 24 | US20170239197A1 | 4 | 否 | 否 | very_low | OCCc1cnc(OC(c2ccccc2)C2CNCCO2)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 26 | US9624159 | 4 | 否 | 否 | very_low | c1(C(=O)O)nc(CNc2c(F)ccc(OCC(=O)O)c2F)cc(-c2cccc(F)c2)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |
| 27 | US9624159 | 3 | 否 | 否 | very_low | c1(CON)cc(CNc2c(F)ccc(OCC(=O)O)c2F)cc(-c2cccc(F)c2)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 30 | US9937139 | 3 | 否 | 否 | very_low | Cc1cc(N(CCCl)OCCCl)c(Br)cc1C(C)(CN)CC(=O)O | ### Technical Analysis Details **Patent**: US9937139 **Target Molecule**: Cc1cc(N(CCCl)OCCCl)c(Br)cc1C(C)(CN)CC(=O)O **Markush Structure**: `<r>R</r>C(<r>R</r>)(<r>R</r>)C(<r>R<... | 0.6 |
| 31 | WO2009117421A2 | 3 | 否 | 否 | very_low | c1(C(F)(F)F)cnc(NNC(=O)c2cccn2(Br))c(Cl)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |
| 32 | US10183009 | 4 | 否 | 否 | very_low | CCCC1cc(-c2ccc(C(C)(C)O)cc2)c2cc(NCl)[nH]c2c1=O | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 33 | US9980929 | 3 | 否 | 否 | very_low | COc1ccc(C(CC(=O)N[C@@H](Cc2cccc(Cl)c2)C(=O)N(OC)[C@H](C(=O)C(F)(F)F)C(C)C)c2c... | ### Technical Analysis Details **Patent:** US9980929 **Target Molecule:** COc1ccc(C(CC(=O)N[C@@H](Cc2cccc(Cl)c2)C(=O)N(OC)[C@H](C(=O)C(F)(F)F)C(C)C)c2ccc(Cl)c(Cl)c2)cc1 **Markus... | 0.75 |
| 37 | US20150190323A1 | 4 | 否 | 否 | very_low | CC1(C)CCC(C)(C)c2nc(S(=O)(=O)CCc3ccc(C(=O)O)cc3)ccc21 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.3 |
| 42 | US20110076230A1 | 3 | 否 | 否 | very_low | Fc1ccc(-c2cc3ccc(Cl)c(S(=O)O)c3[nH]2)cn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |
| 45 | US9943507 | 3 | 否 | 否 | very_low | C(C)C(C)CNCC(=O)N1CCc2sc(Br)cc2C1c1cccc(C)n1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 46 | US10526323 | 3 | 否 | 否 | very_low | Cn1nc(C2CC2)c2c(C(=O))cc(Nc3n[nH]c4cccnc34)cc21 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 47 | US20150224105A1 | 3 | 否 | 否 | very_low | CNCCCOc1cc(F)c(-c2c(S)nc(-n3cccn3)nc2NC(C)C)c(F)c1 | ### Technical Analysis Details **Patent:** US20150224105A1 **Target Molecule:** CNCCCOc1cc(F)c(-c2c(S)nc(-n3cccn3)nc2NC(C)C)c(F)c1 **Markush Structure:** ``` <r>*</r>C1=NC(<r>*<... | 0.7 |
| 58 | US20210070703A1 | 3 | 否 | 否 | very_low | O=C(Nc1ccc(F)c(F)c1)c1cc(S(=O)(=O)NC2CCCC2)c(N)cc1F | ## Detailed Analysis ### Patent: US20210070703A1 ### Target Molecule: O=C(Nc1ccc(F)c(F)c1)c1cc(S(=O)(=O)NC2CCCC2)c(N)cc1F ### Markush Structure `<r>R</r>C1=C(<r>R</r>)C(<r>R</r>... | 0.6 |
| 59 | US9902701 | 3 | 否 | 否 | very_low | Cc1cc(Cl)c(Br)c(F)c1C1=NN(CC(=O)N(C)c2cccc(Cl)c2)C(=O)CC1 | ### Technical Analysis Details **Patent:** US9902701 **Target Molecule:** Cc1cc(Cl)c(Br)c(F)c1C1=NN(CC(=O)N(C)c2cccc(Cl)c2)C(=O)CC1 **Markush Structure:** ``` <r>*</r>C1=NN(CC(=... | 0.3 |
| 62 | US9758477 | 4 | 否 | 否 | very_low | O=C(NCc1ccccc1)c1cnc2c(c1)NC(=O)c1ccccc1S2(=O)=O | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.3 |
| 64 | US20230108114A1 | 3 | 否 | 否 | very_low | Cc1ccc2c(c1)C(N)N(C1CCN(C(=O)c3ccc(OCC(F)(F)F)nc3)CC1O)CC2 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |
| 66 | WO2020252229A2 | 3 | 否 | 否 | very_low | CC(=O)c1cncc(NCc2cccnc2)n1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.75 |
| 67 | US9655879 | 3 | 否 | 否 | very_low | CC(C)(Cc1ccc(C(=O)Oc2ccc(C(=N)N)cc2(C=O))s1)C(=O)Nc1cc(C(=O)O)cc(C(=O)O)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |
| 69 | US9884043 | 3 | 否 | 否 | very_low | O=C(O)c1ccc(-c2nn(S(=O)(=O)c3ccccc3Cl)c3ccc(Br)cc23)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.75 |
| 72 | US9849119 | 3 | 否 | 否 | very_low | c1ccc([C@]2(CCNc3ccc(s3))CCOC3(CCCC3)C2)nc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.7 |
| 73 | US8039496 | 4 | 否 | 否 | very_low | N#C[C@@H]1C[C@@H](O)[C@H](C(F)(F)O)[C@H]1CCCc1ccc(C(=O)O)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |
| 79 | US9439968 | 3 | 否 | 否 | very_low | CCCCCCCCCCCOC(=O)CCN(CCC(=O)OCCCCCCCCCCC)CCN1CC(OCC)N(CCN(CCC(=O)OCCCCCCCCCCC... | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.3 |
| 82 | US12006316 | 4 | 否 | 否 | very_low | [3H]c1cc2[nH]c3nc(-c4cn(C)nc4[3H])ccc3c2c([3H])c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.8 |

## 10. 不可评估/标签缺失样本

| index | patent_id | selection | 真实 | 预测 | 置信度 | SMILES | 原因摘要 | novelty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12 | US9763922 | 1 | 缺失 | 否 | very_low | CC(=O)N1CCc2c(c(N3CCc4ccccc43)nn2C)C1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an empty or invalid R-group mapping. | 0.6 |
| 13 | US9884048 | 2 | 缺失 | 否 | very_low | Cc1cc(-n2ncc3c(Cl)c(NC(=O)N[C@H]4CN(C)C[C@@H]4c4ccccc4)ncc32)ccn1 | ### Technical Analysis Details **Patent:** US9884048 **Target Molecule:** Cc1cc(-n2ncc3c(Cl)c(NC(=O)N[C@H]4CN(C)C[C@@H]4c4ccccc4)ncc32)ccn1 **Markush Structure:** `<r>*</r>N1N=C... | 0.7 |
| 14 | US9492447 |  | 缺失 | 缺失 |  | CC(C)(CO)NC(=O)c1nn(-c2ccc(F)cc2F)c2c1C[C@H]1C[C@@H]21 | first image produced empty caption after 3 attempt(s) | n/a |
| 39 | US9988397 |  | 缺失 | 缺失 |  | Cn1ncc2cc3nc(c21)OCCOC[C@H](c1ccccc1)NC(=O)N3 | first image produced empty caption after 3 attempt(s) | n/a |
| 77 | US9492447 |  | 缺失 | 缺失 |  | CC(C)(CO)NC(=O)c1nn(-c2ccc(F)cc2F)c2c1C[C@H]1C(N)[C@@H]21 | first image produced empty caption after 3 attempt(s) | n/a |
| 102 | US9988397 |  | 缺失 | 缺失 |  | BrCn1ncc2cc3nc(c21)OCCOC[C@H](c1ccccc1)NC(=O)N3 | first image produced empty caption after 3 attempt(s) | n/a |
| 159 | US9988397 |  | 缺失 | 缺失 |  | CC(=O)n1ncc2cc3nc(c21)OCCOC[C@H](c1ccccc1)NC(=O)N3 | first image produced empty caption after 3 attempt(s) | n/a |

## 11. 结论与后续排查建议

- 优先排查第一张图 Caption 质量：本批次全部来自 `first_image`，且成功记录中的 `is_markush` 均为 false，容易导致骨架/R-group 匹配失败。
- 针对 FN 做专项复盘：抽样中大量 FN 的原因是 `No verified skeleton/R-group match`，说明前置结构抽取或 Markush 标准化比权利要求推理更可能是瓶颈。
- 重新校准置信度：高置信错误数量较多，建议将 RDKit/NN/LLM 三路证据不一致时的最终置信度下调，并单独输出冲突标记。
- 专利性子任务目前更像轻量 prior-art 提示：每条 prior_arts 数量固定为 1，若要支撑专利性结论，需要接入更完整的检索候选和结构相似度证据。

