# GLM-5.1 Claim Text + First Image Infringement 结果分析

- 源文件：`/root/Muti-Agent-for-Murkush-codex-project-cleanup-20260425/outputs/molpatent-240.glm5_1_claim_text_first_image_infringement.jsonl`
- 报告生成时间：2026-04-28 16:42:59 UTC
- 评估口径：以 `input.expected_is_protected` 作为真实标签，以 `result.is_infringing` 作为模型预测。只有真实标签和预测都非空的记录进入准确率、精确率、召回率等指标。

## 结论摘要

| 指标 | 值 |
| --- | --- |
| 总记录数 | 197 |
| 可评估记录数 | 183 |
| 未纳入准确率记录数 | 14 |
| 正确数 | 133 |
| 错误数 | 50 |
| 总体准确率 | 133 / 183 (72.68%) |
| Balanced accuracy | 72.93% |
| Precision / 覆盖类精确率 | 77.78% |
| Recall / 覆盖类召回率 | 66.32% |
| Specificity / 非覆盖类召回率 | 79.55% |
| F1 / 覆盖类 | 71.59% |

核心判断：该文件在 183 条可评估样本上正确 133 条，准确率为 **72.68%**。错误主要来自 32 条漏判（真实覆盖但预测不覆盖）和 18 条误判（真实不覆盖但预测覆盖），说明当前结果更偏保守，覆盖类召回率低于非覆盖类召回率。

## 混淆矩阵

| 真实 \ 预测 | 预测覆盖 | 预测不覆盖 | 合计 |
| --- | --- | --- | --- |
| 真实覆盖 | 63 | 32 | 95 |
| 真实不覆盖 | 18 | 70 | 88 |
| 合计 | 81 | 102 | 183 |

| 错误类型 | 数量 | 占可评估样本 |
| --- | --- | --- |
| FP：真实不覆盖，预测覆盖 | 18 | 9.84% |
| FN：真实覆盖，预测不覆盖 | 32 | 17.49% |

## 数据完整性

| 项目 | 数量 |
| --- | --- |
| 状态 ok | 185 |
| 状态 error | 12 |
| 真实标签为覆盖 | 102 |
| 真实标签为不覆盖 | 93 |
| 真实标签缺失 | 2 |
| 预测为覆盖 | 83 |
| 预测为不覆盖 | 102 |
| 预测缺失 | 12 |

| 未纳入原因 | 运行状态 | 数量 |
| --- | --- | --- |
| 标签缺失 | ok | 2 |
| 预测缺失 | error | 12 |

### 错误记录

| 错误信息 | 数量 |
| --- | --- |
| Request timed out. | 12 |

## 分组表现

### 按 selection_type

| selection_type | 可评估 | 正确 | 准确率 | 错误 | 真实覆盖 | 真实不覆盖 | 预测覆盖 | 预测不覆盖 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 62 | 43 | 69.35% | 19 | 62 | 0 | 43 | 19 |
| 2 | 33 | 20 | 60.61% | 13 | 33 | 0 | 20 | 13 |
| 3 | 69 | 57 | 82.61% | 12 | 0 | 69 | 12 | 57 |
| 4 | 19 | 13 | 68.42% | 6 | 0 | 19 | 6 | 13 |

### 按模型置信度

| confidence | 可评估 | 正确 | 准确率 | 错误 | 真实覆盖 | 真实不覆盖 | 预测覆盖 | 预测不覆盖 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| moderate | 106 | 77 | 72.64% | 29 | 42 | 64 | 45 | 61 |
| high | 53 | 48 | 90.57% | 5 | 37 | 16 | 36 | 17 |
| low | 24 | 8 | 33.33% | 16 | 16 | 8 | 0 | 24 |

### 按专利

