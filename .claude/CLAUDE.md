# powersim

Python library to simulate energy assets (batteries, photovoltaics) operating in electricity
markets (for now, the Spanish one) and evaluate how much value they capture. The user writes in
Spanish: reply in Spanish. Code, identifiers and docstrings are in English.

## Environment and commands

- Windows + PowerShell. Always use the venv: `.venv\Scripts\python.exe`
- Python >= 3.12 (required by `esios_request`).
- Install: `.venv\Scripts\python.exe -m pip install -e ".[dev]"`
- Tests: `.venv\Scripts\python.exe -m pytest`
- Lint/format: `.venv\Scripts\python.exe -m ruff check .` / `... -m ruff format .`
- Default solver: HiGHS (`highspy`), no external installation needed.
- Dependencies: declared as ranges in `pyproject.toml`. `requirements.txt` is the exact
  `pip freeze` of the environment (UTF-8, not UTF-16); when a dependency is added or changed,
  update both.
- `esios_request` is the user's own library (github.com/RiverAndres/esios_request, local copy in
  `../esios_request`). If a problem comes from there, say so instead of patching it inside powersim.

## Architecture

Strict separation between **what is studied** (domain) and **how it is optimized** (optimizer):

- Domain (knows nothing about optimization):
  - `powersim/assets/modules.py`: `Module`, `Battery`, `Photovoltaic`, `System`.
  - `powersim/markets/markets.py`: `Market` (ABC) and `DayAhead`, `IntraDay01..03`, `AFRR`, `MFRR`.
    `get_info(esios_token, start_date, end_date, use_cache)` downloads from ESIOS and fills
    `self.datasets: dict[str, pd.DataFrame]` (DataFrames indexed by timestamp with a `value` column).
- Optimization:
  - `powersim/optimizers/optimizer.py`: base `Optimizer`. Declares `system_class` and `market_map`
    and in `__init__` converts (deep copy) the system and markets to their child classes.
    **The user's objects are never modified.**
  - `powersim/optimizers/milp_optimizer/`: `PerfectOptimizer` (`milp_model.py`), market `Milp_*`
    classes (`milp_markets.py`) and module classes (`milp_modules.py`, with `Milp_System.module_map`).
- Results: `powersim/visualization/results.py` (`SimulationResult`: plots and Excel export).
- `powersim/cook_book/`: high-level recipes (sizing, reports).
- `powersim/utils/cache.py`: disk cache (`%TEMP%/powersim_cache`).

### Contract of the `Milp_*` classes

Each `Milp_<Market>` inherits from its domain class and implements:
- `components(model)`: adds its Params/Vars/Constraints to `model` with the suffix `_{self.name}`
  (the Milp class name, e.g. `P_sell_Milp_DayAhead`), and **must** define the expressions
  `Market_output_{name}[t]`, `Power_pre_allocated_{name}[t]` and `Revenues_{name}`, which
  `PerfectOptimizer` uses for the balance with the system and for the objective.
- `results(model) -> pd.DataFrame` indexed by time, with columns suffixed with `parent_name`.

After conversion, markets are instances of the `Milp_*` class: to check the market type use
`isinstance(market, AFRR)`, never `market.__class__.__name__ == "AFRR"`. `parent_name` keeps the
domain name (`"AFRR"`).

`PerfectOptimizer.solve()` flow: `_model_setup()` → `_objective_maximize_revenues()` → `_solve()`.

### Adding a market / asset / optimizer

1. Domain class (subclass of `Market` or `Module`).
2. Child class for each optimizer that should support it (`Milp_X` following the contract above).
3. Register it in the optimizer's `market_map` (or in the child system's `module_map`).
4. Export it in `powersim/__init__.py` (import and `__all__`).
5. Add tests.

## Domain and units

- Power in MW, energy in MWh, energy prices in €/MWh; efficiencies, SOC, DoD as 0-1 fractions.
- In the model, `SOC[b, t]` is a fraction of the battery `capacity`, not MWh.
- `model.dt[t]` is the period length in hours (data may be hourly or quarter-hourly); energy is
  always power × `dt`, never assume 1 h.
- **Exception: aFRR band prices are €/MW** and pay for availability offered in the interval, so
  band revenues are `Band × price` **without** `dt`. Activation energy is still priced in €/MWh
  (× `dt`).
- aFRR activations are predefined inputs (computed before optimizing): do **not** reserve
  energy (SOC) for them; the perfect-foresight model already guarantees they are met.
- Simultaneous charge and discharge of a battery is **intentionally allowed** in the base model
  (avoids extra binaries). Do not add exclusivity constraints unless the user asks.
- `PerfectOptimizer` assumes *perfect foresight*: it is a **benchmark** (upper bound), not a
  realistic operation. The project goal (see the README Roadmap) is to reach algorithms without
  perfect foresight, price forecasting, more assets and European markets.
- When touching MILP constraints, check: units, signs (buy vs sell), linking between consecutive
  periods (SOC at t-1, first period), and that everything stays linear.

## Known state

- `MFRR` is incomplete: `get_info` downloads indicator `""` and `Milp_MFRR` does not define
  `Market_output_*`. Do not use it until it is finished.
- Known bugs are covered by tests marked `xfail(strict=True)`; when fixing one, remove its marker.
- `.claude/TODO.md` holds analysed-but-postponed work (e.g. `PerfectOptimizer` is under-constrained:
  aFRR band not limited by battery power). Read it before working on the optimizers.

## Tests

- Tests must not call ESIOS or require a token. For now market data is synthetic, built in
  `tests/conftest.py`; real data snapshots may be added later as fixtures under `tests/data/`.

## Rules

- **Never** read or display `env/` or `.env`: they contain the user's secrets (ESIOS token).
  Enforced by `.claude/settings.json` (Read deny) and the PreToolUse hook
  `.claude/hooks/guard_secrets.py`, which also blocks any shell command that mentions those
  paths, even inside a string: keep them out of commands (e.g. put test data in a file).
- A PostToolUse hook (`.claude/hooks/ruff_format.py`) runs `ruff format` on every edited `.py`
  file, so edited regions may be reformatted: re-read before a follow-up edit there.
- `main.py` is a personal test script (ignored by git); do not treat it as part of the library.
- Keep `README.md` consistent when the public API changes.
