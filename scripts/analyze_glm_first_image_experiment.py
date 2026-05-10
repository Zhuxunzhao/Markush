#!/usr/bin/env python3
"""Generate metrics for direct GLM first-image infringement outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("Input must be a JSON object with a records array")
    return payload


def _pct(num: int | float, den: int | float) -> str:
    return "n/a" if not den else f"{num / den * 100:.2f}%"


def _metric(num: int | float, den: int | float) -> str:
    return "n/a" if not den else f"{num / den:.4f}"


def _row(record: dict[str, Any]) -> list[str]:
    inp = record.get("input") if isinstance(record.get("input"), dict) else {}
    result = record.get("result") if isinstance(record.get("result"), dict) else {}
    return [
        str(record.get("index", "")),
        str(inp.get("patent_id", "")),
        str(inp.get("selection_type", "")),
        str(inp.get("expected_is_protected", "")),
        str(result.get("is_infringing", "")),
        str(result.get("confidence", "")),
        str(record.get("error", ""))[:180].replace("\n", " "),
    ]


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        return ["_No rows._"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        cells = [str(cell).replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def analyze(payload: dict[str, Any], *, max_examples: int) -> str:
    records: list[dict[str, Any]] = payload["records"]
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

    status_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    tp = tn = fp = fn = 0
    unlabeled: list[dict[str, Any]] = []
    unpredicted: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    false_pos: list[dict[str, Any]] = []
    false_neg: list[dict[str, Any]] = []

    for record in records:
        status = str(record.get("status") or "missing")
        status_counts[status] = status_counts.get(status, 0) + 1
        if status != "ok":
            errors.append(record)

        inp = record.get("input") if isinstance(record.get("input"), dict) else {}
        result = record.get("result") if isinstance(record.get("result"), dict) else {}
        expected = inp.get("expected_is_protected")
        pred = result.get("is_infringing")
        confidence = str(result.get("confidence") or "missing")
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1

        if expected is None:
            unlabeled.append(record)
            continue
        if pred is None:
            unpredicted.append(record)
            continue

        expected_bool = bool(expected)
        pred_bool = bool(pred)
        if expected_bool and pred_bool:
            tp += 1
        elif not expected_bool and not pred_bool:
            tn += 1
        elif not expected_bool and pred_bool:
            fp += 1
            false_pos.append(record)
        elif expected_bool and not pred_bool:
            fn += 1
            false_neg.append(record)

    evaluable = tp + tn + fp + fn
    precision = _metric(tp, tp + fp)
    recall = _metric(tp, tp + fn)
    specificity = _metric(tn, tn + fp)
    accuracy = _metric(tp + tn, evaluable)

    lines = [
        "# GLM First-Image Infringement Evaluation",
        "",
        f"- Input: `{payload.get('input', '')}`",
        f"- Output: `{payload.get('output', '')}`",
        f"- Model: `{summary.get('model', '')}`",
        f"- Base URL: `{summary.get('base_url', '')}`",
        f"- Records: {len(records)}",
        "",
        "## Summary",
        "",
    ]
    lines.extend(
        _table(
            ["Metric", "Value"],
            [
                ["status counts", ", ".join(f"{k}: {v}" for k, v in sorted(status_counts.items()))],
                ["confidence counts", ", ".join(f"{k}: {v}" for k, v in sorted(confidence_counts.items()))],
                ["evaluable", evaluable],
                ["unlabeled", len(unlabeled)],
                ["unpredicted", len(unpredicted)],
                ["errors", len(errors)],
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Metrics",
            "",
        ]
    )
    lines.extend(
        _table(
            ["Metric", "Value", "Formula"],
            [
                ["Accuracy", accuracy, f"(TP + TN) / total = {tp + tn} / {evaluable}"],
                ["Precision", precision, f"TP / (TP + FP) = {tp} / {tp + fp}"],
                ["Recall", recall, f"TP / (TP + FN) = {tp} / {tp + fn}"],
                ["Specificity", specificity, f"TN / (TN + FP) = {tn} / {tn + fp}"],
                ["False positive rate", _pct(fp, tn + fp), f"FP / negatives = {fp} / {tn + fp}"],
                ["False negative rate", _pct(fn, tp + fn), f"FN / positives = {fn} / {tp + fn}"],
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Confusion Matrix",
            "",
        ]
    )
    lines.extend(
        _table(
            ["Truth / Prediction", "Predicted true", "Predicted false"],
            [
                ["True", tp, fn],
                ["False", fp, tn],
            ],
        )
    )
    lines.extend(["", "## False Negatives", ""])
    lines.extend(_table(["index", "patent_id", "selection_type", "expected", "pred", "confidence", "error"], [_row(r) for r in false_neg[:max_examples]]))
    lines.extend(["", "## False Positives", ""])
    lines.extend(_table(["index", "patent_id", "selection_type", "expected", "pred", "confidence", "error"], [_row(r) for r in false_pos[:max_examples]]))
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(_table(["index", "patent_id", "selection_type", "expected", "pred", "confidence", "error"], [_row(r) for r in errors[:max_examples]]))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-examples", type=int, default=30)
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_path = (args.output or input_path.with_suffix(".analysis.md")).resolve()
    payload = _load(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(analyze(payload, max_examples=args.max_examples), encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
