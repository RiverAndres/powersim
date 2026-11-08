# Tab: Sandbox

Code: `powersim/dashboard/tabs/sandbox.py`.

## Purpose

Playground to decide what the dashboard should show. Experiments live here until the user
approves them; then they move to the tab where they belong.

## Layout description

Empty: a note "No experiments right now. New views are tried here before moving to their tab."

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

(none right now)

## Moved

- Candidate overview page → Visualization (approved by the user after 3 design + 3 polish
  rounds).

## Discarded

- Daily revenue by market: replaced by monthly revenue (daily bars unreadable over 2 years).
- SOC heatmap day × hour: replaced by month × hour (731 columns were noise).
