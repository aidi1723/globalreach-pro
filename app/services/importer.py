from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    pd = None


EMAIL_PATTERN = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)
EMAIL_CANDIDATE_PATTERN = re.compile(
    r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})",
    re.IGNORECASE,
)
COMPANY_HINT_PATTERN = re.compile(
    r"\b(ltd|limited|inc|corp|co|company|group|llc|factory|trading|technology|tech|industrial)\b",
    re.IGNORECASE,
)
PERSON_NAME_PATTERN = re.compile(r"^[A-Za-z]+(?:[\s\-][A-Za-z]+){0,2}$")

FIELD_CONFIG = {
    "email": {
        "aliases": [
            "email",
            "e-mail",
            "mail",
            "邮箱",
            "联系邮箱",
            "邮箱地址",
            "emailaddress",
            "email address",
            "e-mailaddress",
            "email1",
            "email 1",
            "mailid",
            "emailid",
            "businessemail",
            "business email",
            "workemailaddress",
            "work email address",
            "companyemail",
            "company email",
            "corporateemail",
            "corporate email",
            "primaryemail",
            "primary email",
            "officialemail",
            "official email",
            "contactemail",
            "contactmail",
            "contact email address",
            "businessmail",
            "workemail",
        ],
    },
    "company": {
        "aliases": [
            "company",
            "companyname",
            "company_name",
            "organization",
            "organisation",
            "businessname",
            "buyercompany",
            "公司",
            "公司名",
            "企业名称",
            "客户公司",
        ],
    },
    "name": {
        "aliases": [
            "name",
            "fullname",
            "full_name",
            "firstname",
            "lastname",
            "contact",
            "contactname",
            "buyername",
            "联系人",
            "姓名",
            "客户名",
        ],
    },
    "product": {
        "aliases": [
            "product",
            "productname",
            "product_name",
            "category",
            "interestproduct",
            "mainproduct",
            "主营产品",
            "产品",
            "产品名",
            "采购产品",
        ],
    },
}

