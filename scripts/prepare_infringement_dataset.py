#!/usr/bin/env python3
"""Clean and convert raw dataset into infringement payload format.

Default conversion:
  data/molpatent-240.json -> data/molpatent-240.infringement_input.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalize_patent_id(value: str) -> str:
    return value.strip().upper()


def convert_records(raw_records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    converted: list[dict[str, Any]] = []
    dropped = Counter()

    for idx, item in enumerate(raw_records):
        patent_id = item.get("patent_id")
        target_smiles = item.get("target_smiles")

        if not _is_non_empty_str(patent_id):
            dropped["missing_patent_id"] += 1
            continue
        if not _is_non_empty_str(target_smiles):
            dropped["missing_target_smiles"] += 1
            continue

        label = item.get("label")
        if not isinstance(label, bool):
            dropped["missing_label"] += 1
            continue

        converted.append(
            {
                "patent_id": _normalize_patent_id(patent_id),
                "smiles": target_smiles.strip(),
                "caption": None,
                "expected_is_protected": label,
                "selection_type": item.get("selection_type"),
                "source_index": idx,
            }
        )

    return converted, dict(dropped)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare usable infringement dataset input")
    parser.add_argument(
        "--input",
        default="data/molpatent-240.json",
        help="Path to raw JSON dataset",
    )
    parser.add_argument(
        "--output",
        default="data/molpatent-240.infringement_input.json",
        help="Path to output cleaned JSON dataset",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    with input_path.open("r", encoding="utf-8") as f:
        raw_records = json.load(f)

    if not isinstance(raw_records, list):
        raise ValueError("Input dataset must be a JSON array")

    converted, dropped = convert_records(raw_records)

    payload = {
        "source_file": input_path.as_posix(),
        "target_format": {
            "mode": "infringement",
            "required_fields": [
                "patent_id",
                "smiles",
                "caption",
                "expected_is_protected",
            ],
        },
        "summary": {
            "total_records": len(raw_records),
            "usable_records": len(converted),
            "dropped_records": len(raw_records) - len(converted),
            "drop_reasons": dropped,
        },
        "records": converted,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(converted)} usable records to {output_path}")


if __name__ == "__main__":
    main()
