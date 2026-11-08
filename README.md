# powersim

**powersim** is a Python library to study energy assets in different electricity markets, applying different strategies and algorithms.

It lets you describe a system (for now, batteries and/or photovoltaic plants), choose the markets where it operates, and run an optimizer to evaluate how much value the system can capture.

> **Status:** early development. The API may change.

## Table of contents

- [Current scope](#current-scope)
- [Roadmap](#roadmap)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Saving and viewing runs](#saving-and-viewing-runs)
- [Core concepts](#core-concepts)
- [Architecture and extending the library](#architecture-and-extending-the-library)

## Current scope

**Assets**

- Batteries
- Photovoltaic plants

Assets are grouped in a `System` that also defines the grid access capacity (buy and sell) and the system efficiency (in addition to the modules' efficiencies).

**Markets** (Spanish electricity market)

| Market | Description |
|---|---|
| Day-ahead | Day-ahead wholesale auction market |
| Intraday 1, 2 and 3 | Intraday auctions |
| aFRR | Secondary regulation |
| mFRR | Tertiary regulation |

Market data is retrieved from ESIOS (Red Eléctrica de España) with a personal ESIOS token.

**Algorithms**

- **LP / MILP solver** (`PerfectOptimizer`). For now it acts as a **benchmark**: it assumes the market prices for the whole simulation are known from the start (perfect foresight), so it gives an upper reference rather than a realistic operation.

## Roadmap

powersim aims to simulate a possible *real* operation of a *real* asset. Planned work:

- More generation assets.
- Better parametrization of the assets, including the usage restrictions typically imposed by manufacturers.
- Other European electricity markets.
- Market price forecasting algorithms.
- Operation algorithms that do not rely on perfect foresight

## Requirements

- Python 3.12 or newer
- [Pyomo](https://www.pyomo.org/) and [pandas](https://pandas.pydata.org/)
- A solver supported by Pyomo (HiGHS is the default)
- An ESIOS token to download market data

## Installation

powersim is not published on PyPI. Install it from GitHub:

```bash
pip install git+https://github.com/RiverAndres/powersim.git
```

Or, for development, from a local clone:

```bash
git clone https://github.com/RiverAndres/powersim.git
cd powersim
pip install -e ".[dev]"
pytest
```

## Quick start

```python
from powersim import System, Battery, DayAhead, PerfectOptimizer

# 1. Describe the system
system = System(capacity_buy=50.0, capacity_sell=50.0, efficiency=0.95)  # MW, MW, -
system.add_module(Battery(capacity=100, rte=0.85, c_rate=0.5, name="bat001"))
# Photovoltaic plants are added the same way with system.add_module(...)

# 2. Get the market data
day_ahead = DayAhead().get_info(
    esios_token="YOUR_ESIOS_TOKEN",
    start_date="2025/01/01T00:00:00Z",
    end_date="2025/01/31T23:00:00Z",
)

# 3. Create the optimizer (your system and markets are copied, not modified)
optimizer = PerfectOptimizer(system, [day_ahead], solver_name="highs")

# 4. Build and solve the model, then inspect the results
optimizer.solve()
results = optimizer.results  # SimulationResult

print(results.operation_timeseries)  # time series of the whole operation
results.plot_operation()
results.export("results.xlsx")
```

`add_module` returns the system, so calls can be chained.

## Saving and viewing runs

A simulation can be saved as a **run**: a self-contained folder with everything needed to inspect
or reproduce it.

```python
run = optimizer.results.to_run(label="BESS 50 MW / 2 h", tags=["day-ahead"])
run.save()             # -> runs/<date>_<label>_<id>/ (never overwrites a previous run)
```

```
runs/2026-11-06T15-30-00_bess-50-mw-2-h_a1b2c3/
  manifest.json        id, date, label, tags, powersim version and git commit
  inputs.json          system, modules, markets, period and optimizer parameters
  solver.json          status, objective, solve time, model size
  kpis.json            revenues (total and per market), energies, equivalent cycles...
  timeseries.parquet   operation, long format (time, variable, value)
  market_data.parquet  market input data used (time, market, dataset, value)
```

Saved runs can be loaded and listed:

```python
from powersim import SimulationRun, list_runs

catalog = list_runs("runs")                      # one row per run, with its KPIs
run = SimulationRun.load(catalog.loc[0, "path"])
run.timeseries_wide()                            # one column per variable
```

### Dashboard

A local [Dash](https://dash.plotly.com/) app to explore saved runs. Pick a tool on the left
and a run on the right:

- **Visualization**: overview of a run, designed for long simulations: plant, headline numbers,
  sanity checks, revenue over time and by stream, energy flows (Sankey, by market, over time),
  battery usage and a 7-day operation detail on demand.
- **Sandbox**: experimental views, still being designed.

It only reads saved runs.

```bash
pip install -e ".[dashboard]"
powersim-dashboard --runs runs      # then open http://127.0.0.1:8050
```

## Core concepts

### System

`System(capacity_buy, capacity_sell, efficiency)`

| Parameter | Description |
|---|---|
| `capacity_buy` | Access capacity to buy from the grid (MW) |
| `capacity_sell` | Access capacity to sell to the grid (MW) |
| `efficiency` | System efficiency |

Modules are added with `system.add_module(module)`. Batteries are stored in `system.batteries` and photovoltaic plants in `system.generators`.

### Battery

| Parameter | Description |
|---|---|
| `capacity` | Total energy that can be stored (MWh) |
| `rte` | Round-trip efficiency (charge and discharge) |
| `c_rate` | Inverse of hours of storage: max power output (of the battery, not of the interconnection) over capacity |
| `dod` | Depth of discharge, as a fraction (default `1`) |
| `soc_max` | Maximum state of charge, as a fraction (default `1`) |
| `soc_initial` | Initial state of charge (default `0`) |
| `max_cycles_day` | Maximum number of cycles per day |
| `max_cycles_day_monthly_avg` | Maximum cycles per day, monthly average |
| `max_cycles_day_yearly_avg` | Maximum cycles per day, yearly average |
| `rsoc` | Allowed range for the average SOC during rest periods, computed monthly or yearly |
| `resting_period` | Minimum rest period (hours) between charging and discharging periods |
| `min_power_output` | Minimum power output (default `0.1`) |
| `name` | Battery name (generated from its parameters if omitted) |

The maximum power output is derived as `capacity * c_rate`.

### Markets

A market (`Market`) holds the datasets needed to model it. `DayAhead.get_info(esios_token, start_date, end_date)` downloads them from ESIOS and returns the market itself. `use_cache=True` enables caching of the ESIOS requests.

### Optimizers

An optimizer receives a system and a **list of markets** and builds the optimization model on top of them.

```python
PerfectOptimizer(system, markets, solver_name="highs", precision=1)
```

## Architecture and extending the library

The library separates **what is being studied** from **how it is optimized**:

- **Domain classes**: `System`, `Battery`, `Photovoltaic`, `Market` (and `DayAhead`...). They describe assets and markets and know nothing about optimization.
- **Optimization classes**: `Milp_System`, `Milp_Battery`, `Milp_DayAhead`... They *inherit* from the domain classes and add what the algorithm needs (Pyomo components, constraints, results).

Each optimizer converts the objects it receives into its own optimization classes. The conversion copies the full state (data and parameters) into an instance of the child class, so the original objects are never modified. It is implemented once in the parent classes:

| Object | Conversion method | Child class declared in |
|---|---|---|
| System | `from_system` | the optimizer (`system_class`) |
| Module (battery, PV) | `from_module` | the child system (`module_map`) |
| Market | `from_market` | the optimizer (`market_map`) |

### Adding a new optimizer

Subclass `Optimizer` (`powersim.optimizers.optimizer`), declare which classes it uses, and add its own parameters if it needs any. This is how `PerfectOptimizer` does it (`powersim/optimizers/milp_optimizer/milp_model.py`):

```python
class PerfectOptimizer(Optimizer):
    system_class = Milp_System
    market_map = {
        DayAhead: Milp_DayAhead,
        IntraDay01: Milp_IntraDay01,
        # ...
        AFRR: Milp_AFRR,
    }

    def __init__(self, system, markets, *, solver_name="highs", precision=1):
        super().__init__(system, markets)  # converts (copies) the system and the markets
        self.solver_name = solver_name
        self.precision = precision
```

A new optimizer follows the same pattern with its own child classes (its system class with a `module_map`, and one child class per supported market) and its own `solve()`.

If a market has no entry in `market_map`, the optimizer raises a `TypeError` that names the missing market.

### Adding a new market or asset

1. Create the domain class (a subclass of `Market`, or a new module type).
2. Create the child class of each optimizer that should support it, with the model components.
3. Register it in that optimizer's `market_map` (or in the child system's `module_map`).

<!-- TODO: add License and Contributing sections -->
