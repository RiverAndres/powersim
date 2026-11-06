"""Definition of a dashboard tab."""

from collections.abc import Callable
from dataclasses import dataclass

from dash import Dash


@dataclass(frozen=True)
class Tab:
    """A dashboard tab.

    ``layout()`` returns the tab components. ``register(app, run_input)`` adds its callbacks;
    ``run_input`` is the ``Input`` carrying the path of the selected run (None if there are none).
    Component ids must start with the tab ``id`` so tabs never clash.
    """

    id: str
    label: str
    description: str
    layout: Callable[[], list]
    register: Callable[[Dash, object], None]
