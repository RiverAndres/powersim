# Tab: Visualization

Code: `powersim/dashboard/tabs/visualization.py` (UI and figures), pure computations in
`powersim/dashboard/tabs/overview_data.py` (no Dash), generic builders in `components.py` /
`figures.py`.

## Purpose

Overview of one saved run for companies that want to judge whether the simulation makes sense
and is worth exporting into their own models (see "Audience and goals" in `app.md`). It is the
"stable" tab: it only gets views the user has approved in the Sandbox. Designed in 3 rounds +
3 polish rounds (approved by the user: "the elements convince me perfectly").

## Questions it answers

- What plant and period was simulated, with which markets?
- How much does it earn in total, per year, per market and per revenue stream? At what prices?
- Does the simulation make sense (Checks)?
- How does revenue evolve over time?
- Where does the energy go: PV → grid / battery, grid → battery, battery → grid, losses,
  curtailment? How is energy split among markets?
- How is the battery used (SOC pattern, cycles per day)?
- What happened in a given week (detail on demand)?

## Layout description

Approximate, as context:

```
+-----------------------------------------------------+--------------------------+
| Plant: [PV] [BESS MW] [MWh] [h] [RTE] [grid] [period]| Simulations    [Refresh] |
| Headline numbers                                    | runs folder path         |
|   Economics: total, per year, per market, prices    | [Run label             ] |
|   Energy: PV, export, import, charge, discharge,... | [date · markets        ] |
| Checks: cycle limit, simult., balance, export,      | ...                      |
|   curtailment, captured vs market (ok/warn/info)    |                          |
| Economics: [revenue by period 2/3] [by stream 1/3]  |                          |
| Energy flows: [Sankey 1/2] [energy by market 1/2]   |                          |
|   [flows by period: export by source ↑ / charge ↓]  |                          |
| Battery: [SOC period x hour] [daily cycles hist.]   |                          |
| Operation detail: [week ▾] assets / markets (7 days)|                          |
+-----------------------------------------------------+--------------------------+
```

## Right side panel

- **Simulations**: one run selected at a time. Title, Refresh button (rescans the runs folder),
  folder path, one card per run (label; creation date and markets), most recent first; the
  most recent is selected on start. Same component for every tab (`side_panel` in `app.py`).

## Current content

- **Plant**: inputs; observed maximum when a rating is missing (e.g. "PV max output").
- **Headline numbers**: Economics (total, per year with k€/MW·year and "extrapolated" note on
  short runs, per market with share, captured sell/buy price vs market average) and Energy
  (PV, exported, imported, charged, discharged, battery losses, cycles, curtailment).
- **Checks**: daily cycle limit, simultaneous charge/discharge, energy balance, export
  consistency, curtailment, captured vs market price. Thresholds at the top of
  `overview_data.py`.
- **Economics**: revenue by period and market; revenue by stream (streams < 0.5 % hidden and
  listed in a footnote).
- **Energy flows**: balanced Sankey (system and battery losses as residuals, totals in labels);
  energy by market; flows by period (export by source up, battery charge by source down).
- **Battery**: SOC by period × hour; histogram of daily cycles, days above the limit in amber.
- **Operation detail**: week selector; assets and markets at full resolution with readable
  names, aFRR bands as dashed lines.

## Decisions

- Only aggregated data is sent except the 7-day detail: ~100 KB per run, < 1 s for 2 years
  quarter-hourly.
- Adaptive period: monthly > 90 days, weekly > 21 days, daily otherwise; titles follow.
  Partial first/last periods are translucent with "partial · N of M days" in the hover.
- Graceful states: no PV (no PV node/tiles/checks), no battery (note instead of charts),
  tile grids sized to avoid orphans (`grid_columns`).
- Series chosen by variable prefix, never by market name.

## Pending / ideas

- Sankey "Grid export" (Σ `E_system_sell_*`) differs slightly from the exported energy KPI
  (Σ `P_system_export`·dt): shown by the export consistency check; root cause in the run data.
