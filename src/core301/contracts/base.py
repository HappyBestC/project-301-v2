from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, AfterValidator


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("patient_id must not be blank")
    return value


PatientId = Annotated[str, AfterValidator(nonblank)]
Number = Annotated[float, Field(allow_inf_nan=False)]
Time = Annotated[Number, Field(ge=0)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True,
                              revalidate_instances="always")
