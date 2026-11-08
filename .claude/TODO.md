# TODO

Pending work that was analysed but deliberately postponed. Known bugs with a reproducing test
are tracked as `xfail(strict=True)` tests in `tests/`, not here.

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
