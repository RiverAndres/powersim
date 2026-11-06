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

<!-- TODO: add the installation instructions (PyPI / source) -->

```bash
pip install powersim
```

## Quick start

```python
from powersim import System, Battery, DayAhead, PerfectOptimizer  # adjust the import paths to your package layout

# 1. Describe the system
system = System(capacity_buy=50.0, capacity_sell=50.0, efficiency=0.95)   # MW, MW, -
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

# 4. Build, solve and inspect the model
# <TODO: add the call that runs the optimization and the way to read the results>
```

`add_module` returns the system, so calls can be chained.

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

Subclass `Optimizer`, declare which classes it uses, and add its own parameters if it needs any:

```python
class RollingOptimizer(Optimizer):
    system_class = Rolling_System
    market_map = {
        DayAhead: Rolling_DayAhead,
    }

    def __init__(self, system, markets, *, window_hours: int, step_hours: int, **kwargs):
        super().__init__(system, markets, **kwargs)   # common parameters and conversion
        self.window_hours = window_hours
        self.step_hours = step_hours
```

If a market has no entry in `market_map`, the optimizer raises a `TypeError` that names the missing market.

### Adding a new market or asset

1. Create the domain class (a subclass of `Market`, or a new module type).
2. Create the child class of each optimizer that should support it, with the model components.
3. Register it in that optimizer's `market_map` (or in the child system's `module_map`).

<!-- TODO: add License and Contributing sections -->
