# TODO

Pending work that was analysed but deliberately postponed. Known bugs with a reproducing test
are tracked as `xfail(strict=True)` tests in `tests/`, not here.

## Simulation: "presolve" stage (user idea, 2026-11-09)

**Idea.** Most errors seen in the saved runs are not about the engine or its constraints (those
follow internal or regulatory criteria). They come from inputs that do not make sense together.
A presolve step (function or class) that runs before the simulation would fix most of them.
It would have two moments:
1. **Before building the model**: on the domain objects (system, modules, markets, data).
2. **Before or after the solver's initial declarations**: on the built model (Params / bounds),
   before solving.

Like the optimizer, it works on the converted copies, so **the user's objects are never
modified**. Every adjustment or rejection is reported (log / list stored in the run), never
silent, so the dashboard (Developer tab) can show what presolve changed.

**Candidates** (from the limit-case runs and the known bugs):
- **Reserve market caps against the plant.** Limit `max_up` / `max_down` to what the assets can
  back: battery power + PV peak for up, battery power (+ PV output) for down. For a plant
  without assets, drop the reserve market or reject it. Evidence: the "None" run earns 451 k€
  of band with nothing behind it (see the aFRR section below). This complements the
  per-period constraint proposed there: presolve removes the obvious cases, the constraint
  handles the hourly PV availability.
- **Grid access vs markets.** `capacity_buy = 0` disables buying, grid charging and downward
  bands that need import. Warn when a market cannot be used at all.
- **Modules vs access.** Battery power above the access, or a PV peak far above it: warn (it is
  a sizing choice, not an error).
- **Market data coherence.** All datasets on the same index and resolution, no gaps; activation
  shares (`e_act_*`) within 0-1; reject markets that are incomplete (`MFRR`) with a clear
  message instead of failing inside the model.
- **Module parameters.** Consistent and actually used: `rsoc` bounds, `dod`, `soc_initial`
  within the usable range, `max_cycles_day` > 0 (several are xfail bugs today).
- **Period.** The cycle budget is computed per calendar year; warn when the run covers a
  partial year (see `max_cycles_day` below).

**Open questions:**
- Where does it live? Likely `powersim/optimizers/presolve.py`, with generic checks plus
  optimizer-specific hooks (`Optimizer.presolve()` called in `solve()` before
  `_model_setup()`, and a second hook after it).
- Adjust or reject? Proposal: adjust and report when the intent is clear (cap a band), reject
  when it is not (incomplete market).
- Does the presolve report go into the run? It would mean a new JSON file, so bump
  `SCHEMA_VERSION`.

## Optimizers: review `PerfectOptimizer` constraints

`PerfectOptimizer` is likely under-constrained: it can reach solutions that are physically
feasible period by period but not admissible in the market. To be revisited as a whole when
working on the optimizers in detail.

### aFRR band limited by unit capability (not only by grid capacity)

**Problem.** `Band_up` / `Band_down` are only limited by the grid connection
(`capacity_sell` / `capacity_buy`) and by what the energy markets already use
(`Total_power_pre_allocated`). Nothing links them to the battery power.

Example: grid 10 MW, battery 10 MWh / 2.5 MW, band price 50 €/MW.
- Hours without activation: it offers 10 MW of band and collects 4x the band revenue the
  battery could really back.
- Hours with full activation (`bin_max`): it must deliver `P_up` = 10 MW but only discharges
  2.5 MW. It closes the balance by **buying 7.5 MW in day-ahead**, a schedule the battery could
  not execute on its own (it only works because the activation is known in advance).

Market rule: the band offered cannot exceed what the unit could deliver if fully activated,
whether or not it is finally activated.

**Proposal** (linear, no binaries):

```
Band_up[t]   <= sum(Pmax_bat) + generation[t] - Total_power_pre_allocated[t]
Band_down[t] <= sum(Pmax_bat)                 + Total_power_pre_allocated[t]
# optional: energy-market schedule executable on its own
-sum(Pmax_bat) <= Total_power_pre_allocated[t] <= sum(Pmax_bat) + generation[t]
```

Open questions:
- Whether to add the third constraint, or accept that advantage of perfect foresight.
- How `System.efficiency` enters (today it is only applied to export).

**Not to do:** reserve energy (SOC) for activations. Activations are predefined inputs and the
perfect-foresight model already guarantees they are met.

**Evidence in saved runs (2026-11-09, limit-case runs, Developer tab "Reserve band backed by
the assets"):** a plant **without assets** (5 MW export, 0 MW import, DA + ID + aFRR) earns
550 k€ in 305 days: 451 k€ of up band with nothing behind it, plus energy "sold" in DA/ID
(1,544 MWh) and cancelled by downward activations (P_down follows Band_up, the known xfail
bug), so the export is 0. PV-only with aFRR: band above PV output in 68 % of band periods
(nights).

**First step when implementing:** a test with the example above (2.5 MW battery, 10 MW grid)
that shows the band exceeding the battery power.

### `max_cycles_day` exceeded in long runs (low priority)

Found by the dashboard "Daily cycle limit" check (2026-11-08):
- `y2_0001 - bess_pv - DA` (real data, 701 d, limit 1.5/day): 65 days above, max 1.87/day.
- Synthetic "PV 30 MW + BESS 20 MW / 2 h - DA + aFRR - 2 years": 30 days above, max 1.66/day.

The dashboard defines daily cycles as daily discharged energy / total battery capacity
(`daily_cycles` in `powersim/dashboard/tabs/overview_data.py`). Either the model counts cycles
differently (charged energy, RTE, SOC-based, a window not aligned to calendar days in UTC...)
or the `max_cycles_day` constraint does not bind as intended.

**First step:** read how `Milp_Battery` builds the cycle constraint and compute the same
quantity from a saved run. If the definitions differ, align the dashboard check (and document
the definition); if they match, write a failing test with a small synthetic case.
