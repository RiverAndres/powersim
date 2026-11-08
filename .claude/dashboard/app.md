# App shell (everything that is not a tab)

Code: `powersim/dashboard/app.py` (layout and shared callbacks), `components.py` (shared pieces),
`assets/style.css` (all styles). Each tab's content and its **right side panel** are described in
the tab's own `.md`.

## Audience and goals (set by the user)

- **Audience**: companies evaluating the profitability of the studied plant. They do not need
  profitability from us (they will export the simulation into their own models), but they must
  be able to judge **whether the simulation makes sense and is worth exporting**.
- **Long runs**: simulations can last two years (quarter-hourly ≈ 70,000 periods). Information
  must stay clear and not go into detail unless the user looks for it (detail on demand).
- **At a glance**: the whole simulation must be understood at first sight: **headline numbers
  for everything**, **charts for the economic part**.
- **Energy flows**: what the PV sells, what the battery charges (from PV and from the grid) and
  what is sold to the grid; and the **distribution of the total energy among markets** (total
  only: per module it is not meaningful).

## Layout description

Approximate, as context:

```
+--------------------------------------------------------------------------------+
| [icon] Simulation runs | Information text (free, up to 2 lines)                |  header
|        powersim        |                                                       |
+-----------+-----------------------------------------------------+--------------+
| Tools     | ● Run name   period · periods · optimizer [MARKETS]  | right side   |
|           |-----------------------------------------------------| panel:       |
| [Visual.] |                                                     | defined by   |
| [Sandbox] |              content of the active tab              | each tab     |
|           |                                                     | (see its .md)|
+-----------+-----------------------------------------------------+--------------+
```

## Header

- Fixed at the top, 64 px high.
- Left: brand icon (⚡), eyebrow "Simulation runs", title "powersim".
- Right of the brand: **information text** of the "web". Set with
  `create_app(runs_dir, info="...")` or `powersim-dashboard --info "..."`; default in
  `DEFAULT_INFO` (`app.py`). Truncated to 2 lines.

## Left side panel: Tools

- Title "Tools" and one selectable card per tab (label + short description), from `TABS`
  (`powersim/dashboard/tabs/__init__.py`), in that order. The first tab is selected on start.
- Every tab stays in the layout; only the selected one is displayed.

## Status row (top of the main area)

- Shared by all tabs: green dot, run name (label or id), period, number and length of the
  periods, optimizer, one badge per market. "No saved runs in ..." when the folder is empty.

## Style

- Dark theme inspired by https://live-well-drilling-metrics.plotly.app/ (Dash + Mantine,
  forced dark). Recreated with plain CSS, no Mantine dependency.
- Palette (CSS variables in `style.css`): body `#1a1a19`, cards and panels `#232322`, borders
  `#383835` / `#4a4a46`, text `#f0efec`, dim text `#a3a29a` / `#898781`, accent `#4dabf7`.
- Fonts: Inter (text), IBM Plex Mono (numbers in KPIs and paths). Radius 8 px.
- Plotly figures: transparent background, same palette, horizontal legend below the plot
  (`figures.apply_theme`). Series colors from `powersim/visualization/styles.py`.

## Decisions

- Charts: legends below the plot; one opaque hover style for every figure (`HOVER_LABEL`;
  CSS forces `fill-opacity: 1` because plotly draws Sankey hover boxes at 0.65); plotly toolbar
  only on hover via CSS (`displayModeBar: "hover"` is coerced to always by dcc.Graph); period
  axes get one tick per bar up to 12 periods, otherwise every N periods (max 8), horizontal,
  "Jan<br>2025"; € and MWh axes scaled to k€/M€, GWh.
- Tabs are modules in `powersim/dashboard/tabs/` with ids prefixed by the tab id.
- Tab callbacks only compute while their tab is active (`register_tab` in `tabs/base.py`), so a
  heavy tab never slows down the others.
- UI changes are made by the `dashboard-builder` agent (`.claude/agents/dashboard-builder.md`):
  generic components in `components.py` / `figures.py`, placement in `tabs/`; the orchestrator
  reviews in Chrome (max 3 rounds per goal, then show the user).
- The dashboard only reads saved runs; it never runs simulations.
