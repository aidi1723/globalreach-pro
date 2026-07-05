import json
import os
import subprocess
import sys
from pathlib import Path


def test_license_platform_console_routes_exist(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"
    db_path = tmp_path / "console_routes.sqlite3"

    code = """
import json
import sys

sys.path.insert(0, sys.argv[1])

from app.main import app

def collect_route_paths(routes, prefix=""):
    paths = []
    for route in routes:
        path = getattr(route, "path", None)
        if path is not None:
            paths.append(f"{prefix}{path}")
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            include_context = getattr(route, "include_context", None)
            child_prefix = getattr(include_context, "prefix", "") if include_context else ""
            paths.extend(collect_route_paths(original_router.routes, f"{prefix}{child_prefix}"))
    return paths

paths = sorted(collect_route_paths(app.routes))
print(json.dumps({
    "has_console_login": "/console/login" in paths,
    "has_console_home": "/console" in paths,
    "has_admin_products": "/api/v1/admin/products" in paths,
    "has_console_batch": "/console/licenses/batch" in paths,
    "has_console_export": "/console/export/licenses.csv" in paths,
    "has_console_product_delete": "/console/products/{product_code}/delete" in paths,
    "has_admin_batch_create": "/api/v1/admin/licenses/batch-create" in paths,
    "has_admin_backup": "/api/v1/admin/backup/export" in paths,
}))
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "LICENSE_PLATFORM_DATABASE_URL": f"sqlite:///{db_path}"},
    )
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout.strip())
    assert payload["has_console_login"] is True
    assert payload["has_console_home"] is True
    assert payload["has_admin_products"] is True
    assert payload["has_console_batch"] is True
    assert payload["has_console_export"] is True
    assert payload["has_console_product_delete"] is True
    assert payload["has_admin_batch_create"] is True
    assert payload["has_admin_backup"] is True


def test_license_platform_import_legacy_licenses_script(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "legacy_import.sqlite3"
    source_path = tmp_path / "legacy.csv"
    source_path.write_text(
        "license_key,customer_email,customer_name,status,max_activations,notes\n"
        "OLD-AAA-BBBB-CCCC,first@example.com,First Customer,active,2,legacy-one\n"
        "OLD-ZZZ-YYYY-XXXX,second@example.com,Second Customer,disabled,1,legacy-two\n",
        encoding="utf-8",
    )

    run_result = subprocess.run(
        [
            sys.executable,
            "license-platform/tools/import_legacy_licenses.py",
            "--file",
            str(source_path),
            "--product-code",
            "plugin_system",
            "--product-name",
            "Plugin System",
            "--operator-id",
            "88",
        ],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "LICENSE_PLATFORM_DATABASE_URL": f"sqlite:///{db_path}"},
    )
    assert "imported=2" in run_result.stdout

    inspect_code = """
import json
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.row_factory = sqlite3.Row
products = [dict(row) for row in conn.execute("SELECT product_code, product_name FROM products ORDER BY product_code").fetchall()]
licenses = [dict(row) for row in conn.execute("SELECT license_key, product_code, status, max_activations FROM license_keys ORDER BY license_key").fetchall()]
events = [dict(row) for row in conn.execute("SELECT event_type, operator_id FROM license_events ORDER BY id").fetchall()]
print(json.dumps({"products": products, "licenses": licenses, "events": events}))
"""
    inspect_result = subprocess.run(
        [sys.executable, "-c", inspect_code, str(db_path)],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    payload = json.loads(inspect_result.stdout.strip())
    assert payload["products"][0]["product_code"] == "plugin_system"
    assert payload["licenses"][0]["product_code"] == "plugin_system"
    assert payload["licenses"][0]["status"] in {"active", "disabled"}
    assert all(item["event_type"] == "license_imported" for item in payload["events"])
    assert all(item["operator_id"] == 88 for item in payload["events"])


def _seed_admin_user(project_root: Path, api_root: Path, db_path: Path):
    code = """
import sys

sys.path.insert(0, sys.argv[1])

from app.auth import hash_password
from app.services.admin_users import create_or_update_admin_user

create_or_update_admin_user(
    email="admin@example.com",
    password_hash=hash_password("super-secret-123"),
    role="owner",
    status="active",
)
"""
    subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "LICENSE_PLATFORM_DATABASE_URL": f"sqlite:///{db_path}"},
    )


def _run_app_script(api_root: Path, db_path: Path, code: str, extra_env: dict[str, str] | None = None):
    env = {**os.environ, "LICENSE_PLATFORM_DATABASE_URL": f"sqlite:///{db_path}"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def test_license_platform_console_supports_batch_actions_and_chinese_ui(tmp_path):
    api_root = Path(__file__).resolve().parents[1] / "license-platform" / "apps" / "api"
    db_path = tmp_path / "console_ui.sqlite3"
    code = """
import asyncio
import json
import sys
from http.cookies import SimpleCookie
from urllib.parse import urlencode, urlparse

sys.path.insert(0, sys.argv[1])

from app.auth import hash_password
from app.main import app
from app.services.admin_users import create_or_update_admin_user
from app.services.license_manager import manager


class ASGIClient:
    def __init__(self, app):
        self.app = app
        self.cookies = {}

    def _cookie_header(self):
        return "; ".join(f"{key}={value}" for key, value in self.cookies.items())

    def _store_cookies(self, headers):
        for key, value in headers:
            if key.lower() != "set-cookie":
                continue
            cookie = SimpleCookie()
            cookie.load(value)
            for morsel in cookie.values():
                self.cookies[morsel.key] = morsel.value

    async def _send(self, method, path, query_string=b"", headers=None, body=b""):
        response = {"status": 500, "headers": [], "body": b""}
        sent = False
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query_string,
            "headers": headers or [],
            "client": ("testclient", 123),
            "server": ("testserver", 80),
            "root_path": "",
        }

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                response["status"] = message["status"]
                response["headers"] = [
                    (key.decode("latin1"), value.decode("latin1"))
                    for key, value in message.get("headers", [])
                ]
            elif message["type"] == "http.response.body":
                response["body"] += message.get("body", b"")

        await self.app(scope, receive, send)
        return response

    def request(self, method, url, *, form=None, json_payload=None, headers=None, follow_redirects=True):
        parsed = urlparse(url)
        body = b""
        request_headers = list((headers or {}).items())
        if self.cookies:
            request_headers.append(("cookie", self._cookie_header()))
        if form is not None:
            body = urlencode(form).encode("utf-8")
            request_headers.append(("content-type", "application/x-www-form-urlencoded"))
        elif json_payload is not None:
            body = json.dumps(json_payload).encode("utf-8")
            request_headers.append(("content-type", "application/json"))
        encoded_headers = [(key.lower().encode("latin1"), value.encode("latin1")) for key, value in request_headers]
        result = asyncio.run(
            self._send(
                method=method,
                path=parsed.path or "/",
                query_string=parsed.query.encode("utf-8"),
                headers=encoded_headers,
                body=body,
            )
        )
        self._store_cookies(result["headers"])
        if follow_redirects and result["status"] in {301, 302, 303, 307, 308}:
            location = dict(result["headers"]).get("location", "")
            redirect_method = "GET" if result["status"] in {301, 302, 303} else method
            return self.request(redirect_method, location, headers=headers, follow_redirects=True)
        return {
            "status": result["status"],
            "text": result["body"].decode("utf-8"),
            "headers": dict(result["headers"]),
        }


