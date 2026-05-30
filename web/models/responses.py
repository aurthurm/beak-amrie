"""Pydantic response models for REST endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SingleInterpretResult(BaseModel):
    whonet_test: str
    interpretation: str


class SingleInterpretResponse(BaseModel):
    results: list[SingleInterpretResult]


class BreakpointResponse(BaseModel):
    breakpoints: list[dict]


class RuleResponse(BaseModel):
    rules: list[dict]


class QCResponse(BaseModel):
    result: str


class OrganismItem(BaseModel):
    code: str
    name: str


class AntibioticItem(BaseModel):
    code: str
    name: str
    potencies: list[str] = Field(default_factory=list)


class ReferenceListResponse(BaseModel):
    items: list[str] | list[OrganismItem] | list[AntibioticItem]
