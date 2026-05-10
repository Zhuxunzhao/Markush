# MolPatent-240 Infringement Truth Analysis

- Generated at: 2026-05-05 08:33:31 UTC
- Input result: `C:\Users\de'l'l\Markush\outputs\results\molpatent-240\legacy\molpatent-240.infringement_full_5bd4761_20260503_182500.json`
- Report path: `C:\Users\de'l'l\Markush\outputs\results\molpatent-240\legacy\molpatent-240.infringement_full_5bd4761_20260503_182500.truth_analysis.md`
- Total records: 197

## 1. Executive Summary

| Metric | Value | Notes |
| --- | --- | --- |
| JSON records | 197 | records in result file |
| successful records | 192 | 97.5% |
| error records | 5 | 2.5% |
| labeled records | 190 | 96.4% |
| evaluable records | 190 | 96.4% |
| Accuracy | 0.568 | correct 108 / 190 |
| Precision | 0.725 | TP 29 / predicted protected 40 |
| Recall / TPR | 0.29 | TP 29 / true protected 100 |
| Specificity / TNR | 0.878 | TN 79 / true unprotected 90 |
| F1 | 0.414 | protected-class F1 |
| Balanced accuracy | 0.584 | mean of TPR and TNR |

Key observations:
- Overall accuracy is 56.8% with TP=29, TN=79, FP=11, FN=71.
- Recall on true protected samples is 29.0%; false negatives dominate the errors, with FN=71.
- Specificity on true unprotected samples is 87.8%; negative-sample rejection is stronger, with TN=79 and FP=11.
- `result.markush_structure.is_markush` distribution: False: 192, missing: 5.

## 2. Raw Summary

| Field | Value |
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

## 3. Infringement Metrics

### 3.1 Confusion Matrix

| Truth / Prediction | Predicted protected | Predicted unprotected | Total |
| --- | --- | --- | --- |
| True protected | 29 | 71 | 100 |
| True unprotected | 11 | 79 | 90 |
| Total | 40 | 150 | 190 |

### 3.2 Label And Prediction Distribution

| Category | Count | Share |
| --- | --- | --- |
| true protected | 100 | 50.8% |
| true unprotected | 90 | 45.7% |
| truth label missing | 7 | 3.6% |
| predicted protected | 40 | 20.3% |
| predicted unprotected | 150 | 76.1% |
| prediction missing/error | 0 | 0.0% |

## 4. Breakdown By Selection Type

| selection_type | Meaning | Evaluable | Correct | Accuracy | Wrong | TP | TN | FP | FN |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | positive sample from patent examples; expected protected | 64 | 19 | 29.7% | 45 | 19 | 0 | 0 | 45 |
| 2 | positive sample manually constructed from claims; expected protected | 36 | 10 | 27.8% | 26 | 10 | 0 | 0 | 26 |
| 3 | negative sample with substituent changed outside claim limits | 70 | 59 | 84.3% | 11 | 0 | 59 | 11 | 0 |
| 4 | negative sample with core Markush scaffold changed | 20 | 20 | 100.0% | 0 | 0 | 20 | 0 | 0 |

## 5. Breakdown By Confidence

| confidence | Evaluable | Correct | Accuracy | Wrong | TP | TN | FP | FN |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| high | 49 | 34 | 69.4% | 15 | 28 | 6 | 10 | 5 |
| low | 1 | 1 | 100.0% | 0 | 0 | 1 | 0 | 0 |
| moderate | 11 | 7 | 63.6% | 4 | 1 | 6 | 1 | 3 |
| very_low | 129 | 66 | 51.2% | 63 | 0 | 66 | 0 | 63 |

## 6. Execution Diagnostics

| Item | Distribution |
| --- | --- |
| status | error: 5, ok: 192 |
| confidence | high: 49, low: 1, missing: 5, moderate: 11, very_low: 131 |
| caption_source | first_image: 197 |
| markush_structure.is_markush | False: 192, missing: 5 |

## 7. False Negatives

True protected, predicted unprotected.

