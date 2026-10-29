"""Deterministic V1 triage from observable wounds and vital signs."""

from .rules import is_ambulatory, triage

__all__ = ['is_ambulatory', 'triage']