| patent_id | 总记录 | 可评估 | 正确 | 准确率 | FP | FN | TP | TN | error |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| US8039496 | 5 | 5 | 5 | 100.00% | 0 | 0 | 2 | 3 | 0 |
| US10016420 | 4 | 4 | 1 | 25.00% | 0 | 3 | 0 | 1 | 0 |
| US10183009 | 4 | 4 | 4 | 100.00% | 0 | 0 | 2 | 2 | 0 |
| US20170304277A1 | 4 | 4 | 4 | 100.00% | 0 | 0 | 2 | 2 | 0 |
| US20230108114A1 | 4 | 4 | 3 | 75.00% | 1 | 0 | 2 | 1 | 0 |
| US20230131535A1 | 4 | 4 | 3 | 75.00% | 0 | 1 | 1 | 2 | 0 |
| US20230295110A1 | 4 | 4 | 2 | 50.00% | 0 | 2 | 0 | 2 | 0 |
| US9750738 | 4 | 4 | 1 | 25.00% | 1 | 2 | 0 | 1 | 0 |
| US9849119 | 4 | 4 | 4 | 100.00% | 0 | 0 | 0 | 4 | 0 |
| US9856219 | 4 | 4 | 4 | 100.00% | 0 | 0 | 2 | 2 | 0 |
| US9937139 | 4 | 4 | 3 | 75.00% | 0 | 1 | 1 | 2 | 0 |
| WO2022038299A1 | 4 | 4 | 0 | 0.00% | 0 | 4 | 0 | 0 | 0 |
| WO2022047583A1 | 4 | 4 | 4 | 100.00% | 0 | 0 | 2 | 2 | 0 |
| US10285986B2 | 3 | 3 | 2 | 66.67% | 0 | 1 | 2 | 0 | 0 |
| US11168070 | 3 | 3 | 1 | 33.33% | 0 | 2 | 1 | 0 | 0 |
| US11746094 | 3 | 3 | 3 | 100.00% | 0 | 0 | 2 | 1 | 0 |
| US12006316 | 3 | 3 | 2 | 66.67% | 1 | 0 | 1 | 1 | 0 |
| US20150174033A1 | 3 | 3 | 3 | 100.00% | 0 | 0 | 1 | 2 | 0 |
| US20150190323A1 | 3 | 3 | 3 | 100.00% | 0 | 0 | 1 | 2 | 0 |
| US20170239197A1 | 3 | 3 | 3 | 100.00% | 0 | 0 | 1 | 2 | 0 |
| US20210070703A1 | 3 | 3 | 2 | 66.67% | 1 | 0 | 1 | 1 | 0 |
| US20230399337A1 | 3 | 3 | 3 | 100.00% | 0 | 0 | 2 | 1 | 0 |
| US20240109886A1 | 3 | 3 | 3 | 100.00% | 0 | 0 | 2 | 1 | 0 |
| US9233979 | 3 | 3 | 2 | 66.67% | 1 | 0 | 2 | 0 | 0 |
| US9512105 | 3 | 3 | 1 | 33.33% | 0 | 2 | 0 | 1 | 0 |
| US9624159 | 5 | 3 | 3 | 100.00% | 0 | 0 | 1 | 2 | 2 |
| US9655879 | 3 | 3 | 2 | 66.67% | 0 | 1 | 0 | 2 | 0 |
| US9707212 | 3 | 3 | 2 | 66.67% | 1 | 0 | 2 | 0 | 0 |
| US9730936 | 3 | 3 | 1 | 33.33% | 2 | 0 | 1 | 0 | 0 |
| US9758477 | 3 | 3 | 2 | 66.67% | 0 | 1 | 0 | 2 | 0 |
| US9763922 | 4 | 3 | 2 | 66.67% | 1 | 0 | 2 | 0 | 0 |
| US9902701 | 3 | 3 | 3 | 100.00% | 0 | 0 | 2 | 1 | 0 |
| US9943507 | 3 | 3 | 3 | 100.00% | 0 | 0 | 1 | 2 | 0 |
| WO2023230609A1 | 3 | 3 | 1 | 33.33% | 1 | 1 | 1 | 0 | 0 |
| WO2024026368A1 | 3 | 3 | 2 | 66.67% | 1 | 0 | 2 | 0 | 0 |
| US10028967 | 2 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US10196354 | 4 | 2 | 1 | 50.00% | 1 | 0 | 1 | 0 | 2 |
| US10526323 | 3 | 2 | 0 | 0.00% | 1 | 1 | 0 | 0 | 1 |
| US10676478 | 2 | 2 | 1 | 50.00% | 0 | 1 | 0 | 1 | 0 |
| US10968217 | 2 | 2 | 1 | 50.00% | 0 | 1 | 0 | 1 | 0 |
| US11684629 | 2 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US20110076230A1 | 2 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US20150224105A1 | 2 | 2 | 2 | 100.00% | 0 | 0 | 0 | 2 | 0 |
| US20160095854A1 | 2 | 2 | 1 | 50.00% | 0 | 1 | 0 | 1 | 0 |
| US20170128460A1 | 2 | 2 | 1 | 50.00% | 1 | 0 | 1 | 0 | 0 |
| US20170182030A1 | 2 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US20170252328A1 | 2 | 2 | 1 | 50.00% | 0 | 1 | 0 | 1 | 0 |
| US20170266167A1 | 3 | 2 | 2 | 100.00% | 0 | 0 | 2 | 0 | 1 |
| US20190008803A1 | 2 | 2 | 1 | 50.00% | 0 | 1 | 1 | 0 | 0 |
| US20220348549A1 | 2 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US20220396567A1 | 2 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US20230293523A1 | 2 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US20240002351A1 | 2 | 2 | 1 | 50.00% | 0 | 1 | 0 | 1 | 0 |
| US9439968 | 2 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US9492447 | 2 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US9884043 | 2 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US9884048 | 3 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US9895330 | 2 | 2 | 1 | 50.00% | 0 | 1 | 0 | 1 | 0 |
| US9988397 | 3 | 2 | 0 | 0.00% | 2 | 0 | 0 | 0 | 1 |
| WO2009117421A2 | 2 | 2 | 1 | 50.00% | 0 | 1 | 0 | 1 | 0 |
| WO2020247701A2 | 2 | 2 | 1 | 50.00% | 0 | 1 | 0 | 1 | 0 |
| WO2020252229A2 | 2 | 2 | 1 | 50.00% | 1 | 0 | 1 | 0 | 0 |
| WO2022046606A1 | 2 | 2 | 1 | 50.00% | 1 | 0 | 1 | 0 | 0 |
| WO2024062043A1 | 2 | 2 | 2 | 100.00% | 0 | 0 | 1 | 1 | 0 |
| US10010539 | 3 | 1 | 1 | 100.00% | 0 | 0 | 0 | 1 | 2 |
| US10183949 | 1 | 1 | 1 | 100.00% | 0 | 0 | 1 | 0 | 0 |
| US10870623 | 1 | 1 | 1 | 100.00% | 0 | 0 | 1 | 0 | 0 |
| US11773096 | 1 | 1 | 1 | 100.00% | 0 | 0 | 0 | 1 | 0 |
| US20230303562A1 | 3 | 1 | 0 | 0.00% | 0 | 1 | 0 | 0 | 2 |
| US9980929 | 2 | 1 | 1 | 100.00% | 0 | 0 | 0 | 1 | 1 |

