"""V2.1 research composites; V2 single-injury API is untouched."""
def open_research_composite_case(*args,**kwargs):
 from .runtime import open_research_composite_case as open_case
 return open_case(*args,**kwargs)
