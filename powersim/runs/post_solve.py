"""Post-solve tasks: derived data computed from a saved run, stored next to it.

A run stores what the simulation produced (inputs, solver, kpis, time series). Derived data
(indicators, aggregated tables...) is computed afterwards from those files only, so it can be
added or recomputed for old runs without re-simulating.

Each task has a ``name`` and a ``version`` and returns :class:`Derived` (scalar KPIs + small
tables). Results are stored in the run folder::

    derived/<task>.json                  task, version, computed_at, powersim_version, kpis
    derived/<task>__<table>.parquet      one file per table (index kept)

Bump a task ``version`` whenever its formulas change: :func:`update_runs` then recomputes it for
every run that has an older version. The core run files (and ``SCHEMA_VERSION``) are untouched.

Usage::

    run.save()                      # runs every registered task after saving
    update_runs("runs")             # add/refresh derived data of existing runs
    load_derived(run.path, "indicators").kpis["spread"]["tbn_capture"]

Command line: ``powersim-post-solve --runs runs [--force] [--task indicators]``.
"""

import argparse
import json
import math
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path

import pandas as pd

DERIVED_DIR = "derived"


@dataclass
class Derived:
    """Output of a post-solve task: JSON-serialisable scalar KPIs and small tables."""

    kpis: dict = field(default_factory=dict)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    version: int | None = None
    computed_at: str | None = None


@dataclass(frozen=True)
class PostSolveTask:
    """A derived computation. ``compute(run)`` receives a :class:`SimulationRun`."""

    name: str
    version: int
    compute: Callable[[object], Derived]


_TASKS: dict[str, PostSolveTask] = {}


def register(task: PostSolveTask) -> PostSolveTask:
    """Register (or replace) a task; it will run on save and in :func:`update_runs`."""
    if "__" in task.name or not task.name:
        raise ValueError(f"Invalid task name {task.name!r} (non-empty, no '__')")
    _TASKS[task.name] = task
    return task


def tasks() -> dict[str, PostSolveTask]:
    """Registered tasks by name."""
    return dict(_TASKS)


# ---------------------------------------------------------------------- running
def run_post_solve(run, names: list[str] | None = None, force: bool = False) -> dict[str, str]:
    """Compute the tasks for ``run`` and store them if the run is saved (``run.path``).

    Returns ``{task: status}`` with status ``"computed"``, ``"up-to-date"`` (stored version is
    current; use ``force`` to recompute) or ``"error: ..."``. A failing task never raises: it is
    reported as a warning so saving a run cannot fail because of derived data.
    """
    statuses = {}
    for name in names or list(_TASKS):
        task = _TASKS[name]
        if not force and run.path is not None and _stored_version(run.path, name) == task.version:
            statuses[name] = "up-to-date"
            continue
        try:
            derived = task.compute(run)
            derived.version = task.version
            derived.computed_at = datetime.now(UTC).isoformat(timespec="seconds")
            if run.path is not None:
                _write(Path(run.path), name, derived)
            statuses[name] = "computed"
        except Exception as error:  # noqa: BLE001 - derived data must never break a run
            warnings.warn(
                f"Post-solve task {name!r} failed for run {run.id}: {error}", stacklevel=2
            )
            statuses[name] = f"error: {error}"
    return statuses


def update_runs(
    root: str | Path = "runs", names: list[str] | None = None, force: bool = False
) -> list[tuple[str, str, str]]:
    """Run the tasks on every saved run under ``root``. Returns ``(run id, task, status)``."""
    from .run import MANIFEST_FILE, SimulationRun

    report = []
    for manifest in sorted(Path(root).glob(f"*/{MANIFEST_FILE}")):
        run = SimulationRun.load(manifest.parent)
        for name, status in run_post_solve(run, names, force).items():
            report.append((run.id, name, status))
    return report


# ---------------------------------------------------------------------- storage
def load_derived(path: str | Path, name: str) -> Derived | None:
    """Stored output of task ``name`` for the run saved in ``path`` (None if absent)."""
    folder = Path(path) / DERIVED_DIR
    meta_file = folder / f"{name}.json"
    if not meta_file.exists():
        return None
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    tables = {
        file.stem.split("__", 1)[1]: pd.read_parquet(file)
        for file in sorted(folder.glob(f"{name}__*.parquet"))
    }
    return Derived(
        kpis=meta.get("kpis", {}),
        tables=tables,
        version=meta.get("version"),
        computed_at=meta.get("computed_at"),
    )


def _stored_version(path: str | Path, name: str) -> int | None:
    meta_file = Path(path) / DERIVED_DIR / f"{name}.json"
    if not meta_file.exists():
        return None
    try:
        return json.loads(meta_file.read_text(encoding="utf-8")).get("version")
    except (OSError, json.JSONDecodeError):
        return None


def _write(path: Path, name: str, derived: Derived) -> None:
    folder = path / DERIVED_DIR
    folder.mkdir(exist_ok=True)
    for old in folder.glob(f"{name}__*.parquet"):  # tables may disappear between versions
        old.unlink()
    for table, frame in derived.tables.items():
        frame.to_parquet(folder / f"{name}__{table}.parquet")
    meta = {
        "task": name,
        "version": derived.version,
        "computed_at": derived.computed_at,
        "powersim_version": _powersim_version(),
        "kpis": _clean(derived.kpis),
    }
    (folder / f"{name}.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _clean(value):
    """JSON-safe copy: numpy scalars to Python, NaN/inf to None."""
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(item) for item in value]
    if hasattr(value, "item") and not isinstance(value, str):  # numpy scalar
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _powersim_version() -> str | None:
    try:
        return importlib_metadata.version("powersim")
    except importlib_metadata.PackageNotFoundError:
        return None


# ---------------------------------------------------------------------- built-in tasks
def _indicators(run) -> Derived:
    from .indicators import all_indicators

    results = all_indicators(run.inputs, run.kpis, run.timeseries_wide(), run.market_data)
    kpis, tables = {}, {}
    for name, indicator in results.items():
        kpis[name] = {"available": indicator.available, "reason": indicator.reason}
        kpis[name].update(indicator.kpis)
        for table, frame in indicator.tables.items():
            tables[f"{name}_{table}"] = frame
    return Derived(kpis=kpis, tables=tables)


# Bump when any formula in powersim/runs/indicators.py changes.
INDICATORS_TASK = register(PostSolveTask("indicators", version=4, compute=_indicators))


# ---------------------------------------------------------------------- CLI
def main() -> None:
    parser = argparse.ArgumentParser(description="Compute derived data of saved powersim runs.")
    parser.add_argument("--runs", default="runs", help="folder with the saved runs (default: runs)")
    parser.add_argument("--task", action="append", help="task to run (default: all); repeatable")
    parser.add_argument("--force", action="store_true", help="recompute even if up to date")
    args = parser.parse_args()

    for run_id, task, status in update_runs(args.runs, args.task, args.force):
        print(f"{run_id}  {task}: {status}")


if __name__ == "__main__":
    main()
