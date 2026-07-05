from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.auth import authenticate_admin_user, issue_admin_bearer_token, try_get_admin_identity
from app.config import settings
from app.services.license_manager import manager, parse_timestamp
from app.services.products import create_or_update_product, delete_product, list_products, list_products_with_stats


templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
router = APIRouter(tags=["admin-console"])

SESSION_COOKIE = "license_admin_session"


def _get_identity_from_request(request: Request):
    cookie_token = request.cookies.get(SESSION_COOKIE, "").strip()
    authorization = f"Bearer {cookie_token}" if cookie_token else ""
    return try_get_admin_identity(authorization=authorization)


def _require_console_identity(request: Request):
    identity = _get_identity_from_request(request)
    if identity:
        return identity
    return None


def _translate_status(status: str) -> str:
    mapping = {
        "active": "正常",
        "disabled": "已停用",
        "expired": "已过期",
        "deleted": "已删除",
    }
    return mapping.get(status.strip().lower(), "未知")


def _translate_plan_name(plan_name: str) -> str:
    normalized = plan_name.strip().lower()
    mapping = {
        "single-device": "单设备版",
        "multi-device": "多设备版",
        "weekly": "周卡",
        "yearly": "年卡",
    }
    if not plan_name.strip():
        return "标准版"
    return mapping.get(normalized, plan_name)


def _build_notice(message: str, count: int, success: int, failed: int) -> str:
    if message == "product_saved":
        return "项目已保存。"
    if message == "product_deleted":
        return "项目已删除。"
    if message == "license_created":
        return "激活码已生成。"
    if message == "license_added":
        return "指定激活码已添加。"
    if message == "batch_created":
        return f"已批量生成 {count} 个激活码。"
    if message == "batch_done":
        return f"批量处理完成，成功 {success} 条，失败 {failed} 条。"
    if message == "license_disabled":
        return "激活码已停用。"
    if message == "license_reset":
        return "激活记录已重置。"
    if message == "license_deleted":
        return "激活码已删除。"
    return "操作已完成。"


def _clean_message_text(value: str) -> str:
    return " ".join(value.strip().split())


def _build_redirect(product_code: str, message: str, count: int = 0, success: int = 0, failed: int = 0):
    query = {"product_code": product_code.strip().lower(), "message": message}
    if count:
        query["count"] = str(count)
    if success or failed:
        query["success"] = str(success)
        query["failed"] = str(failed)
    return RedirectResponse(url=f"/console?{urlencode(query)}", status_code=303)


def _build_error_redirect(product_code: str, error_text: str):
    query = {
        "product_code": product_code.strip().lower(),
        "error": _clean_message_text(error_text) or "操作失败，请重试。",
    }
    return RedirectResponse(url=f"/console?{urlencode(query)}", status_code=303)