create_or_update_admin_user(
    email="admin@example.com",
    password_hash=hash_password("super-secret-123"),
    role="owner",
    status="active",
)

client = ASGIClient(app)
login_page = client.request("GET", "/console/login")
login_response = client.request(
    "POST",
    "/console/login",
    form={"email": "admin@example.com", "password": "super-secret-123"},
)
product_response = client.request(
    "POST",
    "/console/products",
    form={"product_code": "mail_system", "product_name": "邮件系统", "status": "active"},
)
single_response = client.request(
    "POST",
    "/console/licenses",
    form={
        "product_code": "mail_system",
        "plan_name": "标准版",
        "max_activations": "2",
        "quantity": "1",
        "notes": "首批授权",
    },
)
batch_response = client.request(
    "POST",
    "/console/licenses",
    form={
        "product_code": "mail_system",
        "plan_name": "标准版",
        "max_activations": "1",
        "quantity": "2",
        "notes": "批量生成",
    },
)
keys_before = [item["license_key"] for item in manager.list_licenses("mail_system", "")]
batch_action_response = client.request(
    "POST",
    "/console/licenses/batch",
    form={
        "product_code": "mail_system",
        "action": "delete",
        "license_keys_text": "\\n".join(keys_before[:2]),
    },
)
dashboard = client.request("GET", "/console?product_code=mail_system")
csv_export = client.request("GET", "/console/export/licenses.csv?product_code=mail_system", follow_redirects=False)
backup_export = client.request("GET", "/console/export/backup.json?product_code=mail_system", follow_redirects=False)

