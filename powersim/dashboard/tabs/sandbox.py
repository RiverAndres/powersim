"""Sandbox tab: experiments to decide what the dashboard should show.

New views are tried here before moving to the tab where they belong; then they are removed
from here. Notes and decisions: ``.claude/dashboard/sandbox.md``. No experiments right now.
"""

from ..components import note
from .base import Tab


def layout() -> list:
    return [note("No experiments right now. New views are tried here before moving to their tab.")]


def register(app, run_input) -> None:
    """No callbacks while there are no experiments."""


TAB = Tab(
    id="sandbox",
    label="Sandbox",
    description="Experiments for new views",
    layout=layout,
    register=register,
)
