# Tab: Visualization

Code: `powersim/dashboard/tabs/visualization.py` (figures in `powersim/dashboard/figures.py`).

## Purpose

Main view of one saved run: how much it earns and how the system operated. It is the "stable"
tab: it only gets views the user has approved in the Sandbox.

## Questions it answers

- How much does the run earn in total, and how much comes from each market?
- How much energy was exported, imported, charged and discharged? How many equivalent cycles?
- How did the assets and the markets operate over time (detail view)?
- Was there excess power that could not be exported?

## Layout description

Approximate, as context:

```
+-----------------------------------------------------+--------------------------+
| [TOTAL REVENUE] [REV. DAYAHEAD] [REV. AFRR] [ENERGY | Simulations    [Refresh] |
|  37,659 €        29,163 €        8,497 €    EXP...] | runs folder path         |
|  (KPI cards in a grid, wrap to as many rows needed) | [Run label             ] |
|-----------------------------------------------------| [date · markets        ] |
| Assets                     Generation, storage ...  | [Run label             ] |
|   3 stacked rows: generation / storage / POI        | ...                      |
|-----------------------------------------------------|                          |
| Markets                    Prices and operation ... |                          |
|   prices (lines) / operation (stacked areas)        |                          |
|-----------------------------------------------------|                          |
| Excess power               Power that cannot ...    |                          |
+-----------------------------------------------------+--------------------------+
```

## Right side panel

- **Simulations**: one run selected at a time. Title, Refresh button (rescans the runs folder),
  folder path, one card per run (label; creation date and markets), most recent first; the
  most recent is selected on start. Today it is the same component for every tab
  (`_runs_sidebar` in `app.py`).

## Current content

1. KPI cards: total revenue (highlighted), revenue per market (with % of total), energy
   exported / imported / charged / discharged, equivalent cycles, excess energy.
2. Chart cards (same as `SimulationResult.plot_operation()`):
   - Assets: generation, storage, power at the POI (3 rows, shared axes).
   - Markets: prices and stacked operation per market.
   - Excess power.

## Decisions

- Same three charts as `plot_operation()`, series chosen by variable prefix, not market name.
- Graph height is fixed on the `dcc.Graph` container (`chart_card(height=...)`) with `responsive` on: without an explicit container height the graphs collapse, and without `responsive` they keep a 700 px width when a hidden tab is shown.

## Pending / ideas

- Downsampling for long quarter-hourly runs (a 9-month run sends ~17 MB to the browser).