payload = {
    "login_page_has_title": "激活码管理后台" in login_page["text"],
    "login_page_has_license_word": "License" in login_page["text"],
    "dashboard_has_batch": "批量处理" in dashboard["text"],
    "dashboard_has_weekly_option": "周卡" in dashboard["text"],
    "dashboard_has_yearly_option": "年卡" in dashboard["text"],
    "dashboard_has_custom_option": "自定义到期" in dashboard["text"],
    "dashboard_has_customer_name": "客户名" in dashboard["text"],
    "dashboard_has_customer_email": "客户邮箱" in dashboard["text"],
    "dashboard_has_chinese_title": "激活码统一管理后台" in dashboard["text"],
    "dashboard_selected_product_name": "当前筛选项目</span>" in dashboard["text"] and "<strong>邮件系统</strong>" in dashboard["text"],
    "dashboard_selected_product_code": "当前筛选项目</span>" in dashboard["text"] and "<strong>mail_system</strong>" in dashboard["text"],
    "login_status": login_response["status"],
    "product_status": product_response["status"],
    "single_status": single_response["status"],
    "batch_status": batch_response["status"],
    "batch_action_status": batch_action_response["status"],
    "license_count_after_batch": len(manager.list_licenses("mail_system", "")),
    "csv_status": csv_export["status"],
    "csv_name": csv_export["headers"].get("content-disposition", ""),
    "backup_status": backup_export["status"],
    "backup_name": backup_export["headers"].get("content-disposition", ""),
    "backup_product": json.loads(backup_export["text"])["products"][0]["product_name"],
}
print(json.dumps(payload, ensure_ascii=False))
"""
    result = _run_app_script(
        api_root,
        db_path,
        code,
        extra_env={"LICENSE_PLATFORM_ADMIN_AUTH_SECRET": "test-admin-secret"},
    )
    payload = json.loads(result.stdout.strip())
    assert payload["login_page_has_title"] is True
    assert payload["login_page_has_license_word"] is False
    assert payload["dashboard_has_batch"] is True
    assert payload["dashboard_has_weekly_option"] is True
    assert payload["dashboard_has_yearly_option"] is True
    assert payload["dashboard_has_custom_option"] is True
    assert payload["dashboard_has_customer_name"] is False
    assert payload["dashboard_has_customer_email"] is False
    assert payload["dashboard_has_chinese_title"] is True
    assert payload["dashboard_selected_product_name"] is True
    assert payload["dashboard_selected_product_code"] is False
    assert payload["login_status"] == 200
    assert payload["product_status"] == 200
    assert payload["single_status"] == 200
    assert payload["batch_status"] == 200
    assert payload["batch_action_status"] == 200
    assert payload["license_count_after_batch"] == 1
    assert payload["csv_status"] == 200
    assert "filename*=" in payload["csv_name"]
    assert payload["backup_status"] == 200
    assert "filename*=" in payload["backup_name"]
    assert payload["backup_product"] == "邮件系统"


def test_console_license_validity_modes_resolve_expected_plan_and_expiry(tmp_path):
    api_root = Path(__file__).resolve().parents[1] / "license-platform" / "apps" / "api"
    db_path = tmp_path / "console_validity.sqlite3"
    code = """
import json
import sys

sys.path.insert(0, sys.argv[1])

