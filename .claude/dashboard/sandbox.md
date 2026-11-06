# Tab: Sandbox

Code: `powersim/dashboard/tabs/sandbox.py`.

## Purpose

Playground to decide what the dashboard should show. Experiments live here until the user
approves them; then they move to the tab where they belong.

## Layout description

Approximate, as context:

```
+-----------------------------------------------------+--------------------------+
| ┆ Sandbox: experimental views... (dashed note)      | Simulations    [Refresh] |
|-----------------------------------------------------| runs folder path         |
| Daily revenue by market        Experiment · € ...   | [Run label             ] |
|   stacked bars per day, one color per market        | [date · markets        ] |
|-----------------------------------------------------| [Run label             ] |
| Battery state of charge        Experiment · SOC ... | ...                      |
|   heatmap: day (x) × hour (y), 0-1                  |                          |
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

- **Daily revenue by market**: stacked bars, sum of `B_benefit_*` per day. Shows which market
  brings the money and how stable it is day to day.
- **Battery state of charge**: heatmap of mean SOC of all batteries, day (x) × hour of day (y).
  Shows the daily charge/discharge pattern and how it changes over the period.

## Discarded

(none yet)
