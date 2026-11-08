"""Pydantic-модели запросов/ответов API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Status = Literal["draft", "sent", "responded", "deleted", "refused"]
Method = Literal["email", "form", "manual"]
Category = Literal["people_search", "data_broker", "marketing", "search", "custom"]
Lang = Literal["ru", "en"]


class ProfileIn(BaseModel):
    full_name: str = Field("", max_length=200)
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    city: str = Field("", max_length=120)
    birth_year: str = Field("", max_length=4)
    address: str = Field("", max_length=400)
    language: Lang = "ru"

    @field_validator("birth_year")
    @classmethod
    def _check_year(cls, v: str) -> str:
        v = (v or "").strip()
        if v and (not v.isdigit() or not (1900 <= int(v) <= 2100)):
            raise ValueError("Год рождения должен быть числом между 1900 и 2100")
        return v

    @field_validator("emails")
    @classmethod
    def _check_emails(cls, v: list[str]) -> list[str]:
        clean = []
        for item in v:
            item = item.strip()
            if item and "@" not in item:
                raise ValueError(f"Некорректный email: {item}")
            if item:
                clean.append(item)
        return clean[:5]

    @field_validator("phones")
    @classmethod
    def _check_phones(cls, v: list[str]) -> list[str]:
        return [p.strip() for p in v if p.strip()][:5]


class BrokerIn(BaseModel):
    id: str = Field("", max_length=64)
    name: str = Field(..., min_length=1, max_length=120)
    category: Category = "data_broker"
    method: Method = "email"
    url: str = Field("", max_length=500)
    email: str = Field("", max_length=200)
    language: Lang = "ru"
    notes: str = Field("", max_length=1000)
    deadline_days: int = Field(30, ge=5, le=180)


class RequestCreate(BaseModel):
    broker_id: str
    language: Lang | None = None


class RequestPatch(BaseModel):
    status: Status | None = None
    note: str | None = Field(None, max_length=1000)


class SendIn(BaseModel):
    force_dry_run: bool | None = None


class ChatIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=4000)
    history: list[dict[str, Any]] = Field(default_factory=list)


class ApiResult(BaseModel):
    ok: bool = True
    detail: str = ""
    data: Any | None = None
