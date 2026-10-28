from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
class CompositePlan(BaseModel):
 model_config=ConfigDict(extra='forbid',strict=True)
 patient_id:str=Field(min_length=1)
 pattern_id:str=Field(min_length=1)
 bundle:Literal['A','B','AB','BA']
class HostResources(BaseModel):
 model_config=ConfigDict(extra='forbid',strict=True)
 run_id:str=Field(min_length=1)
 patient_id:str=Field(min_length=1)
 stock:dict[str,int]
 holds:dict[str,int]
 capabilities:frozenset[str]
 permissions:frozenset[str]
 protected_route_available:bool=False
 receiving_environment_verified:bool=False