## 结果分布

| 维度 | 取值 | 数量 |
| --- | --- | --- |
| model | glm-5.1 | 197 |
| status | ok | 185 |
| status | error | 12 |
| confidence | moderate | 108 |
| confidence | high | 53 |
| confidence | low | 24 |
| confidence | 缺失 | 12 |
| selection_type | 1 | 67 |
| selection_type | 2 | 37 |
| selection_type | 3 | 73 |
| selection_type | 4 | 20 |
| text_source | claim | 197 |

## 运行耗时

| 指标 | 值 |
| --- | --- |
| 样本数 | 197 |
| 总耗时秒 | 34865.51 |
| 平均秒/条 | 176.98 |
| 中位数秒/条 | 95.30 |
| 最短秒/条 | 20.11 |
| 最长秒/条 | 721.81 |

## 误判样例

### False Positive：真实不覆盖，预测覆盖

| index | patent_id | selection_type | 真实覆盖 | 预测覆盖 | confidence | SMILES | reasoning 摘要 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 52 | WO2023230609A1 | 3 | 否 | 是 | moderate | COCCn1c(-c2nc3cc4c(cc3n2OCC)CCN(C[C@@H](C)N)C4=O)cc2cccc(C)c21 | The query molecule contains a benzimidazole-pyrimidine-lactam tricyclic core structure that appears consistent with Formula I of the patent. The substituents present in the molecule - methyl on the benzimidazole aroma... |
| 58 | US20210070703A1 | 3 | 否 | 是 | moderate | O=C(Nc1ccc(F)c(F)c1)c1cc(S(=O)(=O)NC2CCCC2)c(N)cc1F | The query molecule is a benzamide-sulfonamide derivative with N-(3,4-difluorophenyl) amide, 2-fluoro, 5-cyclopentylsulfamoyl, and an amino (NH2) group on the benzamide ring. This closely matches the general structure ... |
| 66 | WO2020252229A2 | 3 | 否 | 是 | moderate | CC(=O)c1cncc(NCc2cccnc2)n1 | The query molecule CC(=O)c1cncc(NCc2cccnc2)n1 contains a pyrimidine core (6-membered ring with 2 nitrogen atoms) which aligns with Formula I's provision that 'one or two of X1, X2, X3, X4 is N'. The acetyl substituent... |
| 82 | US12006316 | 4 | 否 | 是 | moderate | [3H]c1cc2[nH]c3nc(-c4cn(C)nc4[3H])ccc3c2c([3H])c1 | The query molecule contains a pyrimidine ring substituent (explicitly listed as an allowed R1 group), with methyl and tritium substituents on that pyrimidine (methyl is an allowed substituent under R1 option 2; tritiu... |
| 90 | WO2024026368A1 | 3 | 否 | 是 | moderate | ClC1(Cl)CC(c2nc(C(C#N)c3ccncc3)c[nH]2)C1 | The query molecule ClC1(Cl)CC(c2nc(C(C#N)c3ccncc3)c[nH]2)C1 contains structural elements that align with the patent scope: (1) a gem-dichloro cyclopropyl group matching R4 as C3-6cycloalkyl substituted with 2 halogens... |
| 96 | US9730936 | 3 | 否 | 是 | moderate | c1cc(/C=C/C#N)cc(C)c1-c1cccc2c(N)nc(Nc3ccc(C(=O)O)cc3)nc12 | The query molecule contains a quinazoline core with key structural features that align with the patent's formula (I) claims: an amino group (NH2) on the quinazoline matching R3 = —NH2 (claim 7), a methyl group on the ... |
| 102 | US9988397 | 3 | 否 | 是 | moderate | BrCn1ncc2cc3nc(c21)OCCOC[C@H](c1ccccc1)NC(=O)N3 | The query molecule BrCn1ncc2cc3nc(c21)OCCOC[C@H](c1ccccc1)NC(=O)N3 appears to fall within the scope of formula I. The molecule contains: (1) a pyrazole-based macrocyclic core structure consistent with the patent's cla... |
| 107 | US9707212 | 3 | 否 | 是 | high | O=c1[nH]c(-c2ccc(-c3c(C(F)(F)F)ccc4cc(O)ccc4c3=O)cc2)ns1 | The query molecule is 5-(4-(7-hydroxy-4-oxo-2-(trifluoromethyl)-4H-chromen-3-yl)phenyl)-1,3,4-thiadiazol-2(3H)-one. This structure falls within formula (I) of Claim 1: it has a chromen-4-one core (X=O, Y=O), a phenyl ... |
| 123 | US20230108114A1 | 3 | 否 | 是 | high | Cc1ccc2c(c1)CCN(C1CCN(C(=O)c3ccc(OCC(F)(F)F)nc3)CC1O)CC2 | The query molecule Cc1ccc2c(c1)CCN(C1CCN(C(=O)c3ccc(OCC(F)(F)F)nc3)CC1O)CC2 corresponds to ((3-hydroxy-4-(6-methyl-3,4-dihydroisoquinolin-2(1H)-yl)piperidin-1-yl)(6-(2,2,2-trifluoroethoxy)pyridin-3-yl)methanone. This ... |
| 126 | US10196354 | 4 | 否 | 是 | moderate | O=C(O)c1ccc(-c2nn(C(=O)c3c(Cl)cccc3C(F)(F)F)c3ccc(Br)(N4CCC4=O)ccc23)c(F)c1 | The query molecule appears to fall within the scope of Claim 26, which defines a formula where R1 is 'optionally substituted with one, two, three, four or five R8' (no mandatory cycloalkyl requirement). The query mole... |
| 133 | US9763922 | 4 | 否 | 是 | moderate | CC(=O)N1CCc2c(c(N3CCc4ccccc43)ccc2C)C1 | The query molecule CC(=O)N1CCc2c(c(N3CCc4ccccc43)ccc2C)C1 contains structural features that align with the patent's claim scope for Formula (I): (1) an acetyl group on nitrogen matching R4=acetyl as listed in claim 9;... |
| 137 | US20170128460A1 | 3 | 否 | 是 | moderate | Cc1ncc(C(CNC(=O)c2ccc(C(=O)O)cc2Cl)N2CCC(=O)CC2)cn1 | The query molecule appears to match Formula I as shown in the patent image and defined in Claim 1. R1 = methylpyrazinyl (pyrazinyl optionally substituted with C1-6alkyl, where methyl is C1-6alkyl). R2a/R2b combine wit... |

### False Negative：真实覆盖，预测不覆盖

| index | patent_id | selection_type | 真实覆盖 | 预测覆盖 | confidence | SMILES | reasoning 摘要 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | US9655879 | 1 | 是 | 否 | low | CC(C)(Cc1ccc(C(=O)Oc2ccc(C(=N)N)cc2F)s1)C(=O)Nc1cc(C(=O)O)cc(C(=O)O)c1 | The query molecule contains structural features that could individually align with certain patent substituent definitions (thiophene as a possible Ring A per claim 6, fluorine as a possible R7 halogen per claim 1, car... |
| 25 | US10285986B2 | 2 | 是 | 否 | low | [nH]1c2c(c(C)cc1=O)C(=O)c1c(SCC(C)C)cc(=O)n(CC(C)C)c1C2=O | The query molecule is a complex tricyclic quinone derivative with an NH incorporated into the ring system ([nH]), methyl, S-isobutyl (—S—CH2CH(CH3)2), and N-isobutyl (—N—CH2CH(CH3)2) substituents. While the patent cla... |
| 36 | US10968217 | 1 | 是 | 否 | high | Cc1ccc(C(=O)N2CCc3nc(-c4ccccn4)ncc3C2)cn1 | The query molecule is an amide where the carbonyl group (C=O) is attached to the nitrogen atom (N2) of the dihydropyrido ring (C(=O)N2). The patent claims, however, cover ketones ('methanone') where the carbonyl group... |
| 38 | US9750738 | 1 | 是 | 否 | high | CCC1CN(CCCc2ccccc2)CCN1c1cccc(OC)c1 | The patent claims a method using an opioid receptor antagonist represented by Formula (I), which features a core structure where substituents R1-R4 can form a 'bridged heterocyclic ring' or 'cyclo alkyl group' (charac... |
| 48 | US9512105 | 1 | 是 | 否 | low | Cc1ccc(O)c(Oc2ccc(C(=O)N[C@H](CN3CCN(c4cccc(O)c4)[C@@H](C)C3)C(C)C)cc2)c1 | The patent claim 1 describes a compound with a specific core formula (shown in image C00017) with only 4 variable substituent positions (W, X, Y, Z) limited to small groups like hydrogen, C1-3 alkyl, methoxy, halogens... |
| 53 | US10016420 | 2 | 是 | 否 | moderate | O=C(NCCCn1ccnc1)c1ccc(NCCCc2cc(Cl)cc(Cl)c2)nn1 | The query molecule contains propyl chains (CCC = C3 alkylene) connecting the amide nitrogen to a pyrazole ring and connecting another nitrogen to the dichlorophenyl group. However, claim 1 explicitly limits Y to 'a bo... |
| 54 | US10016420 | 2 | 是 | 否 | moderate | O=C(NCCCn1ccnc1)c1ccc(NC(CC)CCc2cc(Cl)cc(Cl)c2)nn1 | The query molecule contains a propyl chain (3 carbons, CCC) between the amide nitrogen and the terminal pyridine ring (NCCCn1ccnc1 in SMILES). However, Claim 1 explicitly limits Y to 'a bond or C1-2 alkylene,' meaning... |
| 57 | US9895330 | 1 | 是 | 否 | moderate | Cc1ccc(CC(=O)Nc2cc(-c3ccccc3-c3nnn[nH]3)ccc2-n2cccn2)cc1 | The query molecule contains a 1,2,3-triazole/imidazole heterocycle (`-n2cccn2`) directly attached to the central phenyl ring, which is not described in the patent claims. The patent claims (particularly claim 1) defin... |
| 65 | US20240002351A1 | 1 | 是 | 否 | moderate | C(C)(Sc1nc2ccccc2c(=O)n1C1CCCC1)C(=O)N(C)c1ccccc1 | The query molecule contains a quinazolinone core (c1nc2ccccc2c(=O)n1C1CCCC1) which broadly matches the bicyclic heterocyclic scaffold of formula (I), but the key substituent is an exocyclic thioether linkage (-S-CH(CH... |
| 70 | US20230303562A1 | 1 | 是 | 否 | moderate | Cc1cccc(-n2nccc2-c2ccc3ncnn3c2)n1 | The query molecule (Cc1cccc(-n2nccc2-c2ccc3ncnn3c2)n1) is a methylpyridine connected via a single bond through a pyrazole to a benzotriazole — three separate ring systems linked by single bonds. The patent's Formula I... |
| 75 | US20190008803A1 | 2 | 是 | 否 | low | Cc1cccc(CN(CCl)CC[C@@]2(c3ccccn3)CCOC3(CCCC3)C2)c1 | The patent's active claims (121-135) all require a pharmaceutical composition, fixed dosage form, or method that combines the defined compound WITH at least one CYP2D6 or CYP3A4 inhibitor. The query molecule is presen... |
| 80 | US20170252328A1 | 1 | 是 | 否 | moderate | CCC(C)CNCC(=O)N1CCc2sccc2C1c1cccc(C)n1 | The query molecule contains a saturated thieno-fused ring system (with -CH2-CH2- in the nitrogen-containing ring, as shown by N1CC...C1 in the SMILES) rather than the aromatic thieno[3,2-c]pyridine core explicitly cla... |

## 解读

- 当前准确率为 72.68%，但覆盖类召回率为 66.32%，低于非覆盖类召回率 79.55%。这表示模型更容易把真实覆盖样本判成不覆盖。
- FN 数量 32，高于 FP 数量 18。若业务目标是尽量发现可能侵权/覆盖的分子，需要重点降低漏判。
- 14 条记录没有进入准确率统计，其中 12 条为运行错误导致预测缺失，2 条为真实标签缺失。补齐这些记录后，总体指标可能轻微变化。
- `confidence` 并不等同于正确性，需要结合上方按置信度分组表查看校准情况。若高置信错误较多，建议后续单独做置信度校准。

