"""SimulationRun: standardized, optimizer-independent export of one simulation."""

import json
import re
import secrets
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path

import pandas as pd

from .serialize import market_inputs, system_inputs

SCHEMA_VERSION = 1
DEFAULT_RUNS_DIR = "runs"

MANIFEST_FILE = "manifest.json"
INPUTS_FILE = "inputs.json"
SOLVER_FILE = "solver.json"
KPIS_FILE = "kpis.json"
TIMESERIES_FILE = "timeseries.parquet"
MARKET_DATA_FILE = "market_data.parquet"

# Units by variable prefix (longest prefix first).
_UNITS = (
    ("Band_", "MW"),
    ("SOC", "-"),
    ("RSOC", "-"),
    ("P_", "MW"),
    ("E_", "MWh"),
    ("p_", "EUR/MWh"),
    ("B_", "EUR"),
)


def unit_for(variable: str) -> str | None:
    """Unit of a time series variable, derived from its prefix (None if unknown)."""
    for prefix, unit in _UNITS:
        if variable.startswith(prefix):
            return unit
    return None


@dataclass(eq=False)  # DataFrame fields: compare runs field by field, not with ==
class SimulationRun:
    """One simulation, with everything needed to inspect or reproduce it.

    - ``manifest``: identity (id, date, label, tags) and code version.
    - ``inputs``: system, modules, markets, period and optimizer parameters.
    - ``solver``: status, objective, solve time and model size.
    - ``kpis``: scalar results (revenues, energies, cycles...).
    - ``timeseries``: operation in long format (``time, variable, value``).
    - ``market_data``: market input data used, long format (``time, market, dataset, value``).
    """

    manifest: dict
    inputs: dict
    solver: dict
    kpis: dict
    timeseries: pd.DataFrame
    market_data: pd.DataFrame
    path: Path | None = field(default=None, compare=False)

    # ------------------------------------------------------------------ creation
    @classmethod
    def from_result(cls, result, label: str | None = None, tags: list[str] | None = None):
        """Build a run from a :class:`SimulationResult` (see ``SimulationResult.to_run``)."""
        wide = result.operation_timeseries.copy()
        wide.index.name = "time"
        dt = result.operation_system["dt"]

        created_at = datetime.now(UTC)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "id": _run_id(created_at, label),
            "created_at": created_at.isoformat(timespec="seconds"),
            "label": label,
            "tags": list(tags or []),
            "optimizer": result.optimizer_name,
            "powersim_version": _powersim_version(),
            **_git_info(),
        }

        index = wide.index
        inputs = {
            **system_inputs(result.system),
            "markets": [market_inputs(market) for market in result.markets],
            "period": {
                "start": index.min().isoformat(),
                "end": index.max().isoformat(),
                "n_periods": len(index),
                "dt_hours": sorted({float(v) for v in dt.unique()}),
            },
            "optimizer_params": result.metadata.get("optimizer_params", {}),
        }

        return cls(
            manifest=manifest,
            inputs=inputs,
            solver=result.metadata.get("solver", {}),
            kpis=_compute_kpis(wide, dt, result),
            timeseries=_to_long(wide),
            market_data=_market_data(result),
        )

    # ------------------------------------------------------------------ disk
    def save(self, root: str | Path = DEFAULT_RUNS_DIR, post_solve: bool = True) -> Path:
        """Save the run in ``root/<id>/`` and return that folder. Never overwrites a run.

        With ``post_solve`` (default) the registered post-solve tasks (derived indicators...)
        are computed and stored in ``derived/``; see :mod:`powersim.runs.post_solve`.
        """
        path = Path(root) / self.manifest["id"]
        path.mkdir(parents=True, exist_ok=False)

        for filename, content in (
            (MANIFEST_FILE, self.manifest),
            (INPUTS_FILE, self.inputs),
            (SOLVER_FILE, self.solver),
            (KPIS_FILE, self.kpis),
        ):
            (path / filename).write_text(
                json.dumps(content, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
            )
        self.timeseries.to_parquet(path / TIMESERIES_FILE, index=False)
        self.market_data.to_parquet(path / MARKET_DATA_FILE, index=False)

        self.path = path
        if post_solve:
            self.post_solve()
        return path

    def post_solve(self, names: list[str] | None = None, force: bool = False) -> dict[str, str]:
        """Compute (and store, if saved) the post-solve tasks. Returns ``{task: status}``."""
        from .post_solve import run_post_solve

        return run_post_solve(self, names, force)

    def derived(self, name: str = "indicators"):
        """Stored output (:class:`~powersim.runs.post_solve.Derived`) of a post-solve task.

        None if the run is not saved or the task was never run (see :meth:`post_solve`).
        """
        from .post_solve import load_derived

        return load_derived(self.path, name) if self.path is not None else None

    @classmethod
    def load(cls, path: str | Path) -> "SimulationRun":
        """Load a run saved with :meth:`save`."""
        path = Path(path)

        def read_json(filename):
            return json.loads((path / filename).read_text(encoding="utf-8"))

        return cls(
            manifest=read_json(MANIFEST_FILE),
            inputs=read_json(INPUTS_FILE),
            solver=read_json(SOLVER_FILE),
            kpis=read_json(KPIS_FILE),
            timeseries=pd.read_parquet(path / TIMESERIES_FILE),
            market_data=pd.read_parquet(path / MARKET_DATA_FILE),
            path=path,
        )

    # ------------------------------------------------------------------ views
    def timeseries_wide(self) -> pd.DataFrame:
        """Operation time series with one column per variable (original column order)."""
        columns = pd.unique(self.timeseries["variable"])
        wide = self.timeseries.pivot(index="time", columns="variable", values="value")
        wide = wide.reindex(columns=columns)
        wide.columns.name = None
        return wide

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @property
    def label(self) -> str | None:
        return self.manifest.get("label")


# ---------------------------------------------------------------------- helpers
def _to_long(wide: pd.DataFrame) -> pd.DataFrame:
    long = wide.astype(float).reset_index().melt(id_vars="time", var_name="variable")
    return long[["time", "variable", "value"]]


def _market_data(result) -> pd.DataFrame:
    """Input datasets of every market, plus realized activation inputs (e_act_*), long format."""
    frames = []
    for market in result.markets:
        for dataset, df in market.datasets.items():
            frames.append(_series_frame(df["value"], market.parent_name, dataset))

        # Realized activation requirements (e.g. aFRR, possibly random): needed to reproduce.
        market_results = market.results(result.simulation)
        for column in market_results.columns:
            if column.startswith("e_act_"):
                dataset = column.removesuffix(f"_{market.parent_name}") + "_realized"
                frames.append(_series_frame(market_results[column], market.parent_name, dataset))

    if not frames:
        return pd.DataFrame(columns=["time", "market", "dataset", "value"])
    return pd.concat(frames, ignore_index=True)


def _series_frame(series: pd.Series, market: str, dataset: str) -> pd.DataFrame:
    frame = pd.DataFrame(
        {"time": series.index, "market": market, "dataset": dataset, "value": series.to_numpy()}
    )
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce").astype(float)
    return frame


def _compute_kpis(wide: pd.DataFrame, dt: pd.Series, result) -> dict:
    def energy(column: str) -> float:
        return float((wide[column] * dt).sum()) if column in wide else 0.0

    revenue_by_market = {
        column.removeprefix("B_benefit_"): float(wide[column].sum())
        for column in wide.columns
        if column.startswith("B_benefit_")
    }
    objective = result.metadata.get("solver", {}).get("objective")
    battery_capacity = sum(battery.capacity for battery in result.system.batteries)
    discharged = energy("P_storage_discharge")

    # Signs in operation_timeseries: import and charge are negative.
    return {
        "revenue_total": float(objective)
        if objective is not None
        else sum(revenue_by_market.values()),
        "revenue_by_market": revenue_by_market,
        "energy_exported_MWh": energy("P_system_export"),
        "energy_imported_MWh": -energy("P_system_import"),
        "energy_charged_MWh": -energy("P_storage_charge"),
        "energy_discharged_MWh": discharged,
        "equivalent_cycles": discharged / battery_capacity if battery_capacity else None,
        "excess_energy_MWh": energy("P_excess"),
    }


def _run_id(created_at: datetime, label: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (label or "run").lower()).strip("-")[:40] or "run"
    return f"{created_at:%Y-%m-%dT%H-%M-%S}_{slug}_{secrets.token_hex(3)}"


def _powersim_version() -> str | None:
    try:
        return importlib_metadata.version("powersim")
    except importlib_metadata.PackageNotFoundError:
        return None


def _git_info() -> dict:
    """Commit of the powersim checkout (if it is a git repository) and whether it had changes."""
    repo = Path(__file__).resolve().parents[2]

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()

    try:
        return {
            "git_commit": git("rev-parse", "HEAD"),
            "git_dirty": bool(git("status", "--porcelain")),
        }
    except (OSError, subprocess.SubprocessError):
        return {"git_commit": None, "git_dirty": None}
