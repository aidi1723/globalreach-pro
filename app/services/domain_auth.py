from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass


COMMON_DKIM_SELECTORS = [
    "default",
    "selector1",
    "selector2",
    "google",
    "dkim",
    "smtp",
]


@dataclass
class DNSRecordCheck:
    name: str
    status: str
    details: str


@dataclass
class EmailAuthReport:
    domain: str
    spf_found: bool
    dmarc_found: bool
    dkim_found: bool
    selectors_checked: list[str]
    checks: list[DNSRecordCheck]


class DomainCheckError(Exception):
    pass


def build_email_auth_report(domain: str, dkim_selector: str = "") -> EmailAuthReport:
    cleaned_domain = domain.strip().lower()
    if not cleaned_domain:
        raise DomainCheckError("域名不能为空。")

    checks = []

    spf_records = query_txt_records(cleaned_domain)
    spf_found = any("v=spf1" in record.lower() for record in spf_records)
    checks.append(
        DNSRecordCheck(
            name=cleaned_domain,
            status="PASS" if spf_found else "WARN",
            details="找到 SPF 记录。" if spf_found else "未找到 SPF 记录。",
        )
    )

    dmarc_domain = f"_dmarc.{cleaned_domain}"
    dmarc_records = query_txt_records(dmarc_domain)
    dmarc_found = any("v=dmarc1" in record.lower() for record in dmarc_records)
    checks.append(
        DNSRecordCheck(
            name=dmarc_domain,
            status="PASS" if dmarc_found else "WARN",
            details="找到 DMARC 记录。" if dmarc_found else "未找到 DMARC 记录。",
        )
    )

    selectors_checked = _selectors_to_probe(dkim_selector)
    dkim_found = False
    for selector in selectors_checked:
        lookup_domain = f"{selector}._domainkey.{cleaned_domain}"
        records = query_txt_records(lookup_domain)
        if records:
            dkim_found = True
            checks.append(
                DNSRecordCheck(
                    name=lookup_domain,
                    status="PASS",
                    details="找到 DKIM TXT 记录。",
                )
            )
            break

    if not dkim_found:
        checks.append(
            DNSRecordCheck(
                name=f"{selectors_checked[0]}._domainkey.{cleaned_domain}",
                status="WARN",
                details="未找到 DKIM 记录。若你知道 selector，请在 SMTP 配置中填写。",
            )
        )

    return EmailAuthReport(
        domain=cleaned_domain,
        spf_found=spf_found,
        dmarc_found=dmarc_found,
        dkim_found=dkim_found,
        selectors_checked=selectors_checked,
        checks=checks,
    )


def format_email_auth_report(report: EmailAuthReport) -> str:
    lines = [
        "域名认证预检",
        "",
        f"域名: {report.domain}",
        f"SPF: {'PASS' if report.spf_found else 'WARN'}",
        f"DMARC: {'PASS' if report.dmarc_found else 'WARN'}",
        f"DKIM: {'PASS' if report.dkim_found else 'WARN'}",
        f"已检查 selector: {', '.join(report.selectors_checked)}",
        "",
        "明细:",
    ]
    for check in report.checks:
        lines.append(f"- [{check.status}] {check.name}: {check.details}")
    lines.append("")
    lines.append("说明：SMTP 能发出邮件，不代表一定进箱。SPF/DKIM/DMARC 越完整，送达稳定性越高。")
    return "\n".join(lines)


def extract_domain_from_email(email: str) -> str:
    value = email.strip()
    if "@" not in value:
        return ""
    return value.split("@", 1)[1].lower()


def query_txt_records(name: str) -> list[str]:
    if shutil.which("dig"):
        return _query_with_dig(name)
    if shutil.which("nslookup"):
        return _query_with_nslookup(name)
    raise DomainCheckError("当前系统缺少 dig 或 nslookup，无法进行 DNS TXT 查询。")


def _query_with_dig(name: str) -> list[str]:
    try:
        result = subprocess.run(
            ["dig", "+short", "TXT", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
    except Exception as exc:
        raise DomainCheckError(f"DNS 查询失败：{exc}") from exc

    records = []
    for line in result.stdout.splitlines():
        parts = re.findall(r'"([^"]+)"', line)
        if parts:
            records.append("".join(parts))
    return records


def _query_with_nslookup(name: str) -> list[str]:
    try:
        result = subprocess.run(
            ["nslookup", "-type=TXT", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
    except Exception as exc:
        raise DomainCheckError(f"DNS 查询失败：{exc}") from exc

    records = []
    for line in result.stdout.splitlines():
        parts = re.findall(r'"([^"]+)"', line)
        if parts:
            records.append("".join(parts))
    return records


def _selectors_to_probe(selector: str) -> list[str]:
    if selector.strip():
        return [selector.strip()]
    return COMMON_DKIM_SELECTORS