from app.routes.console import resolve_console_license_form

weekly_plan, weekly_expiry, weekly_seconds = resolve_console_license_form("weekly")
yearly_plan, yearly_expiry, yearly_seconds = resolve_console_license_form("yearly")
custom_plan, custom_expiry, custom_seconds = resolve_console_license_form(
    "custom",
    "2026-12-31T23:59",
    "活动包",
)

print(json.dumps({
    "weekly_plan": weekly_plan,
    "weekly_expiry": weekly_expiry,
    "yearly_plan": yearly_plan,
    "yearly_expiry": yearly_expiry,
    "custom_plan": custom_plan,
    "custom_expiry": custom_expiry,
    "weekly_seconds": weekly_seconds,
    "yearly_seconds": yearly_seconds,
    "custom_seconds_positive": custom_seconds > 0,
}))
"""
    result = _run_app_script(
        api_root,
        db_path,
        code,
        extra_env={"LICENSE_PLATFORM_ADMIN_AUTH_SECRET": "test-admin-secret"},
    )
    payload = json.loads(result.stdout.strip())
    assert payload["weekly_plan"] == "周卡"
    assert payload["yearly_plan"] == "年卡"
    assert payload["custom_plan"] == "活动包"
    assert payload["weekly_expiry"] == ""
    assert payload["yearly_expiry"] == ""
    assert payload["custom_expiry"] == ""
    assert payload["weekly_seconds"] == 7 * 24 * 60 * 60
    assert payload["yearly_seconds"] == 365 * 24 * 60 * 60
    assert payload["custom_seconds_positive"] is True


def test_product_delete_requires_empty_product(tmp_path):
    api_root = Path(__file__).resolve().parents[1] / "license-platform" / "apps" / "api"
    db_path = tmp_path / "product_delete.sqlite3"
    code = """
import json
import sys

sys.path.insert(0, sys.argv[1])

from app.services.license_manager import manager
from app.services.products import create_or_update_product, delete_product, list_products_with_stats

create_or_update_product("empty_product", "空项目", "active")
deleted = delete_product("empty_product")

create_or_update_product("used_product", "有码项目", "active")
manager.create_license(product_code="used_product", plan_name="周卡", max_activations=1, notes="test")

error = ""
try:
    delete_product("used_product")
except Exception as exc:
    error = str(exc)

print(json.dumps({
    "deleted_code": deleted["product_code"],
    "error_contains": "不能直接删除" in error,
    "remaining_product_codes": [item["product_code"] for item in list_products_with_stats()],
}, ensure_ascii=False))
"""
    result = _run_app_script(
        api_root,
        db_path,
        code,
        extra_env={"LICENSE_PLATFORM_ADMIN_AUTH_SECRET": "test-admin-secret"},
    )
    payload = json.loads(result.stdout.strip())
    assert payload["deleted_code"] == "empty_product"
    assert payload["error_contains"] is True
    assert "used_product" in payload["remaining_product_codes"]


def test_license_platform_admin_api_supports_batch_create_delete_and_backup(tmp_path):
    api_root = Path(__file__).resolve().parents[1] / "license-platform" / "apps" / "api"
    db_path = tmp_path / "admin_api.sqlite3"
    code = """
import asyncio
import json
import sys
from http.cookies import SimpleCookie
from urllib.parse import urlencode, urlparse

sys.path.insert(0, sys.argv[1])

from app.auth import hash_password
from app.main import app
from app.services.admin_users import create_or_update_admin_user


