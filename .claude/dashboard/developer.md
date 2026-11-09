# Tab: Developer

Code: `powersim/dashboard/tabs/developer.py`.

## Purpose

For the user only (2026-11-09): checks of the simulation itself, used while debugging
simulations and testing. They validate the optimizer result against the model, which is
internal: in the analysis tabs it only raises doubts, so it lives here. Last tab, below
Sandbox.

## Layout description

Approximate, as context:

```
+-----------------------------------------------------+--------------------------+
| ┆ Internal checks of the simulation... (note)       | Simulations    [Refresh] |
| Simulation checks (1 warning · 3 ok · 2 info):      | ...                      |
|   one check list, 2 columns, warnings first         |                          |
+-----------------------------------------------------+--------------------------+
```

## Right side panel

- **Simulations**: same shared run selector as every tab (`side_panel` in `app.py`).

## Current content

- **Simulation checks** (moved from Visualization's Checks, 2026-11-09): daily cycle limit,
  simultaneous charge/discharge, energy balance, export consistency, curtailment
  (`od.run_checks`, thresholds at the top of `overview_data.py`); exports at price ≤ 0
  (`od.indicator_checks`).
- **Reserve checks** (from the time series, `developer.py`, 2026-11-09, prompted by the
  user's limit-case runs):
  - "Reserve band backed by the assets": band (up or down, all markets) ≤ battery power + PV
    output of the period. Replaces "aFRR band vs battery power", which disappeared without a
    battery, the very case where the band has nothing behind it. Known gap of the model
    (`.claude/TODO.md`).
  - "Reserve activation within the offered band": |P_up| ≤ |Band_up| and |P_down| ≤
    |Band_down| per market (down series are stored negative). Catches the known bug
    `act_down_requirement` using `Band_up` (xfail test in `tests/test_afrr.py`).

## Decisions

- Limit-case runs to keep around (user, 2026-11-09): "None" (no assets, only grid access and
  markets), "PV6" without battery (DA, and DA+ID+aFRR). Every tab must render them; charts
  with nothing to draw show a message (`message_figure`).

- No polish needed: it is a working tool, not part of the product shown to companies.
- Good place for future debugging views (solver status, constraint slack, raw series...).
