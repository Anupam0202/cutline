from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateCueRequest(StrictModel):
    text: StrictStr = Field(min_length=1, max_length=500)
    start_ms: StrictInt = Field(ge=0, le=86_400_000)
    end_ms: StrictInt = Field(ge=1, le=86_400_000)
    kind: Literal["NARRATION_DRAFT", "QUOTATION"] = "NARRATION_DRAFT"

    @model_validator(mode="after")
    def validate_range(self) -> CreateCueRequest:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class CreateProjectRequest(StrictModel):
    title: StrictStr | None = Field(default=None, min_length=1, max_length=120)
    cues: list[CreateCueRequest] | None = Field(default=None, min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_custom_project(self) -> CreateProjectRequest:
        if self.cues is None:
            if self.title is not None:
                raise ValueError("title requires cues")
            return self
        if self.title is None:
            raise ValueError("custom projects require a title")
        if not any(cue.kind == "NARRATION_DRAFT" for cue in self.cues):
            raise ValueError("custom projects require at least one narration cue")
        ordered = sorted(self.cues, key=lambda cue: cue.start_ms)
        if list(self.cues) != ordered:
            raise ValueError("cues must be ordered by start_ms")
        for previous, current in zip(self.cues, self.cues[1:], strict=False):
            if current.start_ms < previous.end_ms:
                raise ValueError("cue time ranges cannot overlap")
        return self


class RevisionRequest(StrictModel):
    expected_revision: StrictInt = Field(ge=1)


class CueUpdateRequest(RevisionRequest):
    text: StrictStr = Field(min_length=1, max_length=500)


class ApplyRequest(RevisionRequest):
    confirmed: StrictBool
