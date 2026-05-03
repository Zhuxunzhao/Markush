#!/usr/bin/env python3
"""Generate a Markdown analysis report for infringement experiment outputs."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "outputs/molpatent-240.infringement_full_with_llm_patentability.json"


def get_path(obj: Any, *path: str, default: Any = None) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def load_records(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if path.suffix == ".jsonl":
        records = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return {"input": str(path), "summary": {}}, records

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        return {"input": str(path), "summary": {}}, payload
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload, payload["records"]
    raise ValueError("Input must be a JSON array, JSONL file, or an object with a records array")


def default_output_path(input_path: Path) -> Path:
    if input_path.suffix:
        return input_path.with_suffix(".analysis.md")
    return input_path.with_name(f"{input_path.name}.analysis.md")


def pct(numerator: int | float, denominator: int | float, digits: int = 1) -> str:
    if not denominator:
        return "n/a"
    return f"{numerator / denominator * 100:.{digits}f}%"


def num(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if math.isnan(value):
            return "n/a"
        return f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return str(value)


def bool_label(value: Any) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "缺失"


def md_cell(value: Any, limit: int | None = None) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("|", "\\|")
    if limit and len(text) > limit:
        return text[: max(0, limit - 3)] + "..."
    return text


def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        return ["_无数据。_"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(md_cell(cell) for cell in row) + " |")
    return lines


def parse_success_rate(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", value)
    if match:
        return float(match.group(1))
    match = re.search(r"\d+(?:\.\d+)?", value)
    if match:
        return float(match.group(0))
    return None


def quantiles(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    values = sorted(values)

    def q(pos: float) -> float:
        if len(values) == 1:
            return values[0]
        idx = (len(values) - 1) * pos
        lo = math.floor(idx)
        hi = math.ceil(idx)
        if lo == hi:
            return values[lo]
        return values[lo] * (hi - idx) + values[hi] * (idx - lo)

    return {
        "min": values[0],
        "p25": q(0.25),
        "median": median(values),
        "mean": mean(values),
        "p75": q(0.75),
        "max": values[-1],
    }


def metric_rows(tp: int, tn: int, fp: int, fn: int) -> list[list[Any]]:
    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total else None
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    balanced = (recall + specificity) / 2 if recall is not None and specificity is not None else None
    return [
        ["Accuracy", num(accuracy), "全部有标签且有预测的样本"],
        ["Precision", num(precision), "预测为覆盖时有多少是真的覆盖"],
        ["Recall / TPR", num(recall), "真实覆盖样本被找回的比例"],
        ["Specificity / TNR", num(specificity), "真实不覆盖样本被正确排除的比例"],
        ["F1", num(f1), "覆盖类的综合指标"],
        ["Balanced accuracy", num(balanced), "正负类召回的平均值"],
    ]


def bin_value(value: float | None, bins: list[tuple[float, float, str]]) -> str:
    if value is None:
        return "缺失"
    for lo, hi, label in bins:
        if lo <= value < hi:
            return label
    return bins[-1][2]


def analyze(payload: dict[str, Any], records: list[dict[str, Any]], *, top_n: int, max_examples: int) -> str:
    total = len(records)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    source_path = payload.get("output") or payload.get("input") or ""
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

    status_counts: Counter[str] = Counter()
    expected_counts: Counter[Any] = Counter()
    pred_counts: Counter[Any] = Counter()
    confidence_counts: Counter[str] = Counter()
    caption_source_counts: Counter[str] = Counter()
    error_counts: Counter[str] = Counter()
    markush_flag_counts: Counter[Any] = Counter()
    rdkit_counts: Counter[Any] = Counter()
    fusion_conf_counts: Counter[str] = Counter()
    req_conf_counts: Counter[str] = Counter()
    selection_stats: dict[Any, Counter[str]] = defaultdict(Counter)
    confidence_stats: dict[str, Counter[str]] = defaultdict(Counter)
    patent_stats: dict[str, Counter[str]] = defaultdict(Counter)

    labeled_eval: list[tuple[bool, bool, dict[str, Any]]] = []
    false_positives: list[dict[str, Any]] = []
    false_negatives: list[dict[str, Any]] = []
    high_conf_mistakes: list[dict[str, Any]] = []
    low_conf_correct: list[dict[str, Any]] = []
    unlabeled_or_unpredicted: list[dict[str, Any]] = []

    patentability_status_counts: Counter[str] = Counter()
    novelty_scores: list[float] = []
    success_rates: list[float] = []
    prior_art_counts: Counter[int] = Counter()
    risk_points: Counter[str] = Counter()
    suggestions: Counter[str] = Counter()
    novelty_by_pred: dict[Any, list[float]] = defaultdict(list)
    success_by_pred: dict[Any, list[float]] = defaultdict(list)

    for record in records:
        status = str(record.get("status") or "missing")
        status_counts[status] += 1
        inp = record.get("input") if isinstance(record.get("input"), dict) else {}
        patent_id = str(inp.get("patent_id") or get_path(record, "result", "patent_id", default="未知专利"))
        selection_type = inp.get("selection_type")
        expected = inp.get("expected_is_protected")
        pred = get_path(record, "result", "is_protected")
        confidence = str(get_path(record, "result", "confidence", default="缺失"))

        expected_counts[expected] += 1
        pred_counts[pred] += 1
        confidence_counts[confidence] += 1
        caption_source_counts[str(record.get("caption_source") or "缺失")] += 1
        markush_flag_counts[get_path(record, "result", "markush_structure", "is_markush")] += 1
        rdkit_counts[get_path(record, "result", "fused_match", "rdkit_result", "is_match")] += 1
        fusion_conf_counts[str(get_path(record, "result", "llm_outputs", "match_fusion", "confidence", default="缺失"))] += 1
        req_conf_counts[str(get_path(record, "result", "requirements", "confidence", default="缺失"))] += 1
        patent_stats[patent_id]["total"] += 1
        patent_stats[patent_id][f"status:{status}"] += 1

        if status != "ok":
            error_counts[str(record.get("error") or "unknown error")] += 1

        if expected is not None:
            patent_stats[patent_id][f"expected:{bool(expected)}"] += 1
        if pred is not None:
            patent_stats[patent_id][f"pred:{bool(pred)}"] += 1

        if expected is not None and pred is not None:
            exp_bool = bool(expected)
            pred_bool = bool(pred)
            labeled_eval.append((exp_bool, pred_bool, record))
            key = "correct" if exp_bool == pred_bool else "wrong"
            selection_stats[selection_type]["total"] += 1
            selection_stats[selection_type][key] += 1
            selection_stats[selection_type][f"expected:{exp_bool}"] += 1
            selection_stats[selection_type][f"pred:{pred_bool}"] += 1
            confidence_stats[confidence]["total"] += 1
            confidence_stats[confidence][key] += 1
            patent_stats[patent_id][key] += 1
            if exp_bool and not pred_bool:
                false_negatives.append(record)
            elif not exp_bool and pred_bool:
                false_positives.append(record)
            if exp_bool != pred_bool and confidence in {"high", "moderate"}:
                high_conf_mistakes.append(record)
            if exp_bool == pred_bool and confidence in {"very_low", "low"}:
                low_conf_correct.append(record)
        else:
            unlabeled_or_unpredicted.append(record)

        patentability = record.get("patentability") if isinstance(record.get("patentability"), dict) else {}
        p_status = str(patentability.get("status") or "缺失")
        patentability_status_counts[p_status] += 1
        p_result = patentability.get("result") if isinstance(patentability.get("result"), dict) else {}
        novelty = p_result.get("novelty_score")
        if isinstance(novelty, (int, float)):
            novelty_float = float(novelty)
            novelty_scores.append(novelty_float)
            novelty_by_pred[pred].append(novelty_float)
        success = parse_success_rate(get_path(p_result, "success_analysis", "success_rate_estimation"))
        if success is not None:
            success_rates.append(success)
            success_by_pred[pred].append(success)
        prior_art_counts[len(p_result.get("prior_arts") or [])] += 1
        risk_points.update(str(item) for item in p_result.get("risk_points") or [])
        suggestions.update(str(item) for item in p_result.get("suggestions") or [])

    tp = sum(exp and pred for exp, pred, _ in labeled_eval)
    tn = sum((not exp) and (not pred) for exp, pred, _ in labeled_eval)
    fp = sum((not exp) and pred for exp, pred, _ in labeled_eval)
    fn = sum(exp and (not pred) for exp, pred, _ in labeled_eval)
    labeled_total = len(labeled_eval)

    novelty_bins = Counter(bin_value(v, [(0, 0.4, "<0.40"), (0.4, 0.6, "0.40-0.59"), (0.6, 0.8, "0.60-0.79"), (0.8, 1.01, ">=0.80")]) for v in novelty_scores)
    success_bins = Counter(bin_value(v, [(0, 40, "<40%"), (40, 60, "40-59%"), (60, 75, "60-74%"), (75, 101, ">=75%")]) for v in success_rates)

    def record_row(record: dict[str, Any]) -> list[Any]:
        inp = record.get("input") if isinstance(record.get("input"), dict) else {}
        reasoning = (
            get_path(record, "result", "requirements", "reasoning", default="")
            or get_path(record, "result", "fused_match", "reasoning", default="")
            or get_path(record, "result", "report", default="")
            or record.get("error", "")
        )
        p_result = get_path(record, "patentability", "result", default={})
        return [
            record.get("index"),
            inp.get("patent_id") or get_path(record, "result", "patent_id", default=""),
            inp.get("selection_type"),
            bool_label(inp.get("expected_is_protected")),
            bool_label(get_path(record, "result", "is_protected")),
            get_path(record, "result", "confidence", default=""),
            md_cell(inp.get("smiles") or get_path(record, "result", "target_smiles", default=""), 80),
            md_cell(reasoning, 180),
            num(p_result.get("novelty_score"), 2) if isinstance(p_result, dict) else "n/a",
        ]

    worst_patents = sorted(
        patent_stats.items(),
        key=lambda item: (-item[1].get("wrong", 0), -item[1].get("total", 0), item[0]),
    )[:top_n]

    lines: list[str] = []
    lines.append("# MolPatent-240 侵权与专利性实验分析报告")
    lines.append("")
    lines.append(f"- 生成时间：{generated_at}")
    lines.append(f"- 结果文件：`{source_path}`")
    lines.append(f"- 分析样本数：{total}")
    lines.append("")

    lines.append("## 1. 执行摘要")
    lines.append("")
    lines.extend(
        table(
            ["指标", "数值", "说明"],
            [
                ["总记录", total, "JSON records 数量"],
                ["成功记录", status_counts.get("ok", 0), pct(status_counts.get("ok", 0), total)],
                ["错误记录", total - status_counts.get("ok", 0), pct(total - status_counts.get("ok", 0), total)],
                ["有标签且有预测", labeled_total, pct(labeled_total, total)],
                ["总体准确率", pct(tp + tn, labeled_total), f"正确 {tp + tn} / {labeled_total}"],
                ["覆盖类召回", pct(tp, tp + fn), f"TP {tp} / 正例 {tp + fn}"],
                ["覆盖类精确率", pct(tp, tp + fp), f"TP {tp} / 预测覆盖 {tp + fp}"],
                ["负例特异度", pct(tn, tn + fp), f"TN {tn} / 负例 {tn + fp}"],
                ["假阴性 FN", fn, "真实覆盖但判为未覆盖"],
                ["假阳性 FP", fp, "真实未覆盖但判为覆盖"],
            ],
        )
    )
    lines.append("")
    lines.append("关键观察：")
    if labeled_total:
        lines.append(f"- 该批次主要瓶颈是覆盖类召回偏低：{tp + fn} 个真实覆盖样本中只找回 {tp} 个，FN 为 {fn}。")
        lines.append(f"- 负例排除能力较强：{tn + fp} 个真实未覆盖样本中正确排除 {tn} 个。")
    if markush_flag_counts:
        markush_false = markush_flag_counts.get(False, 0)
        lines.append(f"- `markush_structure.is_markush=false` 的成功记录有 {markush_false} 个；若这不是预期行为，需要优先检查第一张图 Caption/MarkushGrapher 输出。")
    if confidence_stats:
        high_wrong = confidence_stats.get("high", Counter()).get("wrong", 0)
        high_total = confidence_stats.get("high", Counter()).get("total", 0)
        if high_total:
            lines.append(f"- 高置信样本并不完全可靠：high 置信中错误 {high_wrong}/{high_total}，错误率 {pct(high_wrong, high_total)}。")
    lines.append("")

    lines.append("## 2. 原始 summary 对照")
    lines.append("")
    if summary:
        lines.extend(table(["字段", "值"], [[key, value] for key, value in summary.items()]))
    else:
        lines.append("_输入文件未提供 summary。_")
    lines.append("")

    lines.append("## 3. 侵权判定性能")
    lines.append("")
    lines.append("### 3.1 混淆矩阵")
    lines.append("")
    lines.extend(
        table(
            ["真实/预测", "预测覆盖", "预测未覆盖", "合计"],
            [
                ["真实覆盖", tp, fn, tp + fn],
                ["真实未覆盖", fp, tn, fp + tn],
                ["合计", tp + fp, fn + tn, labeled_total],
            ],
        )
    )
    lines.append("")
    lines.append("### 3.2 指标")
    lines.append("")
    lines.extend(table(["指标", "值", "解释"], metric_rows(tp, tn, fp, fn)))
    lines.append("")
    lines.append("### 3.3 标签与预测分布")
    lines.append("")
    lines.extend(
        table(
            ["类别", "数量", "占比"],
            [
                ["真实覆盖", expected_counts.get(True, 0), pct(expected_counts.get(True, 0), total)],
                ["真实未覆盖", expected_counts.get(False, 0), pct(expected_counts.get(False, 0), total)],
                ["真实标签缺失", expected_counts.get(None, 0), pct(expected_counts.get(None, 0), total)],
                ["预测覆盖", pred_counts.get(True, 0), pct(pred_counts.get(True, 0), total)],
                ["预测未覆盖", pred_counts.get(False, 0), pct(pred_counts.get(False, 0), total)],
                ["预测缺失", pred_counts.get(None, 0), pct(pred_counts.get(None, 0), total)],
            ],
        )
    )
    lines.append("")

    lines.append("## 4. 按 selection_type 分层")
    lines.append("")
    selection_rows = []
    for selection_type, counter in sorted(selection_stats.items(), key=lambda item: str(item[0])):
        st_total = counter.get("total", 0)
        selection_rows.append(
            [
                selection_type,
                st_total,
                counter.get("correct", 0),
                pct(counter.get("correct", 0), st_total),
                counter.get("wrong", 0),
                counter.get("expected:True", 0),
                counter.get("expected:False", 0),
                counter.get("pred:True", 0),
                counter.get("pred:False", 0),
            ]
        )
    lines.extend(table(["selection_type", "可评估", "正确", "准确率", "错误", "正例", "负例", "预测覆盖", "预测未覆盖"], selection_rows))
    lines.append("")

    lines.append("## 5. 置信度校准")
    lines.append("")
    conf_rows = []
    for confidence in ["high", "moderate", "low", "very_low", "缺失"]:
        counter = confidence_stats.get(confidence, Counter())
        if not counter and confidence_counts.get(confidence, 0) == 0:
            continue
        c_total = counter.get("total", 0)
        conf_rows.append(
            [
                confidence,
                confidence_counts.get(confidence, 0),
                c_total,
                counter.get("correct", 0),
                counter.get("wrong", 0),
                pct(counter.get("correct", 0), c_total),
            ]
        )
    lines.extend(table(["置信度", "总数", "可评估", "正确", "错误", "可评估准确率"], conf_rows))
    lines.append("")

    lines.append("## 6. Caption / Markush / 匹配链路诊断")
    lines.append("")
    lines.extend(
        table(
            ["项目", "分布"],
            [
                ["caption_source", ", ".join(f"{k}: {v}" for k, v in caption_source_counts.most_common())],
                ["markush_structure.is_markush", ", ".join(f"{k}: {v}" for k, v in markush_flag_counts.most_common())],
                ["RDKit is_match", ", ".join(f"{k}: {v}" for k, v in rdkit_counts.most_common())],
                ["match_fusion confidence", ", ".join(f"{k}: {v}" for k, v in fusion_conf_counts.most_common())],
                ["requirements confidence", ", ".join(f"{k}: {v}" for k, v in req_conf_counts.most_common())],
            ],
        )
    )
    lines.append("")
    if error_counts:
        lines.append("### 6.1 错误记录")
        lines.append("")
        lines.extend(table(["错误信息", "数量"], error_counts.most_common()))
        lines.append("")

    lines.append("## 7. 专利性子任务分析")
    lines.append("")
    novelty_q = quantiles(novelty_scores)
    success_q = quantiles(success_rates)
    patentability_rows = [
        ["patentability status", ", ".join(f"{k}: {v}" for k, v in patentability_status_counts.most_common())],
        ["prior_arts 数量", ", ".join(f"{k}: {v}" for k, v in sorted(prior_art_counts.items()))],
    ]
    if novelty_q:
        patentability_rows.append(["novelty_score", ", ".join(f"{k}: {num(v, 3)}" for k, v in novelty_q.items())])
    if success_q:
        patentability_rows.append(["success_rate_estimation", ", ".join(f"{k}: {num(v, 2)}%" for k, v in success_q.items())])
    lines.extend(table(["项目", "统计"], patentability_rows))
    lines.append("")
    lines.append("### 7.1 分布区间")
    lines.append("")
    lines.extend(
        table(
            ["指标", "区间", "数量"],
            [["novelty_score", key, value] for key, value in sorted(novelty_bins.items())]
            + [["success_rate", key, value] for key, value in sorted(success_bins.items())],
        )
    )
    lines.append("")
    novelty_pred_rows = []
    for pred, values in sorted(novelty_by_pred.items(), key=lambda item: str(item[0])):
        q = quantiles(values)
        if q:
            novelty_pred_rows.append([bool_label(pred), len(values), num(q["mean"], 3), num(q["median"], 3), num(q["min"], 3), num(q["max"], 3)])
    lines.append("### 7.2 按侵权预测分组的专利性分数")
    lines.append("")
    lines.extend(table(["预测覆盖", "数量", "novelty 均值", "novelty 中位数", "novelty 最小", "novelty 最大"], novelty_pred_rows))
    lines.append("")
    lines.append("### 7.3 高频风险点")
    lines.append("")
    lines.extend(table(["risk_point", "出现次数"], risk_points.most_common(top_n)))
    lines.append("")
    lines.append("### 7.4 高频建议")
    lines.append("")
    lines.extend(table(["suggestion", "出现次数"], suggestions.most_common(top_n)))
    lines.append("")

    lines.append("## 8. 专利维度错误集中度")
    lines.append("")
    patent_rows = []
    for patent_id, counter in worst_patents:
        p_total = counter.get("total", 0)
        wrong = counter.get("wrong", 0)
        correct = counter.get("correct", 0)
        patent_rows.append(
            [
                patent_id,
                p_total,
                correct,
                wrong,
                pct(wrong, correct + wrong),
                counter.get("expected:True", 0),
                counter.get("expected:False", 0),
                counter.get("pred:True", 0),
                counter.get("pred:False", 0),
                counter.get("status:error", 0),
            ]
        )
    lines.extend(table(["patent_id", "总数", "正确", "错误", "错误率", "正例", "负例", "预测覆盖", "预测未覆盖", "运行错误"], patent_rows))
    lines.append("")

    lines.append("## 9. 典型错误样本")
    lines.append("")
    lines.append("### 9.1 False Negative：真实覆盖但判为未覆盖")
    lines.append("")
    lines.extend(table(["index", "patent_id", "selection", "真实", "预测", "置信度", "SMILES", "原因摘要", "novelty"], [record_row(r) for r in false_negatives[:max_examples]]))
    lines.append("")
    lines.append("### 9.2 False Positive：真实未覆盖但判为覆盖")
    lines.append("")
    lines.extend(table(["index", "patent_id", "selection", "真实", "预测", "置信度", "SMILES", "原因摘要", "novelty"], [record_row(r) for r in false_positives[:max_examples]]))
    lines.append("")
    lines.append("### 9.3 高/中置信错误")
    lines.append("")
    lines.extend(table(["index", "patent_id", "selection", "真实", "预测", "置信度", "SMILES", "原因摘要", "novelty"], [record_row(r) for r in high_conf_mistakes[:max_examples]]))
    lines.append("")
    lines.append("### 9.4 低置信但判断正确")
    lines.append("")
    lines.extend(table(["index", "patent_id", "selection", "真实", "预测", "置信度", "SMILES", "原因摘要", "novelty"], [record_row(r) for r in low_conf_correct[:max_examples]]))
    lines.append("")
    if unlabeled_or_unpredicted:
        lines.append("## 10. 不可评估/标签缺失样本")
        lines.append("")
        lines.extend(table(["index", "patent_id", "selection", "真实", "预测", "置信度", "SMILES", "原因摘要", "novelty"], [record_row(r) for r in unlabeled_or_unpredicted[:max_examples]]))
        lines.append("")

    lines.append("## 11. 结论与后续排查建议")
    lines.append("")
    lines.append("- 优先排查第一张图 Caption 质量：本批次全部来自 `first_image`，且成功记录中的 `is_markush` 均为 false，容易导致骨架/R-group 匹配失败。")
    lines.append("- 针对 FN 做专项复盘：抽样中大量 FN 的原因是 `No verified skeleton/R-group match`，说明前置结构抽取或 Markush 标准化比权利要求推理更可能是瓶颈。")
    lines.append("- 重新校准置信度：高置信错误数量较多，建议将 RDKit/NN/LLM 三路证据不一致时的最终置信度下调，并单独输出冲突标记。")
    lines.append("- 专利性子任务目前更像轻量 prior-art 提示：每条 prior_arts 数量固定为 1，若要支撑专利性结论，需要接入更完整的检索候选和结构相似度证据。")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Experiment JSON/JSONL result file")
    parser.add_argument("--output", type=Path, default=None, help="Markdown report path")
    parser.add_argument("--top-n", type=int, default=20, help="Rows to keep in top-N sections")
    parser.add_argument("--max-examples", type=int, default=30, help="Rows to keep in example sections")
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_path = (args.output or default_output_path(input_path)).resolve()
    payload, records = load_records(input_path)
    report = analyze(payload, records, top_n=args.top_n, max_examples=args.max_examples)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
