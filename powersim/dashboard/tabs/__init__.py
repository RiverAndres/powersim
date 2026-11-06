"""Dashboard tabs. Each tab is a module exposing a ``TAB`` (see ``Tab``); its working notes
(purpose, questions it answers, decisions) live in ``.claude/dashboard/<tab id>.md``.

To add a tab: create the module, define ``TAB``, append it to ``TABS`` and write its ``.md``.
"""

from . import sandbox, visualization
from .base import Tab

TABS: list[Tab] = [visualization.TAB, sandbox.TAB]

__all__ = ["TABS", "Tab"]
