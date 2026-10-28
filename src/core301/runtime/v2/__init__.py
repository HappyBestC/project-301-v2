"""Restricted, opt-in V2 runtime. No V1 factory or default version is changed."""


def open_research_case(*args, **kwargs):
    """Public unified research entry; lazy import preserves legacy imports."""
    from .research_router import open_research_case as open_case
    return open_case(*args, **kwargs)
