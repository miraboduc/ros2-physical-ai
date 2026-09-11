"""COMP-BR-03 — EnableGate.

Holds the pipeline enabled/disabled state (US-BR-003). Does not cancel an
in-flight goal on disable (BR006) — it simply stops NEW goals from being
sent; whatever is already EXECUTING keeps running to completion.
"""


class EnableGate:
    def __init__(self, enabled_on_start: bool = True) -> None:
        self._enabled = enabled_on_start

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)
