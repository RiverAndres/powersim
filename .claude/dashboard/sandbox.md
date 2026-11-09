# Tab: Sandbox

Code: `powersim/dashboard/tabs/sandbox.py`.

## Purpose

Playground to decide what the dashboard should show. Experiments live here until the user
approves them; then they move to the tab where they belong.

## Layout description

Approximate, as context:

```
+-----------------------------------------------------+--------------------------+
| ┆ No experiments right now... (note)                | Simulations    [Refresh] |
|   (experiment sections are added here)              | ...                      |
+-----------------------------------------------------+--------------------------+
```

## Right side panel

- **Simulations**: one run selected at a time; every experiment uses it. Title, Refresh
  button (rescans the runs folder), folder path, one card per run (label; creation date and
  markets), most recent first. Today it is the same component for every tab (`_runs_sidebar` in
  `app.py`). If an experiment needs another selection (several runs, a date range...), describe
  it here first.

## Workflow

1. The user describes a question or a view; it is added here as an experiment card, with its
   figure function inside `sandbox.py` and the hint "Experiment · ...".
2. The user reviews it (ideally with a screenshot) and asks for changes.
3. When approved ("move it to Visualization"): move the figure to `figures.py`, the card to the
   target tab, its tests to the target tab tests, record it in that tab's `.md`, and remove it
   from here (also from "Experiments" below).
4. Rejected experiments are removed; note them under "Discarded" with the reason, so they are
   not proposed again.

## Experiments

None (2026-11-09: everything was moved or discarded). The tab shows a note and registers no
callbacks; add a section and a callback in `sandbox.py` with the next experiment.

- **Derived indicators**: the computations stay in `powersim/runs/indicators.py` (pure,
  documented formulas/units; also stored by the `indicators` post-solve task in
  `<run>/derived/`) and Visualization uses them. Definitions worth remembering:
  - Battery energy valued at the price of the first energy market (`p_DayAhead` today); a
    footnote appears when the run trades more energy markets (no per-market attribution yet).
  - TBn: n = duration (h); one full cycle per day; also a cycle-limited version.
  - Grid export limit = capacity_sell × system efficiency (export is measured after it).
  - Time at battery power limit: |charge| or |discharge| ≥ 99 % of total battery power
    (`battery_usage.power_limit_share`, indicators task version 2).
- Not yet: the dashboard computes indicators on the fly (same functions as post-solve) instead
  of reading them from `derived/`.

## Moved

- **Sizing checks** → Visualization, Checks section (approved by the user 2026-11-09; code moved
  to `tabs/sizing_checks.py`). Origin (2026-11-09, user request: Checks should not validate the optimizer, that
  is internal and only raises doubts in the UI; they should be questions that confirm the
  plant is well sized, plus informative rows with figures already shown elsewhere).
  Computation: `sizing` indicator in `powersim/runs/indicators.py` (indicators task v3; v4 keeps a 0 MW import capacity instead of None);
  verdicts and thresholds in `tabs/sizing_checks.py`.
  **Round 2 (user, 2026-11-09)**: the plant is sized on its **grid access** (export / import
  capacity), a given condition, not a lever. Key questions: is the battery power coherent
  with the PV and with the access? is the PV peak coherent with the access? do the battery
  hours make sense? Rows: Grid access (first, no status, "given condition"), battery MW vs
  access, battery MW vs PV, PV peak vs access, battery hours; then informative rows (battery
  use, reserve band at its market cap, PV capture). Status warn = to review, ok = coherent,
  info = note (room for more PV, battery above access). Charts: value of each storage hour
  (marginal arbitrage curve) and share of time at each limit per month. Decisions:
  - Battery MW vs access: matched (≥ 95 %) → more MW could not reach the grid (no "+1 MW"
    shown); above → extra MW only charge from PV; below → worth filling only if +1 MW earns
    ≥ 50 % of an installed MW (arbitrage curve: value(P, E) ≈ P × Σ_{k≤E/P} m_k).
  - Battery MW vs PV: must cover the PV excess over the access (largest generation −
    capacity_sell); "PV lost" if ≥ 2 % of PV is sold at ≤ 0 or curtailed with the battery full.
  - PV vs access: too much PV when ≥ 2 % is lost; room for more PV when the PV never reaches
    the access, or exceeds it by < 1 % of its energy and the battery covers that excess (a
    higher DC/AC would be stored). Saved runs: DC/AC 1.20, peak 5.7 MW on 5 MW, 0.4 % above
    the access → room for more PV.
  - Battery hours: short when ≥ 50 % of days use the full SOC range and +1 h earns ≥ 50 % of
    an installed hour, or when the cycle limit binds; long when the last installed hour earns
    < 30 % of the average or the mean SOC range is < 50 % of the usable range.
  - Round 1 (replaced): "is the grid connection limiting?" (meaningless with a fixed access),
    "battery MW / MWh limiting?", cycle limit and aFRR band as questions. The operational
    signal alone (time at full power) flagged MW wrongly: arbitrage always runs at full power.
  - Validation: the curve predicts ≈ 304 k€ (305 days) for 2 h → 4 h at 5 MW; the real DA-only
    runs differ by 318 k€.
  - Cycles: the model's yearly budget is limit × days of the calendar year (whatever the run
    covers), cycles Σ|ΔSOC|/2; so a 305-day run at 1.68/day uses 98 % of a 1.5/day budget
    (not a violation).
  - aFRR: band at the `max_up`/`max_down` market cap (input) 97 % of the time, half of the
    battery power: the cap limits, not the plant.
  - Pending ideas: compare marginal values with user-supplied costs (€/MW, €/MWh) to answer
    "is it worth growing?"; include reserves in the marginal value.
- Candidate overview page → Visualization (approved by the user after 3 design + 3 polish
  rounds).
- Derived indicators → Visualization (2026-11-09, chosen by Claude at the user's request, 3
  review rounds): realized spread, value per cycle, PV capture, top 10 % days, spread by period
  (Economics · Revenue quality); grid / battery sizing tiles and POI / battery duration curves
  (new Plant sizing section); aFRR band and exports at price ≤ 0 (Checks). The user still has
  to review the result.

## Discarded

- Sandbox leftovers (user, 2026-11-09: "everything in the Sandbox can be discarded"; their
  useful parts were already in Visualization): summary tiles, daily TBn vs realized spread
  scatter, revenue concentration tiles + daily revenue histogram, net POI power histogram,
  temporal stability (monthly CV, year-on-year), prices ≤ 0 tiles, battery usage tiles + SOC
  histogram. The indicators behind them stay in `powersim/runs/indicators.py`.
- TBn capture % tile: ≈ 100 % by construction with perfect foresight (revisit with realistic
  optimizers).
- Cumulative revenue by best days: repeats the top 10 % days tile.
- aFRR band vs battery power histogram: bands sit at a constant level; tiles + check say it.

## Discarded (earlier)

- Daily revenue by market: replaced by monthly revenue (daily bars unreadable over 2 years).
- SOC heatmap day × hour: replaced by month × hour (731 columns were noise).