def _format_products(products: list[dict[str, str]]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for product in products:
        item = dict(product)
        item["display_name"] = product["product_name"].strip() or "未命名项目"
        items.append(item)
    return items


def _resolve_selected_product_display_name(selected_product: str, products: list[dict[str, str]]) -> str:
    normalized_product = selected_product.strip().lower()
    if not normalized_product:
        return "全部项目"
    for product in products:
        if str(product["product_code"]).strip().lower() == normalized_product:
            return str(product["display_name"])
    return "全部项目"


def _format_licenses(licenses: list[dict[str, str | int]], products: list[dict[str, str]]) -> list[dict[str, str | int]]:
    product_map = {product["product_code"]: product["display_name"] for product in products}
    items: list[dict[str, str | int]] = []
    for license_item in licenses:
        item = dict(license_item)
        item["display_status"] = _translate_status(str(item["effective_status"]))
        item["display_plan_name"] = _translate_plan_name(str(item["plan_name"]))
        item["display_product_name"] = product_map.get(str(item["product_code"]), "未命名项目")
        item["display_expires_at"] = _format_console_expiry_display(
            str(item["expires_at"] or ""),
            int(item["validity_seconds"] or 0),
        )
        items.append(item)
    return items


def _parse_license_keys(raw_text: str) -> list[str]:
    tokens = raw_text.replace(",", "\n").replace("，", "\n").splitlines()
    return [token.strip() for token in tokens if token.strip()]


def _build_export_rows(product_code: str = "") -> list[dict[str, str | int]]:
    rows = manager.list_licenses(product_code, "")
    return [
        {
            "项目标识": str(item["product_code"]),
            "激活码": str(item["license_key"]),
            "套餐": str(item["plan_name"]),
            "状态": _translate_status(str(item["effective_status"])),
            "设备占用": f"{item['active_activations']}/{item['max_activations']}",
            "过期时间": _format_console_expiry_display(
                str(item["expires_at"] or ""),
                int(item["validity_seconds"] or 0),
            ),
            "最近校验时间": str(item["last_validated_at"] or ""),
            "创建时间": str(item["created_at"] or ""),
            "备注": str(item["notes"] or ""),
        }
        for item in rows
    ]


def _format_validity_label(validity_seconds: int) -> str:
    if validity_seconds <= 0:
        return "长期有效"
    if validity_seconds % 86400 == 0:
        days = validity_seconds // 86400
        return f"{days} 天"
    hours = round(validity_seconds / 3600, 1)
    return f"{hours:g} 小时"


def _format_console_expiry_display(expires_at: str, validity_seconds: int) -> str:
    normalized_expiry = expires_at.strip()
    if normalized_expiry:
        return normalized_expiry
    if validity_seconds > 0:
        return f"首次激活后 {_format_validity_label(validity_seconds)}"
    return "长期有效"


def _normalize_console_expiry(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo or timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def resolve_console_license_form(
    validity_mode: str,
    custom_expires_at: str = "",
    custom_plan_name: str = "",
) -> tuple[str, str, int]:
    normalized_mode = validity_mode.strip().lower() or "weekly"

    if normalized_mode == "weekly":
        return "周卡", "", 7 * 24 * 60 * 60
    if normalized_mode == "yearly":
        return "年卡", "", 365 * 24 * 60 * 60
    if normalized_mode == "custom":
        if not custom_expires_at.strip():
            raise RuntimeError("选择自定义到期时间时，必须填写具体时间。")
        target_time = parse_timestamp(_normalize_console_expiry(custom_expires_at))
        delta_seconds = int((target_time - datetime.now(timezone.utc)).total_seconds())
        if delta_seconds <= 0:
            raise RuntimeError("自定义到期时间必须晚于当前时间。")
        return custom_plan_name.strip() or "自定义有效期", "", delta_seconds
    if normalized_mode in {"permanent", "lifetime"}:
        return custom_plan_name.strip() or "长期有效", "", 0

    raise RuntimeError("不支持的有效期模式。")


def _build_license_summary(licenses: list[dict[str, str | int]]) -> dict[str, int]:
    summary = {
        "total": len(licenses),
        "active": 0,
        "expired": 0,
        "disabled": 0,
    }
    for item in licenses:
        status = str(item.get("effective_status", "")).strip().lower()
        if status in summary:
            summary[status] += 1
    return summary


@router.get("/console/login", response_class=HTMLResponse)
def login_page(request: Request):
    identity = _get_identity_from_request(request)
    if identity:
        return RedirectResponse(url="/console", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "title": "激活码管理后台登录",
            "error": "",
        },
    )


@router.post("/console/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
):
    user = authenticate_admin_user(email, password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "title": "激活码管理后台登录",
                "error": "邮箱或密码错误",
            },
            status_code=401,
        )

    token = issue_admin_bearer_token(int(user["id"]), str(user["email"]), str(user["role"]))
    response = RedirectResponse(url="/console", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        token["access_token"],
        httponly=True,
        samesite="lax",
        secure=not settings.is_development,
        max_age=60 * 60 * 12,
    )
    return response


@router.get("/console/logout")
def logout():
    response = RedirectResponse(url="/console/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/console", response_class=HTMLResponse)
