"""Definition of a dashboard tab and the registration of its callbacks."""

import json
from collections.abc import Callable
from dataclasses import dataclass

from dash import Dash, Input, Output, State, dcc
from dash.exceptions import PreventUpdate

TAB_INPUT = Input("tab-selector", "value")


@dataclass(frozen=True)
class Tab:
    """A dashboard tab.

    ``layout()`` returns the tab components. ``register(app, run_input)`` adds its callbacks;
    ``run_input`` is the ``Input`` carrying the path of the selected run (None if there are none).
    Component ids must start with the tab ``id`` so tabs never clash.

    Tabs register their callbacks as usual (``app.callback(...)``); ``register_tab`` makes them
    run only while the tab is shown (see ``ActiveTabApp``).
    """

    id: str
    label: str
    description: str
    layout: Callable[[], list]
    register: Callable[[Dash, object], None]


def register_tab(app: Dash, tab: Tab, run_input) -> list:
    """Register ``tab``'s callbacks so they only compute while it is the selected tab.

    Returns the extra components (``dcc.Store``) those callbacks need: add them to the layout.
    """
    proxy = ActiveTabApp(app, tab.id)
    tab.register(proxy, run_input)
    return [dcc.Store(id=store_id) for store_id in proxy.store_ids]


class ActiveTabApp:
    """Stand-in for the Dash app passed to ``Tab.register``.

    Each ``callback`` gets the selected tab as an extra input and a store with the input values
    it last computed. It runs only when its tab is selected and those values changed, so a hidden
    tab never computes, and showing a tab again with the same run does not recompute.
    """

    def __init__(self, app: Dash, tab_id: str):
        self.app = app
        self.tab_id = tab_id
        self.store_ids: list[str] = []

    def callback(self, *dependencies, **kwargs):
        outputs = [d for d in dependencies if isinstance(d, Output)]
        inputs = [d for d in dependencies if isinstance(d, Input)]
        states = [d for d in dependencies if isinstance(d, State)]
        store_id = f"{self.tab_id}-computed-{len(self.store_ids)}"
        self.store_ids.append(store_id)
        tab_id = self.tab_id

        def decorator(func):
            @self.app.callback(
                *outputs,
                Output(store_id, "data"),
                *inputs,
                TAB_INPUT,
                *states,
                State(store_id, "data"),
                **kwargs,
            )
            def guarded(*args):
                values = list(args[: len(inputs)])
                selected = args[len(inputs)]
                state_values = list(args[len(inputs) + 1 : -1])
                key = computation_key(values + state_values)
                if not should_compute(tab_id, selected, key, args[-1]):
                    raise PreventUpdate
                result = func(*values, *state_values)
                result = (result,) if len(outputs) == 1 else tuple(result)
                return (*result, key)

            return func

        return decorator


def computation_key(values: list) -> str:
    """Identity of the inputs of a callback, as stored after computing it."""
    return json.dumps(values, default=str, sort_keys=True)


def should_compute(tab_id: str, selected: str | None, key: str, computed: str | None) -> bool:
    """A tab callback computes only for the selected tab and inputs it has not computed yet."""
    return selected == tab_id and key != computed
