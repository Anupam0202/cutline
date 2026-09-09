from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateProjectRequest(StrictModel):
    pass


class RevisionRequest(StrictModel):
    expected_revision: StrictInt = Field(ge=1)


class CueUpdateRequest(RevisionRequest):
    text: StrictStr = Field(min_length=1, max_length=500)


class ApplyRequest(RevisionRequest):
    confirmed: StrictBool