GENERIC_HEADER_ALIASES = [
    "phone",
    "telephone",
    "mobile",
    "website",
    "url",
    "address",
    "category",
    "reviewcount",
    "averagerating",
    "query",
    "updatedat",
    "facebook",
    "instagram",
    "linkedin",
    "youtube",
    "whatsapp",
    "twitter",
    "country",
    "state",
    "city",
    "zipcode",
    "pluscode",
    "locatedin",
    "businessstatus",
    "hours",
    "openinghours",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

LINK_LIKE_HEADER_TOKENS = (
    "website",
    "url",
    "facebook",
    "instagram",
    "linkedin",
    "youtube",
    "twitter",
    "whatsapp",
)


class ImporterError(Exception):
    pass


@dataclass
class LeadDataset:
    source_path: str
    headers: list[str]
    rows: list[dict[str, str]]
    field_mapping: dict[str, str | None]
    mapping_details: dict[str, dict[str, str]]

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    def mapping_summary(self) -> str:
        lines = ["字段映射结果："]
        for field in ("email", "company", "name", "product"):
            mapped = self.field_mapping.get(field) or "未识别"
            detail = self.mapping_details.get(field, {})
            confidence = detail.get("confidence", "low")
            reason = detail.get("reason", "无说明")
            lines.append(f"- {field}: {mapped} | confidence={confidence} | {reason}")
        return "\n".join(lines)

    def update_mapping(self, new_mapping: dict[str, str | None]):
        for field in ("email", "company", "name", "product"):
            mapped = new_mapping.get(field)
            self.field_mapping[field] = mapped
            self.mapping_details[field] = {
                "header": mapped or "",
                "confidence": "manual" if mapped else "none",
                "reason": "手动映射" if mapped else "未映射",
            }

    def row_at(self, index: int) -> dict[str, str]:
        if index < 0 or index >= len(self.rows):
            raise IndexError("线索索引超出范围。")
        return self.rows[index]


def load_leads(file_path: str) -> LeadDataset:
    path = Path(file_path)
    if not path.exists():
        raise ImporterError(f"文件不存在：{file_path}")

    suffix = path.suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise ImporterError("仅支持 CSV / XLSX / XLS 文件。")

    rows = _load_rows(path, suffix)
    if not rows:
        raise ImporterError("文件中没有可用的数据行。")

    headers = list(rows[0].keys())
    mapping, mapping_details = auto_map_fields(headers, rows)
    return LeadDataset(
        source_path=str(path),
        headers=headers,
        rows=rows,
        field_mapping=mapping,
        mapping_details=mapping_details,
    )


def format_dataset_preview(dataset: LeadDataset, limit: int = 5) -> str:
    lines = [
        f"Source: {Path(dataset.source_path).name}",
        f"Rows: {dataset.total_rows}",
        f"Headers: {', '.join(dataset.headers)}",
        "",
        "Preview:",
    ]
    for index, row in enumerate(dataset.rows[:limit], start=1):
        compact = " | ".join(f"{key}={value}" for key, value in row.items())
        lines.append(f"{index}. {compact}")
    if dataset.total_rows > limit:
        lines.append(f"... 共 {dataset.total_rows} 行，仅显示前 {limit} 行。")
    return "\n".join(lines)


def auto_map_fields(
    headers: list[str],
    rows: list[dict[str, str]] | None = None,
) -> tuple[dict[str, str | None], dict[str, dict[str, str]]]:
    sample_rows = rows[:25] if rows else []
    result = {}
    details = {}
    used_headers = set()

    for field in ("email", "company", "name", "product"):
        best_header = None
        best_score = -1
        best_reason = "未找到可信候选"

        for header in headers:
            if header in used_headers:
                continue
            score, reason = _score_header(field, header, sample_rows)
            if score > best_score:
                best_score = score
                best_header = header
                best_reason = reason

        if best_score >= 30 and best_header:
            result[field] = best_header
            used_headers.add(best_header)
            details[field] = {
                "header": best_header,
                "confidence": _confidence_label(best_score),
                "reason": best_reason,
            }
        else:
            result[field] = None
            details[field] = {
                "header": "",
                "confidence": "none",
                "reason": best_reason,
            }

    return result, details


def _score_header(field: str, header: str, rows: list[dict[str, str]]) -> tuple[int, str]:
    normalized = _normalize_key(header)
    aliases = [_normalize_key(alias) for alias in FIELD_CONFIG[field]["aliases"]]
    reasons = []
    score = 0

    if normalized in aliases:
        score += 90
        reasons.append("表头完全匹配")
    elif any(alias in normalized for alias in aliases):
        score += 60
        reasons.append("表头包含关键别名")

    values = [str(row.get(header, "")).strip() for row in rows if str(row.get(header, "")).strip()]
    if values:
        value_score, value_reason = _score_values(field, values)
        score += value_score
        if value_reason:
            reasons.append(value_reason)

    if normalized.endswith("id") and field in {"name", "company"}:
        score -= 30
        reasons.append("表头更像 ID 字段")
    if "phone" in normalized or "tel" in normalized:
        score -= 40
        reasons.append("表头更像电话字段")
    if "country" in normalized or "region" in normalized:
        score -= 20
        reasons.append("表头更像地区字段")
    if any(token in normalized for token in LINK_LIKE_HEADER_TOKENS):
        score -= 50
        reasons.append("表头更像链接或社媒字段")

    reason = "；".join(reasons) if reasons else "无明显特征"
    return score, reason


def _score_values(field: str, values: list[str]) -> tuple[int, str]:
    sample = values[:15]
    total = len(sample)
    if not total:
        return 0, ""

    if field == "email":
        exact_matches = sum(1 for value in sample if EMAIL_PATTERN.match(_clean_text(value)))
        extracted_matches = sum(1 for value in sample if extract_email_address(value))
        if exact_matches == total:
            return 80, "样例值全部符合邮箱格式"
        if extracted_matches == total:
            return 72, "样例值可稳定提取邮箱地址"
        if extracted_matches >= max(2, total // 2):
            return 45, "样例值大部分符合邮箱格式"
        return -20, "样例值不符合邮箱格式"

    if field == "company":
        non_url_values = [value for value in sample if not value.lower().startswith("http")]
        if not non_url_values:
            return -15, "样例值更像链接地址"
        company_like = sum(1 for value in non_url_values if COMPANY_HINT_PATTERN.search(value))
        avg_len = sum(len(value) for value in non_url_values) / len(non_url_values)
        if company_like >= max(2, total // 3):
            return 35, "样例值像公司名称"
        if avg_len >= 10:
            return 12, "样例值长度偏长，可能是公司名"
        return 0, ""

    if field == "name":
        non_url_values = [value for value in sample if not value.lower().startswith("http")]
        if not non_url_values:
            return -15, "样例值更像链接地址"
        person_like = sum(1 for value in non_url_values if PERSON_NAME_PATTERN.match(value))
        short_values = sum(1 for value in non_url_values if len(value.split()) <= 3 and len(value) <= 24)
        if person_like >= max(2, total // 3):
            return 30, "样例值像人名"
        if short_values >= max(2, total // 2):
            return 10, "样例值较短，可能是联系人"
        return 0, ""

    if field == "product":
        keyword_hits = sum(
            1
            for value in sample
            if any(token in value.lower() for token in ("window", "door", "glass", "aluminum", "product"))
        )
        comma_like = sum(1 for value in sample if "," in value or "/" in value)
        if keyword_hits >= max(2, total // 3):
            return 28, "样例值像产品或品类"
        if comma_like >= max(2, total // 3):
            return 12, "样例值包含多产品描述"
        return 0, ""

    return 0, ""


def _load_rows(path: Path, suffix: str) -> list[dict[str, str]]:
    if suffix == ".csv":
        return _read_csv_without_pandas(path)

    if pd is not None:
        try:
            table_rows = _read_excel_with_pandas(path)
            return _tabular_rows_to_dicts(table_rows)
        except Exception as exc:
            raise ImporterError(f"读取文件失败：{exc}") from exc

    raise ImporterError("当前环境缺少 pandas/openpyxl，暂时只能导入 CSV。")


def _read_excel_with_pandas(path: Path) -> list[list[str]]:
    frame = pd.read_excel(path, dtype=str, header=None)
    return frame.fillna("").values.tolist()


def _read_csv_without_pandas(path: Path) -> list[dict[str, str]]:
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.reader(handle)
                rows = [[_clean_text(value) for value in row] for row in reader]
                rows = _tabular_rows_to_dicts(rows)
                if not rows:
                    raise ImporterError("CSV 中没有可用的数据行。")
                return rows
        except Exception as exc:
            last_error = exc
    raise ImporterError(f"读取 CSV 失败：{last_error}") from last_error


def _tabular_rows_to_dicts(table_rows: list[list[str]]) -> list[dict[str, str]]:
    cleaned_rows = [
        [_clean_text(value) for value in row]
        for row in table_rows
        if any(_clean_text(value) for value in row)
    ]
    if not cleaned_rows:
        return []

    header_index = _detect_header_row(cleaned_rows)
    headers = _dedupe_headers(cleaned_rows[header_index])
    data_rows = cleaned_rows[header_index + 1 :]

    normalized_rows = []
    for row in data_rows:
        padded = list(row) + [""] * max(0, len(headers) - len(row))
        record = {
            headers[index]: padded[index] if index < len(padded) else ""
            for index in range(len(headers))
        }
        if _row_has_content(record):
            normalized_rows.append(_clean_row(record))
    return normalized_rows


def _detect_header_row(rows: list[list[str]]) -> int:
    best_index = 0
    best_score = float("-inf")
    header_hints = _build_header_hints()

    for index, row in enumerate(rows[:8]):
        non_empty = [value for value in row if value]
        if not non_empty:
            continue

        normalized = [_normalize_key(value) for value in non_empty]
        hint_hits = sum(1 for value in normalized if value in header_hints)
        title_like = len(non_empty) == 1 and any(token in non_empty[0] for token in ("全部结果", "导出", "报表"))
        data_like = sum(
            1
            for value in non_empty
            if extract_email_address(value)
            or value.lower().startswith("http")
            or re.search(r"\d{4}-\d{2}-\d{2}", value)
        )

        score = 0
        score += hint_hits * 120
        score += len(non_empty) * 4
        score += len(set(normalized)) * 2
        score -= data_like * 25
        if len(non_empty) == 1:
            score -= 80
        if title_like:
            score -= 160

        if score > best_score:
            best_score = score
            best_index = index

    return best_index


def _dedupe_headers(headers: list[str]) -> list[str]:
    result = []
    seen = {}
    for index, raw_header in enumerate(headers, start=1):
        header = raw_header or f"Column{index}"
        counter = seen.get(header, 0)
        seen[header] = counter + 1
        result.append(header if counter == 0 else f"{header}_{counter + 1}")
    return result


def _clean_row(row: dict) -> dict[str, str]:
    cleaned = {}
    for key, value in row.items():
        normalized_key = str(key).strip()
        cleaned[normalized_key] = "" if value is None else str(value).strip()
    return cleaned


def _row_has_content(row: dict) -> bool:
    return any(str(value).strip() for value in row.values() if value is not None)


def _normalize_key(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", _clean_text(value).lower())


def _clean_text(value: str) -> str:
    return (
        str(value)
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\xa0", " ")
        .strip()
    )


def extract_email_address(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""

    if text.lower().startswith("mailto:"):
        text = text[7:].strip()

    matches = EMAIL_CANDIDATE_PATTERN.findall(text)
    if not matches:
        return ""

    candidate = matches[0].strip(" <>\"'(),;")
    return candidate.lower() if EMAIL_PATTERN.match(candidate) else ""


def _build_header_hints() -> set[str]:
    hints = set(GENERIC_HEADER_ALIASES)
    for config in FIELD_CONFIG.values():
        hints.update(config["aliases"])
    return {_normalize_key(item) for item in hints if item}


def _confidence_label(score: int) -> str:
    if score >= 120:
        return "high"
    if score >= 70:
        return "medium"
    return "low"
