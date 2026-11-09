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
- Is the plant well sized for its grid access (Checks)? Battery MW vs access and vs PV, PV peak
  vs access, battery hours.
- How does revenue evolve over time? How good is it (spread captured, value per cycle, PV
  capture with/without storage, dependence on a few days)?
- Is the configuration right? Which component limits the plant (grid connection, battery MW,
  battery MWh)?
- Where does the energy go: PV → grid / battery, grid → battery, battery → grid, losses,
  curtailment? How is energy split among markets?
- How is the battery used (SOC pattern, cycles per day)?
- What happened in a given week (detail on demand)?

## Layout description

Approximate, as context:

```
+-----------------------------------------------------+--------------------------+
| Plant: [Grid | PV | Battery | Markets | Period]    | Simulations    [Refresh] |
| Headline numbers                                    | runs folder path         |
|   [hero: total | per year | cycles]  [Energy list ] | [Run label             ] |
|   [Markets table: revenue, share,    [ PV, export, ] | [date · markets        ] |
|    sell / buy price vs market]       [ ... 1/3     ] | ...                      |
| Checks (to review · coherent · notes): grid access  |                          |
|   + sizing questions, 2 columns; [value per storage |                          |
|   hour] [limits by month]                           |                          |
| Economics: [revenue by period 2/3] [by stream 1/3]  |                          |
|   [Revenue quality list 1/3] [spread by period 2/3] |                          |
| Plant sizing: [Grid list 1/3] [Battery list 2/3,    |                          |
|   2 columns]; [POI duration] [battery duration]     |                          |
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

- **Plant**: one `spec_card` with groups ordered physical → markets → time (user request,
  2026-11-09): Grid connection (export / import capacity, efficiency), one PV group per
  generator (peak power, location, orientation, tracker, performance factor = input `losses`),
  one Battery group per battery (power with min, capacity, duration, RTE, usable / initial SOC,
  cycle limits), Markets (one row per market, params such as the aFRR max band), Period
  (dates, days). Resolution removed (the status row shows it). Observed maximum when a rating
  is missing ("Max output (observed)").
- **Headline numbers**: hero strip (total revenue, per year with k€/MW·year and "extrapolated"
  note on short runs, equivalent cycles per day); Markets table (one row per market: revenue,
  share, avg sell / buy price with "± vs mkt" delta, green when favourable, amber otherwise);
  Energy list (PV, exported, imported, charged, discharged, battery losses, curtailment).
- **Checks** (sizing checks, moved from the Sandbox, 2026-11-09): questions that confirm the
  plant is well sized for its **grid access** (a given condition, not a lever). Code:
  `tabs/sizing_checks.py` (verdicts, thresholds at the top), computation in the `sizing`
  indicator. Rows: Grid access (first, no status), battery MW vs access, battery MW vs PV, PV
  peak vs access, battery hours; then informative rows (battery use, reserve band at its market
  cap, PV capture). Status warn = to review, ok = coherent, info = note. Charts: value of each
  storage hour (marginal arbitrage curve) and share of time at each limit per month. Decisions
  and rule details: see "Sizing checks" under "Moved" in `sandbox.md`.
  The former checks of the simulation itself (cycle limit, simultaneous charge/discharge,
  energy balance, export consistency, aFRR band vs power, exports at price ≤ 0) moved to the
  **Developer** tab (user request: validating the optimizer is internal and raises doubts in
  the UI).
- **Economics**: revenue by period and market; revenue by stream (streams < 0.5 % hidden and
  listed in a footnote). **Revenue quality** (moved from the Sandbox, 2026-11-09): battery
  realized spread (with break-even), value per cycle, PV capture rate (sub: export capture rate
  with storage and uplift), top 10 % days share; chart of mean daily TBn spread vs realized
  spread per period (periods with < 25 % of their days dropped: it is a chart of averages).
- **Plant sizing** (moved from the Sandbox, 2026-11-09): "which component limits the plant?".
  Grid connection (time at export / import limit, POI capacity factor) and Battery (time at
  power limit, mean daily DoD, time at min / max SOC, idle time, avg aFRR bands as % of battery
  power). Duration curves of net POI power and battery power (% of their limits, dotted ±100 %);
  the battery curve is hidden when it matches the POI curve (battery-only runs).
- **Energy flows**: balanced Sankey (system and battery losses as residuals, totals in labels;
  node y computed from the flows with `sankey_figure(columns=...)` so every column fits: fixed
  positions cut the tall Grid import node of standalone batteries, 2026-11-09);
  energy by market; flows by period (export by source up, battery charge by source down).
- **Battery**: SOC by period × hour; histogram of daily cycles, days above the limit in amber.
- **Operation detail**: week selector; assets and markets at full resolution with readable
  names, aFRR bands as dashed lines.

## Decisions

- Data that is not a chart is condensed (user request, 2026-11-09, 3 rounds): one card per
  topic with compact rows (`hero_strip`, `data_table`, `stat_list`, `check_list` in
  `components.py`) instead of one tile per number (~40 boxes → 7 cards). Side-by-side cards use
  `columns(..., align_start=True)` so a short card never stretches half empty. Secondary
  formulas live in row tooltips. `kpi_tile` / `check_tile` remain as generic components (unused today).

- Only aggregated data is sent except the 7-day detail: ~100 KB per run, < 1 s for 2 years
  quarter-hourly.
- Adaptive period: monthly > 90 days, weekly > 21 days, daily otherwise; titles follow.
  Partial first/last periods are translucent with "partial · N of M days" in the hover.
- Graceful states: no PV (no PV node/tiles/checks), no battery (note instead of charts), no
  assets (Sankey, flows by period and assets detail show a message: `message_figure`),
  tile grids sized to avoid orphans (`grid_columns`).
- Series chosen by variable prefix, never by market name.
- Indicators computed on the fly with `all_indicators` (same functions as the `indicators`
  post-solve task); reading them from `<run>/derived/` is pending.
- Not shown on purpose: TBn capture % (≈ 100 % by construction with perfect foresight; worth
  revisiting with realistic optimizers), cumulative revenue by best days (repeats the top 10 %
  tile), aFRR band histogram (repeats tiles + check), export capture as its own tile (same as
  the headline captured price).

## Pending / ideas

- Sankey "Grid export" (Σ `E_system_sell_*`) differs slightly from the exported energy KPI
  (Σ `P_system_export`·dt): shown by the export consistency check; root cause in the run data.
