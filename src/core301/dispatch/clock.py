"""A backend-fed simulation clock, not a wall-clock scheduler or a new Pulse clock."""
from pydantic import TypeAdapter
from core301.contracts.base import Time


class SimulationClock:
    def __init__(self, now_s):
        self._now_s = TypeAdapter(Time).validate_python(now_s, strict=True)

    @property
    def now_s(self):
        return self._now_s

    def advance_to(self, simulation_time_s):
        value = TypeAdapter(Time).validate_python(simulation_time_s, strict=True)
        if value < self._now_s:
            raise ValueError("global simulation time cannot move backwards")
        self._now_s = value