class ASGIClient:
    def __init__(self, app):
        self.app = app
        self.cookies = {}

    async def _send(self, method, path, query_string=b"", headers=None, body=b""):
        response = {"status": 500, "headers": [], "body": b""}
        sent = False
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query_string,
            "headers": headers or [],
            "client": ("testclient", 123),
            "server": ("testserver", 80),
            "root_path": "",
        }

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                response["status"] = message["status"]
                response["headers"] = [
                    (key.decode("latin1"), value.decode("latin1"))
                    for key, value in message.get("headers", [])
                ]
            elif message["type"] == "http.response.body":
                response["body"] += message.get("body", b"")

        await self.app(scope, receive, send)
        return response

    def request(self, method, url, *, form=None, json_payload=None, headers=None):
        parsed = urlparse(url)
        body = b""
        request_headers = list((headers or {}).items())
        if form is not None:
            body = urlencode(form).encode("utf-8")
            request_headers.append(("content-type", "application/x-www-form-urlencoded"))
        elif json_payload is not None:
            body = json.dumps(json_payload).encode("utf-8")
            request_headers.append(("content-type", "application/json"))
        encoded_headers = [(key.lower().encode("latin1"), value.encode("latin1")) for key, value in request_headers]
        result = asyncio.run(
            self._send(
                method=method,
                path=parsed.path or "/",
                query_string=parsed.query.encode("utf-8"),
                headers=encoded_headers,
                body=body,
            )
        )
        return {
            "status": result["status"],
            "text": result["body"].decode("utf-8"),
            "headers": dict(result["headers"]),
        }


create_or_update_admin_user(
    email="admin@example.com",
    password_hash=hash_password("super-secret-123"),
    role="owner",
    status="active",
)

client = ASGIClient(app)
login = client.request(
    "POST",
    "/api/v1/admin/auth/login",
    json_payload={"email": "admin@example.com", "password": "super-secret-123"},
)
token = json.loads(login["text"])["access_token"]
headers = {"authorization": f"Bearer {token}"}
product = client.request(
    "POST",
    "/api/v1/admin/products",
    json_payload={"product_code": "email_system", "product_name": "邮箱系统", "status": "active"},
    headers=headers,
)
single = client.request(
    "POST",
    "/api/v1/admin/licenses",
    json_payload={"product_code": "email_system", "plan_name": "标准版", "max_activations": 2, "notes": "单条生成"},
    headers=headers,
)
batch = client.request(
    "POST",
    "/api/v1/admin/licenses/batch-create",
    json_payload={"product_code": "email_system", "plan_name": "标准版", "max_activations": 1, "quantity": 2},
    headers=headers,
)
items = json.loads(client.request("GET", "/api/v1/admin/licenses?product_code=email_system", headers=headers)["text"])["items"]
delete_target = items[0]["license_key"]
delete_response = client.request("POST", f"/api/v1/admin/licenses/{delete_target}/delete", headers=headers)
after_delete = json.loads(client.request("GET", "/api/v1/admin/licenses?product_code=email_system", headers=headers)["text"])
export_response = client.request("GET", "/api/v1/admin/licenses/export?product_code=email_system", headers=headers)
backup_response = client.request("GET", "/api/v1/admin/backup/export?product_code=email_system", headers=headers)

payload = {
    "login_status": login["status"],
    "product_status": product["status"],
    "single_status": single["status"],
    "single_key": json.loads(single["text"])["license_key"],
    "batch_status": batch["status"],
    "batch_count": json.loads(batch["text"])["count"],
    "list_count_before_delete": len(items),
    "first_customer_name": items[0]["customer_name"],
    "first_customer_email_suffix": items[0]["customer_email"].endswith("@local.invalid"),
    "delete_status": delete_response["status"],
    "list_count_after_delete": len(after_delete["items"]),
    "export_status": export_response["status"],
    "export_disposition": export_response["headers"].get("content-disposition", ""),
    "backup_status": backup_response["status"],
    "backup_license_count": len(json.loads(backup_response["text"])["licenses"]),
    "backup_deleted_count": len([item for item in json.loads(backup_response["text"])["licenses"] if item["status"] == "deleted"]),
    "backup_product_name": json.loads(backup_response["text"])["products"][0]["product_name"],
}
print(json.dumps(payload, ensure_ascii=False))
"""
    result = _run_app_script(
        api_root,
        db_path,
        code,
        extra_env={"LICENSE_PLATFORM_ADMIN_AUTH_SECRET": "test-admin-secret"},
    )
    payload = json.loads(result.stdout.strip())
    assert payload["login_status"] == 200
    assert payload["product_status"] == 200
    assert payload["single_status"] == 200
    assert payload["single_key"]
    assert payload["batch_status"] == 200
    assert payload["batch_count"] == 2
    assert payload["list_count_before_delete"] == 3
    assert payload["first_customer_name"] == "未登记"
    assert payload["first_customer_email_suffix"] is True
    assert payload["delete_status"] == 200
    assert payload["list_count_after_delete"] == 2
    assert payload["export_status"] == 200
    assert "filename*=" in payload["export_disposition"]
    assert payload["backup_status"] == 200
    assert payload["backup_license_count"] == 3
    assert payload["backup_deleted_count"] == 1
    assert payload["backup_product_name"] == "邮箱系统"


def test_license_platform_admin_api_returns_400_for_duplicate_manual_license(tmp_path):
    api_root = Path(__file__).resolve().parents[1] / "license-platform" / "apps" / "api"
    db_path = tmp_path / "admin_api_duplicate.sqlite3"
    code = """
