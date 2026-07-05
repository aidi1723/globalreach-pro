from __future__ import annotations

import csv
import io
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

from app.auth import (
    AdminIdentity,
    authenticate_admin_user,
    issue_admin_bearer_token,
    require_admin_identity,
)
from app.schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    BatchCreateLicensesRequest,
    BatchCreateLicensesResponse,
    BatchLicenseActionRequest,
    BatchLicenseActionResponse,
    CreateLicenseRequest,
    CreateLicenseResponse,
    LicenseMutationRequest,
    LicenseStatusResponse,
    ListLicensesResponse,
    ProductListResponse,
    ProductRequest,
    ProductResponse,
)
from app.services.license_manager import manager
from app.services.products import create_or_update_product, list_products


router = APIRouter(prefix="/admin", tags=["admin"])


def _raise_business_error(message: str, *, status_code: int = status.HTTP_400_BAD_REQUEST):
    raise HTTPException(status_code=status_code, detail=message)


def _raise_for_license_result(result):
    if result.ok:
        return
    status_code = status.HTTP_404_NOT_FOUND if result.code == "invalid_license" else status.HTTP_400_BAD_REQUEST
    _raise_business_error(result.message, status_code=status_code)


def _translate_status(status: str) -> str:
    mapping = {
        "active": "正常",
        "disabled": "已停用",
        "expired": "已过期",
        "deleted": "已删除",
    }
    return mapping.get(status.strip().lower(), status)


def _translate_plan_name(plan_name: str) -> str:
    normalized = plan_name.strip().lower()
    mapping = {
        "single-device": "单设备版",
        "multi-device": "多设备版",
    }
    if not plan_name.strip():
        return "标准版"
    return mapping.get(normalized, plan_name)


def _format_validity_label(validity_seconds: int) -> str:
    if validity_seconds <= 0:
        return "长期有效"
    if validity_seconds % 86400 == 0:
        return f"{validity_seconds // 86400} 天"
    return f"{validity_seconds / 3600:g} 小时"


def _format_expiry_display(expires_at: str, validity_seconds: int) -> str:
    normalized_expiry = expires_at.strip()
    if normalized_expiry:
        return normalized_expiry
    if validity_seconds > 0:
        return f"首次激活后 {_format_validity_label(validity_seconds)}"
    return ""


def _build_export_rows(product_code: str = "", license_key: str = "") -> list[dict[str, str | int]]:
    rows = manager.list_licenses(product_code, license_key)
    return [
        {
            "项目标识": str(item["product_code"]),
            "激活码": str(item["license_key"]),
            "套餐": _translate_plan_name(str(item["plan_name"])),
            "状态": _translate_status(str(item["effective_status"])),
            "设备占用": f"{item['active_activations']}/{item['max_activations']}",
            "过期时间": _format_expiry_display(
                str(item["expires_at"] or ""),
                int(item["validity_seconds"] or 0),
            ),
            "最近校验时间": str(item["last_validated_at"] or ""),
            "创建时间": str(item["created_at"] or ""),
            "备注": str(item["notes"] or ""),
        }
        for item in rows
    ]


