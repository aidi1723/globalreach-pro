from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def normalize_optional_timestamp(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


class ActivateRequest(BaseModel):
    product_code: str
    license_key: str
    machine_id: str
    machine_name: str = ""
    os_name: str = ""
    os_version: str = ""
    app_version: str = ""


class ValidateRequest(BaseModel):
    product_code: str
    license_key: str
    activation_token: str = ""
    machine_id: str
    app_version: str = ""


class ReleaseRequest(BaseModel):
    product_code: str
    license_key: str
    machine_id: str
    activation_token: str = Field(min_length=1)


class LicenseStatusResponse(BaseModel):
    ok: bool
    message: str
    code: str = ""
    license_status: str = ""
    activation_status: str = ""
    activation_token: str = ""
    expires_at: str = ""
    plan_name: str = ""
    max_activations: int = 0


class CreateLicenseRequest(BaseModel):
    product_code: str
    license_key: str = ""
    customer_name: str = ""
    customer_email: str = ""
    plan_name: str = "标准版"
    max_activations: int = Field(default=1, ge=1)
    validity_seconds: int = Field(default=0, ge=0)
    expires_at: str = ""
    notes: str = ""

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: str) -> str:
        return normalize_optional_timestamp(value)


class CreateLicenseResponse(BaseModel):
    ok: bool
    license_key: str


class BatchCreateLicensesRequest(BaseModel):
    product_code: str
    plan_name: str = "标准版"
    max_activations: int = Field(default=1, ge=1)
    validity_seconds: int = Field(default=0, ge=0)
    expires_at: str = ""
    notes: str = ""
    quantity: int = Field(default=1, ge=1, le=500)

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: str) -> str:
        return normalize_optional_timestamp(value)


class BatchCreateLicensesResponse(BaseModel):
    ok: bool
    items: list[str]
    count: int


class AdminLoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class AdminLoginResponse(BaseModel):
    ok: bool
    access_token: str
    expires_at: str
    operator_id: int
    email: str
    role: str


class ProductRequest(BaseModel):
    product_code: str
    product_name: str = ""
    status: str = "active"


class ProductResponse(BaseModel):
    ok: bool
    item: dict


class ProductListResponse(BaseModel):
    ok: bool
    items: list[dict]


class ListLicensesResponse(BaseModel):
    ok: bool
    items: list[dict]


class LicenseMutationRequest(BaseModel):
    expires_at: str = ""

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: str) -> str:
        return normalize_optional_timestamp(value)


class BatchLicenseActionRequest(BaseModel):
    action: Literal["disable", "reset", "delete", "extend"]
    license_keys: list[str] = Field(default_factory=list)
    expires_at: str = ""

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: str) -> str:
        return normalize_optional_timestamp(value)


class BatchLicenseActionResponse(BaseModel):
    ok: bool
    action: str
    success_count: int
    failed_count: int
    results: list[dict]