| index | patent_id | selection | truth | prediction | confidence | SMILES | reason/error summary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | WO2020252229A2 | 1 | true | false | very_low | CCc1cncc(NCc2cccnc2)n1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 2 | US9655879 | 1 | true | false | high | CC(C)(Cc1ccc(C(=O)Oc2ccc(C(=N)N)cc2F)s1)C(=O)Nc1cc(C(=O)O)cc(C(=O)O)c1 | 根据权利要求文本和对齐后的 R 基团映射，R[1] 的取值 Nc1cc(C(=O)O)cc(C(=O)O)c1 不符合权利要求中 R[1] 的定义。R[1] 应为 C1-4 烷基或 C2-4 烯基，或者与 R[2] 一起形成 C3-8 环烷环。Nc1cc(C(=O)O)cc... |
| 4 | US10196354 | 1 | true | false | very_low | O=C(O)c1ccc(-c2nn(C(=O)c3c(Cl)cccc3C(F)(F)F)c3cc(N4CCC4=O)ccc23)c(F)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 8 | US8039496 | 2 | true | false | very_low | N#C[C@@H]1C[C@@H](O)[C@H](COc2ccc(F)cc2)[C@H]1CCCc1ccc(C(=O)O)s1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 11 | US9763922 | 2 | true | false | very_low | CC(=O)N1CCc2c(c(N3CCc4ccccc43)nn2CCCCCCC)C1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 15 | US20170128460A1 | 1 | true | false | very_low | Cc1ncc(C(CNC(=O)c2ccc(Cl)cc2Cl)N2CCC(=O)CC2)cn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 19 | US20170304277A1 | 2 | true | false | very_low | BrCCN1N=C2CCN(C(=O)[C@@H](CCc3ccccc3)NC(=O)C(C)(C)N)C[C@]2(Cc2ccccc2)C1=O | R-group label alignment failed. The original caption-local labels cannot be safely used as claim labels, so claim requirement examination... |
| 22 | WO2022046606A1 | 1 | true | false | very_low | O=C1C(Cc2ccc(F)nc2)CCCN1c1nc(-c2ccncc2)n[nH]1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 23 | US10183949 | 2 | true | false | very_low | CC(C)(C)NC(=O)Cn1cnc(-c2ccc(Cl)cc2NC(=O)C(C)(C)C)c(Cl)c1=O | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 28 | US9624159 | 2 | true | false | very_low | c1(C(=O)N)cc(CNc2c(F)ccc(OCC(=O)O)c2F)cc(-c2cccc(F)c2)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 29 | WO2024026368A1 | 2 | true | false | very_low | ClC1(Cl)CC(c2nc(C(CCCCC)c3ccncc3)c[nH]2)C1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 34 | US9730936 | 1 | true | false | very_low | Cc1cc(/C=C/C#N)cc(C)c1-c1cccc2c(N)nc(Nc3ccc(C#N)cc3)nc12 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 35 | US10010539 | 1 | true | false | very_low | C[C@H]1CC[C@@H](n2ncc(-c3ccccc3)n2)CN1C(=O)c1ccccc1-n1nccn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 36 | US10968217 | 1 | true | false | very_low | Cc1ccc(C(=O)N2CCc3nc(-c4ccccn4)ncc3C2)cn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 38 | US9750738 | 1 | true | false | high | CCC1CN(CCCc2ccccc2)CCN1c1cccc(OC)c1 | 查询分子的 R2 基团为 CCCc1ccccc1，这不符合权利要求中对 R2 的定义。根据权利要求，R2 应该是氢、甲基或乙基，并且至少一个 R1, R2, R3 和 R4 不是氢。CCCc1ccccc1 是一个丙基苯基，不在权利要求的范围内。 |
| 43 | US20230399337A1 | 1 | true | false | moderate | Cc1ccc(CN2CCCC2)cc1NC(=O)CSc1nc2cc3c(cc2cc1C#N)OCCO3 | 查询分子中的 R[1] 取值为 C#N，符合权利要求中 R[1] 的定义。然而，R[2] 取值为 c1cc(CN2CCCC2)ccc1C，这是一个取代的苯环，不符合权利要求中 R[2] 的定义（五元杂芳环，含有一个至三个选自氮和硫的原子，并且可以被取代）。因此，该分子不落入... |
| 44 | US9707212 | 1 | true | false | very_low | O=c1[nH]c(-c2ccc(-c3c(C(F)(F)F)oc4cc(O)ccc4c3=O)cc2)ns1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 48 | US9512105 | 1 | true | false | very_low | Cc1ccc(O)c(Oc2ccc(C(=O)N[C@H](CN3CCN(c4cccc(O)c4)[C@@H](C)C3)C(C)C)cc2)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 53 | US10016420 | 2 | true | false | very_low | O=C(NCCCn1ccnc1)c1ccc(NCCCc2cc(Cl)cc(Cl)c2)nn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 54 | US10016420 | 2 | true | false | very_low | O=C(NCCCn1ccnc1)c1ccc(NC(CC)CCc2cc(Cl)cc(Cl)c2)nn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 55 | US11746094 | 1 | true | false | very_low | c1(OC)ccc(Oc2ccc([N+](=O)[O-])c3n[se]nc23)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 56 | US20170266167A1 | 2 | true | false | very_low | COC[C@@H](NC(=O)Nc1cc2cnn(Cc3ccncc3)c2c(CO)n1)c1ccccc1 |  |
| 57 | US9895330 | 1 | true | false | very_low | Cc1ccc(CC(=O)Nc2cc(-c3ccccc3-c3nnn[nH]3)ccc2-n2cccn2)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 61 | US10028967 | 1 | true | false | very_low | CC(=O)Nc1ccc(O)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 63 | US11168070 | 1 | true | false | very_low | Cn1cc(-c2cc3c(cc2C(F)F)N(c2ccc4sc(=O)n(C)c4c2)CCC3)cn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 68 | US10196354 | 2 | true | false | very_low | O=C(O)c1ccc(-c2nn(C(=O)c3c(Cl)cccc3C(F)(F)F)c3c(CC(=O))c(N4CCC4=O)ccc23)c(F)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 74 | US9763922 | 2 | true | false | very_low | CC(=O)N1CCc2c(c(N3CCc4ccccc43)nn2(OC(F)(F)(F)))C1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 75 | US20190008803A1 | 2 | true | false | very_low | Cc1cccc(CN(CCl)CC[C@@]2(c3ccccn3)CCOC3(CCCC3)C2)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 78 | US9439968 | 1 | true | false | very_low | CCCCCCCCCCCOC(=O)CCN(CCC(=O)OCCCCCCCCCCC)CCN1CCN(CCN(CCC(=O)OCCCCCCCCCCC)CCC(=O)OCCCCCC... | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 80 | US20170252328A1 | 1 | true | false | very_low | CCC(C)CNCC(=O)N1CCc2sccc2C1c1cccc(C)n1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 84 | US9856219 | 2 | true | false | very_low | O=C(O)c1ccc(-c2ccc3cc(O)cc(C#N)c3n2)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 85 | US9856219 | 1 | true | false | very_low | O=C(O)c1ccc(-c2ccc3cc(O)cc(F)c3n2)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 86 | US20150174033A1 | 1 | true | false | very_low | CC(=O)CCc1ccc2c(c1)OCO2 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 87 | US20170239197A1 | 1 | true | false | moderate | OCCc1ccc(OC(c2ccccc2)C2CNCCO2)cc1 | 查询分子的 R2 位置取代基为苯环（c1ccccc1），不符合权利要求中 R[2] 的定义 A-OR8。虽然其他 R 基团取值均符合权利要求，但由于 R2 不符合，因此该分子不落入专利保护范围。 |
| 92 | US9937139 | 2 | true | false | very_low | Cc1cc(N(CCCl)OCCCl)c(CC(C)C)cc1C(C)(CN)CC(=O)O | R-group label alignment failed. The original caption-local labels cannot be safely used as claim labels, so claim requirement examination... |
| 93 | WO2009117421A2 | 1 | true | false | very_low | c1(C(F)(F)F)cnc(NNC(=O)c2cccn2-c2cccc(C)c2)c(Cl)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 97 | US10010539 | 2 | true | false | very_low | C[C@H]1CC[C@@H](n2nc(F)c(-c3ccccc3)n2)CN1C(=O)c1ccccc1-n1nccn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 108 | US9943507 | 1 | true | false | very_low | C(C)C(C)CNCC(=O)N1CCc2sccc2C1c1cccc(C)n1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 109 | US20220396567A1 | 1 | true | false | very_low | CC(C)Oc1ccc(CNc2nc(N)nc(-c3ccco3)c2C#N)cc1Br | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 110 | US10526323 | 1 | true | false | very_low | Cn1nc(C2CC2)c2ccc(Nc3n[nH]c4cccnc34)cc21 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 113 | WO2023230609A1 | 2 | true | false | very_low | COCCn1c(-c2nc3cc4c(cc3n2CC(C)C)CCN(C[C@@H](C)N)C4=O)cc2cccc(C)c21 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 116 | US11746094 | 1 | true | false | very_low | c1(OC)ccc(Oc2cc(I)c([N+](=O)[O-])c3n[se]nc23)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 117 | US20170266167A1 | 1 | true | false | very_low | COC[C@@H](NC(=O)Nc1cc2cnn(Cc3ccncc3)c2cn1)c1ccccc1 |  |
| 122 | US11168070 | 2 | true | false | very_low | Cn1cc(-c2cc3c(cn2)N(c2ccc4sc(=O)n(C)c4c2)CCC3)cn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 124 | US20230108114A1 | 2 | true | false | very_low | Cc1ccc2c(c1)C(CC)N(C1CCN(C(=O)c3ccc(OCC(F)(F)F)nc3)CC1O)CC2 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 127 | US10196354 | 2 | true | false | very_low | O=C(O)c1ccc(-c2nn(C(=O)c3c(Cl)cccc3C(F)(F)F)c3cc(N4CCC4=O)c(Br)cc23)c(F)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 128 | US9884043 | 1 | true | false | very_low | O=C(O)c1ccc(-c2nn(S(=O)(=O)c3ccccc3Cl)c3ccncc23)cc1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 131 | US8039496 | 1 | true | false | very_low | N#C[C@@H]1C[C@@H](O)[C@H](COc2cc(Cl)cc(Cl)c2)[C@H]1CCCc1ccc(C(=O)O)s1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 134 | US20190008803A1 | 1 | true | false | very_low | Cc1cccc(CNCC[C@@]2(c3ccccn3)CCOC3(CCCC3)C2)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 140 | US10870623 | 1 | true | false | very_low | COc1ccc(CS(=O)(=O)[C@@H]2C[C@@H](C(=O)N[C@H](C(=O)C(F)(F)F)C(C)C)N(C(=O)[C@@H](C)NC(=O)... | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 141 | US12006316 | 1 | true | false | very_low | [3H]c1cc2[nH]c3nc(-c4cn(C)nc4[3H])ccc3c2c([3H])n1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 148 | US9624159 | 1 | true | false | very_low | c1(C#N)cc(CNc2c(F)ccc(OCC(=O)O)c2F)cc(-c2cccc(F)c2)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 149 | WO2024026368A1 | 1 | true | false | very_low | ClC1(Cl)CC(c2nc(Cc3ccncc3)c[nH]2)C1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 150 | US9937139 | 1 | true | false | very_low | Cc1cc(N(CCCl)OCCCl)ccc1C(C)(CN)CC(=O)O | R-group label alignment failed. The original caption-local labels cannot be safely used as claim labels, so claim requirement examination... |
| 152 | US9980929 | 1 | true | false | very_low | COc1ccc(C(CC(=O)N[C@@H](Cc2cccc(Cl)c2)C(=O)N[C@H](C(=O)C(F)(F)F)C(C)C)c2ccc(Cl)c(Cl)c2)cc1 | R-group label alignment failed. The original caption-local labels cannot be safely used as claim labels, so claim requirement examination... |
| 160 | US11684629 | 1 | true | false | very_low | O=C(O)C[C@@H]1CC[C@H](NC(=O)Cc2cccs2)B(O)O1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 163 | US20230399337A1 | 2 | true | false | very_low | Cc1ccc(CN2CCCC2)cc1NC(=O)CSc1cc2cc3c(cc2cc1C#N)OCCO3 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 164 | US9707212 | 2 | true | false | very_low | O=c1[nH]c(-c2ccc(-c3c(C(F)(F)F)sc4cc(O)ccc4c3=O)cc2)ns1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 168 | US9512105 | 2 | true | false | very_low | Cc1ccc(Br)c(Oc2ccc(C(=O)N[C@H](CN3CCN(c4cccc(O)c4)[C@@H](C)C3)C(C)C)cc2)c1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 171 | US10676478 | 1 | true | false | high | CCCCOc1nc(N)c2[nH]cc(Cc3cnc(CN4CCCC4)s3)c2n1 | 根据权利要求文本，R1 和 R2 与它们所连接的氮原子一起形成一个 4-8 元杂环烷基。查询分子中的 R[1] 和 R[2] 取值为 'CCCC[*:2]'，这表示一个丁基取代基。丁基并不是一个 4-8 元杂环烷基，因此不符合权利要求的限定。 |
| 172 | WO2023230609A1 | 1 | true | false | very_low | COCCn1c(-c2nc3cc4c(cc3n2C)CCN(C[C@@H](C)N)C4=O)cc2cccc(C)c21 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 173 | US10016420 | 1 | true | false | very_low | O=C(NCCCn1ccnc1)c1ccc(NCc2cc(Cl)cc(Cl)c2)nn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 179 | US9758477 | 1 | true | false | very_low | O=C(NCc1ccccc1)c1ccc2c(c1)NC(=O)c1ccccc1S2(=O)=O | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 180 | US11168070 | 2 | true | false | very_low | Cn1cc(-c2cc3c(cc2C(Br)Cl)N(c2ccc4sc(=O)n(C)c4c2)CCC3)cn1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 181 | US20230108114A1 | 1 | true | false | very_low | Cc1ccc2c(c1)CN(C1CCN(C(=O)c3ccc(OCC(F)(F)F)nc3)CC1O)CC2 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 182 | US20230131535A1 | 1 | true | false | very_low | Cn1cc(C(c2ccncc2)c2c(O)ccc(Cl)c2Cl)cn1 | R-group label alignment failed. The original caption-local labels cannot be safely used as claim labels, so claim requirement examination... |
| 190 | WO2022038299A1 | 1 | true | false | high | CC(C)OC(=O)Oc1cccc2[nH]cc(CCN(C)C)c12 | 根据权利要求文本和查询分子的 R 基团取值，R1、R3 和 R4 的取值需要逐一核对。R1 取值为 OC(C)C，符合权利要求中的 -O-(Ci-i2 alkyl)。R3 取值为 C（即甲基），符合权利要求中的甲基或乙基。R4 取值为 [H][H]（即氢），符合权利要求中的... |
| 191 | WO2022038299A1 | 2 | true | false | very_low | CC(C)OC(=O)Oc1cccc2[nH]cc(CCN(CC)CC)c12 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 192 | WO2022047583A1 | 1 | true | false | very_low | [N+](=O)([O-])c1cccc2c(CCNC(C)=O)c[nH]c12 | R-group label alignment failed. The original caption-local labels cannot be safely used as claim labels, so claim requirement examination... |
| 193 | WO2022047583A1 | 2 | true | false | moderate | [N+](=O)([O-])c1ccc(O)c2c(CCNC(C)=O)c[nH]c12 | 查询分子的结构与 Markush 结构匹配，但 R 基团取值不完全符合权利要求。具体来说，R3a 对应的权利要求中的 R4 取值为氧原子（O），这在权利要求中是允许的。然而，R3b 对应的权利要求中的 R2 取值为氢原子（[H][H]），这在权利要求中也是允许的。但是，查询... |
| 196 | WO2022038299A1 | 2 | true | false | high | C(N)OC(=O)Oc1cccc2[nH]cc(CCN(C)C)c12 | 根据权利要求文本和查询分子的结构，R1、R3 和 R4 的取值需要逐一核验。R1 的实际取值为 OCN，不在权利要求中列出的 R1 取值范围内。R3 的实际取值为 C（即甲基），符合权利要求中的限定。R4 的实际取值为 [H][H]（即氢），也符合权利要求中的限定。由于 R... |

## 8. False Positives

True unprotected, predicted protected.

| index | patent_id | selection | truth | prediction | confidence | SMILES | reason/error summary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | US20230303562A1 | 3 | false | true | high | Cc1cccc(-n2nc(I)cc2-c2ccc3ncnn3c2)n1 | 查询分子的 R 基团取值均符合权利要求中的定义。R[1] 是一个 5- 至 10 元杂芳基，符合权利要求中对 R1 的定义；R[2] 是碘，符合权利要求中对 R2 的定义；R[3] 是氢，符合权利要求中对 R3 的定义；R[4] 是一个 5- 至 10 元杂芳基，符合权利要... |
| 40 | WO2020247701A2 | 3 | false | true | high | c1(C(F)(F)F)ccccc1N(OCC)c1sn(-c2ccccc2)c(=O)c1C(=O)N1CCOCC1 | 查询分子中的每个 R 基团取值都符合权利要求1中的定义。R1 取代基 C(=O)N1CCOCC1 符合 -CON(R)2 的定义；R2 取代基 OCC 符合 -R 的定义；R3 取代基 c1ccccc1C(F)(F)F 符合 Cy1 的定义，其中苯环被三氟甲基取代；R4 取... |
| 59 | US9902701 | 3 | false | true | high | Cc1cc(Cl)c(Br)c(F)c1C1=NN(CC(=O)N(C)c2cccc(Cl)c2)C(=O)CC1 | 查询分子中的每个 R 基团取值都符合权利要求中的定义。R1、R2、R3 和 R4 的取值均在权利要求的限定范围内。 |
| 98 | US20170182030A1 | 3 | false | true | moderate | Brc1cc(=O)[nH]c2c1C(=O)c1c(C)cc(=O)n(CC(C)C)c1C2=O | 查询分子的 R 基团取值基本符合权利要求中的定义。R1 和 R3 的取值明确符合权利要求，而 R2 和 R4 的取值虽然符合定义，但需要进一步确认具体的桥接基团。 |
| 125 | US20240002351A1 | 3 | false | true | high | C(C)(Sc1nc2ccccc2c(=O)n1(Cl))C(=O)N(C)c1ccccc1 | 查询分子中的 R 基团取值均符合权利要求中的定义。R1 取值为 C，符合权利要求中 R1 的定义；A1 取值为 CH，符合权利要求中 A1 的定义。 |
| 132 | WO2024062043A1 | 3 | false | true | high | c1ccc2c(c1)Nc1c(NC3CCCCC3)cc(C#N)cc1S2 | 查询分子的 R 基团取值均符合权利要求中的定义。R1 为哌啶基，属于环烷基；R2 为氢，符合 R2 的定义；R3 为氰基，属于杂芳基。因此，该分子落入专利保护范围。 |
| 151 | US10183009 | 3 | false | true | high | CCCCn1cc(-c2ccc(C(C)(C)O)cc2)c2cc(NCl)[nH]c2c1=O | 查询分子的 R 基团取值均符合权利要求中的定义。R1 对应的是一个苯环上的取代基，符合权利要求中 R[1] 的定义；R2 对应的是一个丁基（CCCC），符合权利要求中 R[2] 的定义；R3 对应的是一个 N-氯基团（NCl），符合权利要求中 R[3] 的定义。 |
| 184 | US20230131535A1 | 3 | false | true | high | Cn1cc(C(c2ccncc2)c2c(O)ccc(N=O)c2Cl)cn1 | 查询分子的每个 R 基团取值都符合权利要求中的定义。具体分析如下： 1. X1: [H][H] 符合权利要求中 X1 的定义，即 H。 2. X2: O 符合权利要求中 X2 的定义，即卤素或氧。 3. R1: Cl 符合权利要求中 R1 的定义，即卤素。 4. R2: c... |
| 185 | US20230131535A1 | 3 | false | true | high | Cn1cc(C(c2ccncc2)c2c(O)ccc(Cl)c2(SO))cn1 | 查询分子的每个 R 基团取值都符合权利要求中的定义。X1 和 X2 的取值分别为 [H][H] 和 O，均在权利要求中被允许。R1 和 R2 的取值分别为 SO 和 c1cnn(C)c1，也都在权利要求中被允许。A 的取值为 [H][H]，同样符合权利要求中的定义。 |
| 188 | US20230295110A1 | 3 | false | true | high | Cc1c(F)cnc(C(=O)NCC(=O)O)c1O | 查询分子 Cc1c(F)cnc(C(=O)NCC(=O)O)c1O 的 R 基团取值均符合权利要求中的定义。R[1] 为 C，符合可选取代的 C1-3 烷基；R[2] 为 F，符合卤素；R[3]、R[4] 和 R[5] 均为 [H][H]（氢），符合各自位置的定义；R[6]... |
| 189 | US20230295110A1 | 3 | false | true | high | Cc1c(-c2cccc(F)c2)c([N+](=O)([O-]))nc(C(=O)NCC(=O)O)c1O | 查询分子的每个 R 基团取值都符合权利要求中的定义。R1 为 C，符合 R[1] 的定义；R2 为氟代苯（c1cccc(F)c1），符合 R[2] 的定义；R3 为硝酸根离子 ([NH+](=O)[O-])，符合 R[3] 的定义；R4 和 R5 为氢 ([H][H])，符... |

## 9. Missing Truth Or Prediction

| index | patent_id | selection | truth | prediction | confidence | SMILES | reason/error summary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 12 | US9763922 | 1 | missing | false | very_low | CC(=O)N1CCc2c(c(N3CCc4ccccc43)nn2C)C1 | No verified skeleton/R-group match was produced. Skipping claim requirement examination to avoid a high-confidence conclusion from an emp... |
| 13 | US9884048 | 2 | missing | false | very_low | Cc1cc(-n2ncc3c(Cl)c(NC(=O)N[C@H]4CN(C)C[C@@H]4c4ccccc4)ncc32)ccn1 |  |
| 14 | US9492447 |  | missing | missing |  | CC(C)(CO)NC(=O)c1nn(-c2ccc(F)cc2F)c2c1C[C@H]1C[C@@H]21 | first image produced empty caption after 3 attempt(s) |
| 39 | US9988397 |  | missing | missing |  | Cn1ncc2cc3nc(c21)OCCOC[C@H](c1ccccc1)NC(=O)N3 | first image produced empty caption after 3 attempt(s) |
| 77 | US9492447 |  | missing | missing |  | CC(C)(CO)NC(=O)c1nn(-c2ccc(F)cc2F)c2c1C[C@H]1C(N)[C@@H]21 | first image produced empty caption after 3 attempt(s) |
| 102 | US9988397 |  | missing | missing |  | BrCn1ncc2cc3nc(c21)OCCOC[C@H](c1ccccc1)NC(=O)N3 | first image produced empty caption after 3 attempt(s) |
| 159 | US9988397 |  | missing | missing |  | CC(=O)n1ncc2cc3nc(c21)OCCOC[C@H](c1ccccc1)NC(=O)N3 | first image produced empty caption after 3 attempt(s) |

## 10. Error Records

| index | patent_id | selection | truth | prediction | confidence | SMILES | reason/error summary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 14 | US9492447 |  | missing | missing |  | CC(C)(CO)NC(=O)c1nn(-c2ccc(F)cc2F)c2c1C[C@H]1C[C@@H]21 | first image produced empty caption after 3 attempt(s) |
| 39 | US9988397 |  | missing | missing |  | Cn1ncc2cc3nc(c21)OCCOC[C@H](c1ccccc1)NC(=O)N3 | first image produced empty caption after 3 attempt(s) |
| 77 | US9492447 |  | missing | missing |  | CC(C)(CO)NC(=O)c1nn(-c2ccc(F)cc2F)c2c1C[C@H]1C(N)[C@@H]21 | first image produced empty caption after 3 attempt(s) |
| 102 | US9988397 |  | missing | missing |  | BrCn1ncc2cc3nc(c21)OCCOC[C@H](c1ccccc1)NC(=O)N3 | first image produced empty caption after 3 attempt(s) |
| 159 | US9988397 |  | missing | missing |  | CC(=O)n1ncc2cc3nc(c21)OCCOC[C@H](c1ccccc1)NC(=O)N3 | first image produced empty caption after 3 attempt(s) |