def _build_csv_content(rows: list[dict[str, str | int]]) -> str:
    output = io.StringIO()
    fieldnames = [
        "项目标识",
        "激活码",
        "套餐",
        "状态",
        "设备占用",
        "过期时间",
        "最近校验时间",
        "创建时间",
        "备注",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


@router.post("/auth/login", response_model=AdminLoginResponse)
def login(payload: AdminLoginRequest):
    user = authenticate_admin_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误。")
    token = issue_admin_bearer_token(int(user["id"]), str(user["email"]), str(user["role"]))
    return AdminLoginResponse(
        ok=True,
        access_token=token["access_token"],
        expires_at=token["expires_at"],
        operator_id=int(user["id"]),
        email=str(user["email"]),
        role=str(user["role"]),
    )


@router.get("/health")
def admin_health(_identity: AdminIdentity = Depends(require_admin_identity)):
    return {"ok": True, "message": "管理接口可用"}


@router.get("/products", response_model=ProductListResponse)
def get_products(_identity: AdminIdentity = Depends(require_admin_identity)):
    return ProductListResponse(ok=True, items=list_products())


@router.post("/products", response_model=ProductResponse)
def upsert_product(payload: ProductRequest, _identity: AdminIdentity = Depends(require_admin_identity)):
    try:
        item = create_or_update_product(payload.product_code, payload.product_name, payload.status)
    except RuntimeError as exc:
        _raise_business_error(str(exc))
    return ProductResponse(ok=True, item=item)


@router.post("/licenses", response_model=CreateLicenseResponse)
def create_license(payload: CreateLicenseRequest, identity: AdminIdentity = Depends(require_admin_identity)):
    try:
        if payload.license_key.strip():
            result = manager.import_license(
                product_code=payload.product_code,
                license_key=payload.license_key,
                customer_name=payload.customer_name,
                customer_email=payload.customer_email,
                plan_name=payload.plan_name,
                max_activations=payload.max_activations,
                validity_seconds=payload.validity_seconds,
                expires_at=payload.expires_at,
                status="active",
                notes=payload.notes,
                operator_id=identity.operator_id,
            )
        else:
            result = manager.create_license(
                product_code=payload.product_code,
                customer_name=payload.customer_name,
                customer_email=payload.customer_email,
                plan_name=payload.plan_name,
                max_activations=payload.max_activations,
                validity_seconds=payload.validity_seconds,
                expires_at=payload.expires_at,
                notes=payload.notes,
                operator_id=identity.operator_id,
            )
    except RuntimeError as exc:
        _raise_business_error(str(exc))
    return CreateLicenseResponse(**result)


@router.post("/licenses/batch-create", response_model=BatchCreateLicensesResponse)
def batch_create_licenses(
    payload: BatchCreateLicensesRequest,
    identity: AdminIdentity = Depends(require_admin_identity),
):
    try:
        result = manager.create_licenses_batch(
            product_code=payload.product_code,
            quantity=payload.quantity,
            plan_name=payload.plan_name,
            max_activations=payload.max_activations,
            validity_seconds=payload.validity_seconds,
            expires_at=payload.expires_at,
            notes=payload.notes,
            operator_id=identity.operator_id,
        )
    except RuntimeError as exc:
        _raise_business_error(str(exc))
    return BatchCreateLicensesResponse(**result)


@router.get("/licenses", response_model=ListLicensesResponse)
def list_licenses(
    product_code: str = Query(default=""),
    license_key: str = Query(default=""),
    _identity: AdminIdentity = Depends(require_admin_identity),
):
    return ListLicensesResponse(ok=True, items=manager.list_licenses(product_code, license_key))


@router.get("/licenses/export")
def export_licenses(
    product_code: str = Query(default=""),
    license_key: str = Query(default=""),
    format: str = Query(default="csv"),
    _identity: AdminIdentity = Depends(require_admin_identity),
):
    rows = _build_export_rows(product_code, license_key)
    if format.strip().lower() == "json":
        return JSONResponse({"ok": True, "items": rows})
    content = _build_csv_content(rows)
    filename = "激活码导出.csv"
    return Response(
        content="\ufeff" + content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="license-export.csv"; filename*=UTF-8\'\'{quote(filename)}'
            )
        },
    )


@router.get("/backup/export")
def export_backup(
    product_code: str = Query(default=""),
    _identity: AdminIdentity = Depends(require_admin_identity),
):
    return JSONResponse(manager.export_backup(product_code))


@router.post("/licenses/batch-mutate", response_model=BatchLicenseActionResponse)
def batch_mutate_licenses(
    payload: BatchLicenseActionRequest,
    identity: AdminIdentity = Depends(require_admin_identity),
):
    result = manager.batch_update_licenses(
        license_keys=payload.license_keys,
        action=payload.action,
        expires_at=payload.expires_at,
        operator_id=identity.operator_id,
    )
    if not result["ok"] and int(result["success_count"]) == 0:
        first_error = str(result["results"][0]["message"]) if result["results"] else "批量处理失败。"
        _raise_business_error(first_error)
    return BatchLicenseActionResponse(**result)


@router.post("/licenses/{license_key}/disable", response_model=LicenseStatusResponse)
def disable_license(license_key: str, identity: AdminIdentity = Depends(require_admin_identity)):
    result = manager.disable_license(license_key, operator_id=identity.operator_id)
    _raise_for_license_result(result)
    return LicenseStatusResponse(**result.__dict__)


@router.post("/licenses/{license_key}/extend", response_model=LicenseStatusResponse)
def extend_license(
    license_key: str,
    payload: LicenseMutationRequest,
    identity: AdminIdentity = Depends(require_admin_identity),
):
    result = manager.extend_license(license_key, payload.expires_at, operator_id=identity.operator_id)
    _raise_for_license_result(result)
    return LicenseStatusResponse(**result.__dict__)


@router.post("/licenses/{license_key}/reset-activations", response_model=LicenseStatusResponse)
def reset_activations(license_key: str, identity: AdminIdentity = Depends(require_admin_identity)):
    result = manager.reset_activations(license_key, operator_id=identity.operator_id)
    _raise_for_license_result(result)
    return LicenseStatusResponse(**result.__dict__)


@router.post("/licenses/{license_key}/delete", response_model=LicenseStatusResponse)
def delete_license(license_key: str, identity: AdminIdentity = Depends(require_admin_identity)):
    result = manager.delete_license(license_key, operator_id=identity.operator_id)
    _raise_for_license_result(result)
    return LicenseStatusResponse(**result.__dict__)
