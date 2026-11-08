# Tab: Sandbox

Code: `powersim/dashboard/tabs/sandbox.py`.

## Purpose

Playground to decide what the dashboard should show. Experiments live here until the user
approves them; then they move to the tab where they belong.

## Layout description

Approximate, as context. Today the whole tab is one experiment: a candidate overview page of a
run, built in 3 design rounds (orchestrator review in Chrome + `dashboard-builder` agent).

```
+-----------------------------------------------------+--------------------------+
| ┆ Sandbox: candidate overview page... (note)        | Simulations    [Refresh] |
| Plant: [PV] [BESS MW] [MWh] [h] [RTE] [grid] [period]| runs folder path         |
| Headline numbers                                    | [Run label             ] |
|   Economics 3x2: total, per year, per market, prices| [date · markets        ] |
|   Energy 4x2: PV, export, import, charge, ...       | ...                      |
| Checks 3x2: cycle limit, simult., balance, export,  |                          |
|   curtailment, captured vs market (ok/warn/info)    |                          |
| Economics: [monthly revenue 2/3] [rev. by stream 1/3]|                         |
| Energy flows: [Sankey 1/2] [energy by market 1/2]   |                          |
|   [monthly flows: export by source ↑ / charge ↓]    |                          |
| Battery: [SOC month x hour] [daily cycles histogram]|                          |
| Operation detail: [week ▾] assets / markets (7 days)|                          |
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

- **Candidate overview page** (whole tab), for the goals in `app.md` (audience, 2-year runs,
  at a glance, energy flows). Only aggregated data is sent, except the 7-day detail; the
  overview is ~100 KB and builds in < 1 s for a 2-year quarter-hourly run. Sections:
  - **Plant**: inputs; observed maximum when a rating is missing.
  - **Headline numbers**: Economics (incl. captured prices, k€/MW·year) and Energy.
  - **Checks**: cycle limit, simultaneous charge/discharge, energy balance, export consistency,
    curtailment, captured vs market price.
  - **Economics**: monthly revenue by market; revenue by stream (streams < 0.5 % hidden, listed).
  - **Energy flows**: balanced Sankey (system and battery losses as residuals); energy by market;
    two-sided monthly flows.
  - **Battery**: SOC month × hour; daily cycles histogram with the limit highlighted.
  - **Operation detail**: week selector, assets and markets with readable names, bands dashed.
- Known minor issues: Sankey labels on the right edge slightly clipped; detail legends overlap
  the plotly toolbar; generation row of the detail shares the y axis with storage (half empty).

## Discarded

- Daily revenue by market: replaced by monthly revenue (daily bars unreadable over 2 years).
- SOC heatmap day × hour: replaced by month × hour (731 columns were noise).
