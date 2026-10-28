"""Full native state, held only for the lifetime of a counterfactual experiment."""
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import math

from .session import PulseSession


@dataclass
class PulseSnapshot:
    patient_id: str
    data_root: Path
    requested_fields: tuple[str, ...]
    simulation_time_s: float
    timestep_s: float
    spare_time_s: float
    sha256: str
    _state: str | None = field(repr=False)

    def __enter__(self):
        if self._state is None:
            raise RuntimeError("snapshot is closed")
        return self

    def close(self):
        self._state = None

    def __exit__(self, *exc):
        self.close()


class PulseStateManager:
    def save_state(self, session):
        state = session.serialize_state()
        return PulseSnapshot(session.patient_id, session.data_root, session.requested_fields,
                             session.get_simulation_time(), session.get_timestep(), session._spare_time,
                             sha256(state.encode()).hexdigest(), state)

    def load_state(self, snapshot):
        if snapshot._state is None:
            raise RuntimeError("snapshot is closed")
        if sha256(snapshot._state.encode()).hexdigest() != snapshot.sha256:
            raise ValueError("snapshot integrity check failed")
        session = PulseSession(snapshot.patient_id, snapshot.data_root, snapshot.requested_fields)
        try:
            session.initialize_from_state(snapshot._state, spare_time_s=snapshot.spare_time_s)
            if not math.isclose(session.get_simulation_time(), snapshot.simulation_time_s, abs_tol=1e-7, rel_tol=0):
                raise RuntimeError("restored simulation time differs from snapshot")
            if session.get_timestep() != snapshot.timestep_s:
                raise RuntimeError("restored timestep differs from snapshot")
            return session
        except BaseException:
            session.close()
            raise

    def fork(self, snapshot):
        return self.load_state(snapshot)
