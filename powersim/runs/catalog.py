"""Catalog of saved runs: one row per run, read from the JSON files only (fast)."""

import json
from pathlib import Path

import pandas as pd

from .run import DEFAULT_RUNS_DIR, INPUTS_FILE, KPIS_FILE, MANIFEST_FILE

_COLUMNS = ["id", "path", "created_at", "label", "tags", "optimizer", "markets", "start", "end"]


def list_runs(root: str | Path = DEFAULT_RUNS_DIR) -> pd.DataFrame:
    """Saved runs under ``root``, most recent first.

    Columns: id, path, created_at, label, tags, optimizer, markets, start, end, and the scalar
    KPIs (revenue per market as ``revenue_<market>``). Folders without a manifest are ignored.
    """
    rows = []
    for manifest_path in sorted(Path(root).glob(f"*/{MANIFEST_FILE}")):
        folder = manifest_path.parent
        try:
            manifest = _read_json(manifest_path)
            inputs = _read_json(folder / INPUTS_FILE)
            kpis = _read_json(folder / KPIS_FILE)
        except (OSError, json.JSONDecodeError):
            continue  # incomplete or corrupted run folder

        row = {
            "id": manifest["id"],
            "path": str(folder),
            "created_at": manifest.get("created_at"),
            "label": manifest.get("label"),
            "tags": manifest.get("tags", []),
            "optimizer": manifest.get("optimizer"),
            "markets": [market["type"] for market in inputs.get("markets", [])],
            "start": inputs.get("period", {}).get("start"),
            "end": inputs.get("period", {}).get("end"),
        }
        for key, value in kpis.items():
            if isinstance(value, dict):
                row.update({f"revenue_{market}": v for market, v in value.items()})
            else:
                row[key] = value
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=_COLUMNS)
    return pd.DataFrame(rows).sort_values("created_at", ascending=False, ignore_index=True)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
