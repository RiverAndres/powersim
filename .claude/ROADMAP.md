# Roadmap (short to medium term)

Set by the user on 2026-11-08. Not in the README on purpose. Work in this order:

1. **Dashboard**: improve the current Dash dashboard until it is decent
   (`.claude/dashboard/*.md`, `dashboard-builder` agent).
2. **Simulators and data**: pending optimizer work (`.claude/TODO.md`) and the user's own
   `esios_request` library (cache bug, dataset alignment).
3. **Tests**: improve coverage and fixtures (real data snapshots under `tests/data/`).
4. **Scale**: more optimizers (beyond the perfect-foresight benchmark) and future-price
   estimation strategies. Together with the current structure this is the basic skeleton of the
   whole application.
5. **UI again**: iterate the UI, add client-side analysis tools, keep iterating to debug.

Only after 1-5 (minimum viable product) the user will decide how to go web:

- Phase 1: private Dash deploy (Docker + gunicorn + HTTPS + auth proxy).
- Phase 2: product, typical **SaaS** (companies, users, per-company runs; FastAPI, job queue for
  simulations, PostgreSQL catalog, object storage + DuckDB for Parquet).
- Phase 3: separate React/Next.js frontend, only if needed.

Do not push deployment/infra work before that. When touching related code, prefer low-cost
choices that ease the SaaS move and propose them (run ids instead of filesystem paths in the
dashboard, a `RunStore` abstraction, config via env vars, dashboard reading `derived/`, no
assumption that every run belongs to everyone).
