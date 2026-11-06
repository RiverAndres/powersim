# App shell (everything that is not a tab)

Code: `powersim/dashboard/app.py` (layout and shared callbacks), `components.py` (shared pieces),
`assets/style.css` (all styles). Each tab's content and its **right side panel** are described in
the tab's own `.md`.

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
- Plotly figures: transparent background, same palette, horizontal legend on top
  (`figures.apply_theme`). Series colors from `powersim/visualization/styles.py`.

## Decisions

- Tabs are modules in `powersim/dashboard/tabs/` with ids prefixed by the tab id.
- The dashboard only reads saved runs; it never runs simulations.