def console_home(
    request: Request,
    product_code: str = "",
    message: str = "",
    error: str = "",
    count: int = 0,
    success: int = 0,
    failed: int = 0,
):
    identity = _require_console_identity(request)
    if not identity:
        return RedirectResponse(url="/console/login", status_code=303)

    products = _format_products(list_products())
    product_cards = _format_products(list_products_with_stats())
    selected_product = product_code.strip().lower()
    selected_product_name = _resolve_selected_product_display_name(selected_product, products)
    licenses = _format_licenses(manager.list_licenses(selected_product, ""), products)
    creation_product_code = selected_product or (products[0]["product_code"] if products else "")
    summary = _build_license_summary(licenses)
    notice_text = _build_notice(message, count, success, failed) if message else ""
    error_text = _clean_message_text(error) if error else ""

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "title": "激活码管理后台",
            "identity": identity,
            "products": products,
            "product_cards": product_cards,
            "selected_product": selected_product,
            "selected_product_name": selected_product_name,
            "creation_product_code": creation_product_code,
            "licenses": licenses,
            "summary": summary,
            "notice_text": notice_text,
            "error_text": error_text,
        },
    )


@router.post("/console/products")
def console_create_product(
    request: Request,
    product_code: str = Form(default=""),
    product_name: str = Form(default=""),
    status: str = Form(default="active"),
):
    identity = _require_console_identity(request)
    if not identity:
        return RedirectResponse(url="/console/login", status_code=303)
    try:
        item = create_or_update_product(product_code, product_name, status)
    except Exception as exc:
        return _build_error_redirect(product_code, str(exc))
    return _build_redirect(str(item["product_code"]), "product_saved")


@router.post("/console/products/{product_code}/delete")
def console_delete_product(request: Request, product_code: str):
    identity = _require_console_identity(request)
    if not identity:
        return RedirectResponse(url="/console/login", status_code=303)
    try:
        item = delete_product(product_code)
    except Exception as exc:
        return _build_error_redirect(product_code, str(exc))
    return _build_redirect(str(item["product_code"]), "product_deleted")


@router.post("/console/licenses")
def console_create_license(
    request: Request,
    product_code: str = Form(default=""),
    custom_license_key: str = Form(default=""),
    plan_name: str = Form(default="标准版"),
    validity_mode: str = Form(default="weekly"),
    custom_expires_at: str = Form(default=""),
    custom_plan_name: str = Form(default=""),
    max_activations: int = Form(default=1),
    expires_at: str = Form(default=""),
    notes: str = Form(default=""),
    quantity: int = Form(default=1),
    submit_mode: str = Form(default="single"),
):
    identity = _require_console_identity(request)
    if not identity:
        return RedirectResponse(url="/console/login", status_code=303)

    normalized_product = product_code.strip().lower()
    try:
        resolved_plan_name, resolved_expires_at, resolved_validity_seconds = resolve_console_license_form(
            validity_mode=validity_mode,
            custom_expires_at=custom_expires_at or expires_at,
            custom_plan_name=custom_plan_name or plan_name,
        )
        if custom_license_key.strip():
            manager.import_license(
                product_code=normalized_product,
                license_key=custom_license_key,
                plan_name=resolved_plan_name,
                max_activations=max_activations,
                customer_name="",
                customer_email="",
                expires_at=resolved_expires_at,
                validity_seconds=resolved_validity_seconds,
                status="active",
                notes=notes,
                operator_id=identity.operator_id,
            )
            return _build_redirect(normalized_product, "license_added")

        if submit_mode == "batch" or quantity > 1:
            result = manager.create_licenses_batch(
                product_code=normalized_product,
                quantity=quantity,
                plan_name=resolved_plan_name,
                max_activations=max_activations,
                expires_at=resolved_expires_at,
                validity_seconds=resolved_validity_seconds,
                notes=notes,
                operator_id=identity.operator_id,
            )
            return _build_redirect(normalized_product, "batch_created", count=int(result["count"]))

        manager.create_license(
            product_code=normalized_product,
            customer_name="",
            customer_email="",
            plan_name=resolved_plan_name,
            max_activations=max_activations,
            expires_at=resolved_expires_at,
            validity_seconds=resolved_validity_seconds,
            notes=notes,
            operator_id=identity.operator_id,
        )
        return _build_redirect(normalized_product, "license_created")
    except Exception as exc:
        return _build_error_redirect(normalized_product, str(exc))


