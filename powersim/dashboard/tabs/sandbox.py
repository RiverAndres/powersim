"""Sandbox tab: experiments for new views of the selected run.

New views are tried here before moving to the tab where they belong; then they are removed
from here. Empty while there is no experiment in progress. Notes, workflow and the list of
discarded ideas: ``.claude/dashboard/sandbox.md``.
"""

from ..components import note
from .base import Tab

EMPTY_NOTE = "No experiments right now. New views are tried here before moving to their own tab."


def layout() -> list:
    return [note(EMPTY_NOTE, id="sandbox-empty")]


def register(app, run_input) -> None:
    """No callbacks while there are no experiments."""


TAB = Tab(
    id="sandbox",
    label="Sandbox",
    description="Experiments for new views",
    layout=layout,
    register=register,
)
