from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.rate_limit import enforce_public_rate_limit, extract_client_ip
from app.schemas import ActivateRequest, LicenseStatusResponse, ReleaseRequest, ValidateRequest
from app.services.license_manager import manager


router = APIRouter(tags=["public-license"], dependencies=[Depends(enforce_public_rate_limit)])


@router.post("/licenses/activate", response_model=LicenseStatusResponse)
def activate_license(payload: ActivateRequest, request: Request):
    data = payload.model_dump()
    data["client_ip"] = extract_client_ip(request)
    result = manager.activate_license(data)
    return LicenseStatusResponse(**result.__dict__)


@router.post("/licenses/validate", response_model=LicenseStatusResponse)
def validate_license(payload: ValidateRequest, request: Request):
    data = payload.model_dump()
    data["client_ip"] = extract_client_ip(request)
    result = manager.validate_license(data)
    return LicenseStatusResponse(**result.__dict__)


@router.post("/licenses/release", response_model=LicenseStatusResponse)
def release_license(payload: ReleaseRequest, request: Request):
    data = payload.model_dump()
    data["client_ip"] = extract_client_ip(request)
    result = manager.release_license(data)
    return LicenseStatusResponse(**result.__dict__)