@router.post("/console/licenses/batch")
def console_batch_mutation(
    request: Request,
    product_code: str = Form(default=""),
    action: str = Form(default="reset"),
    license_keys_text: str = Form(default=""),
    expires_at: str = Form(default=""),
):
    identity = _require_console_identity(request)
    if not identity:
        return RedirectResponse(url="/console/login", status_code=303)

    try:
        result = manager.batch_update_licenses(
            license_keys=_parse_license_keys(license_keys_text),
            action=action.strip(),
            expires_at=expires_at,
            operator_id=identity.operator_id,
        )
    except Exception as exc:
        return _build_error_redirect(product_code, str(exc))
    if not result["ok"]:
        first_error = str(result["results"][0]["message"]) if result["results"] else "批量处理失败。"
        return _build_error_redirect(product_code, first_error)
    return _build_redirect(
        product_code,
        "batch_done",
        success=int(result["success_count"]),
        failed=int(result["failed_count"]),
    )


@router.post("/console/licenses/selection-action")
def console_selection_action(
    request: Request,
    product_code: str = Form(default=""),
    selection_action: str = Form(default="delete"),
    selected_license_keys: list[str] = Form(default=[]),
):
    identity = _require_console_identity(request)
    if not identity:
        return RedirectResponse(url="/console/login", status_code=303)

    try:
        result = manager.batch_update_licenses(
            license_keys=selected_license_keys,
            action=selection_action.strip(),
            operator_id=identity.operator_id,
        )
    except Exception as exc:
        return _build_error_redirect(product_code, str(exc))
    if not result["ok"]:
        first_error = str(result["results"][0]["message"]) if result["results"] else "批量处理失败。"
        return _build_error_redirect(product_code, first_error)
    return _build_redirect(
        product_code,
        "batch_done",
        success=int(result["success_count"]),
        failed=int(result["failed_count"]),
    )


@router.post("/console/licenses/{license_key}/disable")
def console_disable_license(request: Request, license_key: str, product_code: str = Form(default="")):
    identity = _require_console_identity(request)
    if not identity:
        return RedirectResponse(url="/console/login", status_code=303)
    result = manager.disable_license(license_key, operator_id=identity.operator_id)
    if not result.ok:
        return _build_error_redirect(product_code, result.message)
    return _build_redirect(product_code, "license_disabled")


@router.post("/console/licenses/{license_key}/reset")
def console_reset_license(request: Request, license_key: str, product_code: str = Form(default="")):
    identity = _require_console_identity(request)
    if not identity:
        return RedirectResponse(url="/console/login", status_code=303)
    result = manager.reset_activations(license_key, operator_id=identity.operator_id)
    if not result.ok:
        return _build_error_redirect(product_code, result.message)
    return _build_redirect(product_code, "license_reset")


@router.post("/console/licenses/{license_key}/delete")
def console_delete_license(request: Request, license_key: str, product_code: str = Form(default="")):
    identity = _require_console_identity(request)
    if not identity:
        return RedirectResponse(url="/console/login", status_code=303)
    result = manager.delete_license(license_key, operator_id=identity.operator_id)
    if not result.ok:
        return _build_error_redirect(product_code, result.message)
    return _build_redirect(product_code, "license_deleted")


@router.get("/console/export/licenses.csv")
def console_export_licenses(request: Request, product_code: str = ""):
    identity = _require_console_identity(request)
    if not identity:
        return RedirectResponse(url="/console/login", status_code=303)

    rows = _build_export_rows(product_code)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["项目标识", "激活码", "套餐", "状态", "设备占用", "过期时间", "最近校验时间", "创建时间", "备注"],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="console-licenses.csv"; filename*=UTF-8\'\'{quote("激活码列表.csv")}'
            )
        },
    )


@router.get("/console/export/backup.json")
def console_export_backup(request: Request, product_code: str = ""):
    identity = _require_console_identity(request)
    if not identity:
        return RedirectResponse(url="/console/login", status_code=303)

    payload = manager.export_backup(product_code)
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="console-backup.json"; filename*=UTF-8\'\'{quote("授权后台备份.json")}'
            )
        },
    )
