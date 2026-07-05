from __future__ import annotations

import re

from app.services.importer import LeadDataset


PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z0-9_]+)\}")
DEFAULT_VALUES = {
    "Name": "there",
    "Company": "your team",
    "Product": "your catalog",
    "Email": "",
}
CANONICAL_FIELDS = {
    "Email": "email",
    "Name": "name",
    "Company": "company",
    "Product": "product",
}


class SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def extract_placeholders(template: str) -> list[str]:
    found = PLACEHOLDER_PATTERN.findall(template)
    return list(dict.fromkeys(found))


def build_context(row: dict[str, str], dataset: LeadDataset) -> dict[str, str]:
    context = {key: value for key, value in row.items()}

    for placeholder, field_name in CANONICAL_FIELDS.items():
        mapped_header = dataset.field_mapping.get(field_name)
        value = row.get(mapped_header, "") if mapped_header else ""
        context[placeholder] = value or DEFAULT_VALUES.get(placeholder, "")

    return context


def render_template(template: str, row: dict[str, str], dataset: LeadDataset) -> tuple[str, list[str]]:
    placeholders = extract_placeholders(template)
    context = build_context(row, dataset)
    rendered = template.format_map(SafeDict(context))
    unresolved = [
        placeholder
        for placeholder in placeholders
        if "{" + placeholder + "}" in rendered
    ]
    fallback_required = [
        placeholder
        for placeholder in placeholders
        if placeholder in CANONICAL_FIELDS
        and not dataset.field_mapping.get(CANONICAL_FIELDS[placeholder])
    ]
    issues = list(dict.fromkeys(unresolved + fallback_required))
    return rendered, issues


def render_template_for_dataset(template: str, dataset: LeadDataset) -> tuple[str, list[str]]:
    if not dataset.rows:
        return "当前没有可预览的数据。", []
    return render_template(template, dataset.rows[0], dataset)


def available_placeholders(dataset: LeadDataset) -> set[str]:
    placeholders = set(dataset.headers)
    placeholders.update(CANONICAL_FIELDS.keys())
    return placeholders


def split_subject_and_body(rendered: str) -> tuple[str, str]:
    lines = rendered.splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip() or "GlobalReach PRO Test"
        body_lines = lines[1:]
        if body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
        body = "\n".join(body_lines).strip() or "SMTP test body"
        return subject, body
    return "GlobalReach PRO Test", rendered.strip() or "SMTP test body"
