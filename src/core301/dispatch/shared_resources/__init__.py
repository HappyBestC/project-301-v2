"""M2-A shared research resources. No legacy runtime is switched automatically."""
from .manager import SharedResourceManager
from .models import (Action, Plan, Request, Resource, Location, Execution,
                     ReleaseEvidence, ResourceChange, Result, Conflict)

__all__ = ['SharedResourceManager', 'Action', 'Plan', 'Request', 'Resource', 'Location',
           'Execution', 'ReleaseEvidence', 'ResourceChange', 'Result', 'Conflict']