import asyncio
import json
import sys
from urllib.parse import urlencode, urlparse

sys.path.insert(0, sys.argv[1])

from app.auth import hash_password
from app.main import app
from app.services.admin_users import create_or_update_admin_user


class ASGIClient:
    def __init__(self, app):
        self.app = app

    async def _send(self, method, path, query_string=b"", headers=None, body=b""):
        response = {"status": 500, "headers": [], "body": b""}
        sent = False
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query_string,
            "headers": headers or [],
            "client": ("testclient", 123),
            "server": ("testserver", 80),
            "root_path": "",
        }

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                response["status"] = message["status"]
                response["headers"] = [
                    (key.decode("latin1"), value.decode("latin1"))
                    for key, value in message.get("headers", [])
                ]
            elif message["type"] == "http.response.body":
                response["body"] += message.get("body", b"")

        await self.app(scope, receive, send)
        return response

    def request(self, method, url, *, json_payload=None, headers=None):
        parsed = urlparse(url)
        body = b""
        request_headers = list((headers or {}).items())
        if json_payload is not None:
            body = json.dumps(json_payload).encode("utf-8")
            request_headers.append(("content-type", "application/json"))
        encoded_headers = [(key.lower().encode("latin1"), value.encode("latin1")) for key, value in request_headers]
        result = asyncio.run(
            self._send(
                method=method,
                path=parsed.path or "/",
                query_string=parsed.query.encode("utf-8"),
                headers=encoded_headers,
                body=body,
            )
        )
        return {
            "status": result["status"],
            "text": result["body"].decode("utf-8"),
            "headers": dict(result["headers"]),
        }


create_or_update_admin_user(
    email="admin@example.com",
    password_hash=hash_password("super-secret-123"),
    role="owner",
    status="active",
)

client = ASGIClient(app)
login = client.request(
    "POST",
    "/api/v1/admin/auth/login",
    json_payload={"email": "admin@example.com", "password": "super-secret-123"},
)
token = json.loads(login["text"])["access_token"]
headers = {"authorization": f"Bearer {token}"}
first = client.request(
    "POST",
    "/api/v1/admin/licenses",
    json_payload={
        "product_code": "email_system",
        "license_key": "MAIL-AAAA-BBBB-CCCC",
        "plan_name": "标准版",
        "max_activations": 1,
    },
    headers=headers,
)
duplicate = client.request(
    "POST",
    "/api/v1/admin/licenses",
    json_payload={
        "product_code": "email_system",
        "license_key": "MAIL-AAAA-BBBB-CCCC",
        "plan_name": "标准版",
        "max_activations": 1,
    },
    headers=headers,
)

payload = {
    "first_status": first["status"],
    "duplicate_status": duplicate["status"],
    "duplicate_detail": json.loads(duplicate["text"])["detail"],
}
print(json.dumps(payload, ensure_ascii=False))
"""
    result = _run_app_script(
        api_root,
        db_path,
        code,
        extra_env={"LICENSE_PLATFORM_ADMIN_AUTH_SECRET": "test-admin-secret"},
    )
    payload = json.loads(result.stdout.strip())
    assert payload["first_status"] == 200
    assert payload["duplicate_status"] == 400
    assert "激活码已存在" in payload["duplicate_detail"]
