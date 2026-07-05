from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.importer import LeadDataset, extract_email_address
from app.services.template import available_placeholders, extract_placeholders


@dataclass
class PreflightReport:
    total_rows: int
    valid_email_rows: int
    missing_email_rows: int
    mapped_fields: dict[str, str | None]
    placeholders: list[str]
    unresolved_placeholders: list[str]
    fallback_placeholders: list[str]
    invalid_email_examples: list[str]
    unmapped_required_fields: list[str]


def build_preflight_report(dataset: LeadDataset, template: str) -> PreflightReport:
    email_header = dataset.field_mapping.get("email")
    valid_email_rows = 0
    invalid_email_examples = []

    for index, row in enumerate(dataset.rows, start=1):
        raw_email = row.get(email_header, "").strip() if email_header else ""
        email = extract_email_address(raw_email)
        if email:
            valid_email_rows += 1
        elif len(invalid_email_examples) < 5:
            invalid_email_examples.append(f"第 {index} 行: {raw_email or '空值'}")

    placeholders = extract_placeholders(template)
    unresolved = sorted(
        placeholder
        for placeholder in placeholders
        if placeholder not in available_placeholders(dataset)
    )
    fallback_placeholders = sorted(
        placeholder
        for placeholder in placeholders
        if placeholder in {"Email", "Company", "Name", "Product"}
        and not dataset.field_mapping.get(placeholder.lower())
    )
    unmapped_required_fields = [
        field
        for field in ("email", "company", "name", "product")
        if not dataset.field_mapping.get(field)
    ]

    return PreflightReport(
        total_rows=dataset.total_rows,
        valid_email_rows=valid_email_rows,
        missing_email_rows=dataset.total_rows - valid_email_rows,
        mapped_fields=dataset.field_mapping,
        placeholders=placeholders,
        unresolved_placeholders=unresolved,
        fallback_placeholders=fallback_placeholders,
        invalid_email_examples=invalid_email_examples,
        unmapped_required_fields=unmapped_required_fields,
    )


def format_preflight_report(report: PreflightReport) -> str:
    sendable_ratio = 0
    if report.total_rows:
        sendable_ratio = int((report.valid_email_rows / report.total_rows) * 100)

    lines = [
        "任务预检报告",
        "",
        f"总线索数: {report.total_rows}",
        f"有效邮箱数: {report.valid_email_rows}",
        f"缺失或无效邮箱数: {report.missing_email_rows}",
        f"当前可发送比例: {sendable_ratio}%",
        "",
        "字段映射:",
    ]
    for field in ("email", "company", "name", "product"):
        lines.append(f"- {field}: {report.mapped_fields.get(field) or '未识别'}")

    lines.append("")
    lines.append(
        "模板变量: " + (", ".join(report.placeholders) if report.placeholders else "未检测到变量")
    )
    lines.append(
        "未解析变量: "
        + (", ".join(report.unresolved_placeholders) if report.unresolved_placeholders else "无")
    )
    lines.append(
        "依赖默认值的变量: "
        + (", ".join(report.fallback_placeholders) if report.fallback_placeholders else "无")
    )
    lines.append(
        "未映射字段: "
        + (", ".join(report.unmapped_required_fields) if report.unmapped_required_fields else "无")
    )
    lines.append(
        "无效邮箱样例: "
        + (", ".join(report.invalid_email_examples) if report.invalid_email_examples else "无")
    )
    lines.append("")
    lines.append("下一步建议：先修正缺失邮箱和未识别字段，再接入 SMTP 测试发送。")
    return "\n".join(lines)
