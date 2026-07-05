from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from urllib import error, request

from app.services.importer import LeadDataset
from app.services.template import build_context, render_template, split_subject_and_body


class AIWriterError(Exception):
    pass


@dataclass
class AISettings:
    mode: str = "local"
    endpoint: str = ""
    model: str = ""
    api_key: str = ""
    tone: str = "professional"
    offer_summary: str = ""
    call_to_action: str = "If useful, I can share a short catalog and pricing sample."
    signature_name: str = "GlobalReach PRO"

    @classmethod
    def from_state(cls, state: dict[str, str]) -> "AISettings":
        return cls(
            mode=state.get("ai_mode", "local") or "local",
            endpoint=state.get("ai_endpoint", ""),
            model=state.get("ai_model", ""),
            api_key=state.get("ai_api_key", ""),
            tone=state.get("ai_tone", "professional") or "professional",
            offer_summary=state.get("ai_offer_summary", ""),
            call_to_action=state.get("ai_call_to_action", "") or "If useful, I can share a short catalog and pricing sample.",
            signature_name=state.get("ai_signature_name", "") or "GlobalReach PRO",
        )

    def to_state(self) -> dict[str, str]:
        return {
            "ai_mode": self.mode,
            "ai_endpoint": self.endpoint,
            "ai_model": self.model,
            "ai_api_key": self.api_key,
            "ai_tone": self.tone,
            "ai_offer_summary": self.offer_summary,
            "ai_call_to_action": self.call_to_action,
            "ai_signature_name": self.signature_name,
        }


@dataclass
class EmailDraft:
    subject: str
    body: str
    source: str
    issues: list[str]

    def as_text(self) -> str:
        return f"Subject: {self.subject}\n\n{self.body}".strip()


def generate_email_draft(
    template: str,
    row: dict[str, str],
    dataset: LeadDataset,
    row_index: int,
    settings: AISettings,
) -> EmailDraft:
    rendered, issues = render_template(template, row, dataset)
    subject, body = split_subject_and_body(rendered)
    context = build_context(row, dataset)

    if settings.mode == "openai" and settings.api_key and settings.model and settings.endpoint:
        try:
            return _generate_openai_compatible(subject, body, context, row_index, settings, issues)
        except AIWriterError as exc:
            issues = issues + [f"AI 接口失败，已切回本地差异化：{exc}"]
    elif settings.mode == "gemini" and settings.api_key and settings.model:
        try:
            return _generate_gemini(subject, body, context, row_index, settings, issues)
        except AIWriterError as exc:
            issues = issues + [f"Gemini 接口失败，已切回本地差异化：{exc}"]

    return _generate_local_variation(subject, body, context, row_index, settings, issues)


def generate_subject_samples(
    template: str,
    dataset: LeadDataset,
    settings: AISettings,
    count: int = 5,
) -> list[str]:
    samples = []
    for index, row in enumerate(dataset.rows[:count]):
        draft = generate_email_draft(template, row, dataset, index, settings)
        samples.append(f"{index + 1}. {draft.subject}")
    return samples


def _generate_local_variation(
    subject: str,
    body: str,
    context: dict[str, str],
    row_index: int,
    settings: AISettings,
    issues: list[str],
) -> EmailDraft:
    company = context.get("Company", "your team")
    name = context.get("Name", "there")
    product = context.get("Product", "your current product line")
    email = context.get("Email", "")
    offer_summary = settings.offer_summary.strip() or _derive_offer_summary(body)
    tone = settings.tone.strip() or "professional"

    seed = int(hashlib.sha256(f"{email}|{company}|{row_index}".encode()).hexdigest()[:8], 16)
    subject_templates = [
        f"{company}: a quick sourcing idea for {product}",
        f"Question about {company}'s {product} sourcing",
        f"A practical supply option for {company}",
        f"{company} and a possible fit on {product}",
        f"Improving consistency for {company}'s supply plan",
    ]
    opener_templates = [
        f"I noticed {company} may be reviewing options around {product}.",
        f"I'm reaching out because {company} looks relevant to our work in {product}.",
        f"I thought {company} might be a strong fit for a more reliable {product} supply conversation.",
        f"Your team at {company} seems aligned with the kind of {product} projects we support.",
    ]
    value_templates = [
        f"We focus on stable delivery, cleaner communication, and practical support around {offer_summary}.",
        f"Our work usually helps teams reduce sourcing friction while keeping response times tighter on {offer_summary}.",
        f"The main reason I am writing is that we support buyers who need more predictable execution on {offer_summary}.",
        f"We typically help importers and distributors who want a more dependable process around {offer_summary}.",
    ]
    cta_templates = [
        settings.call_to_action.strip() or "If useful, I can share a short catalog and pricing sample.",
        "If this is relevant, I can send a short catalog and one sample quotation.",
        "If helpful, I can send a concise product sheet and a sample price list for review.",
        "If you are open to it, I can send a short overview and a few matching product options.",
    ]
    closings = [
        f"Best regards,\n{settings.signature_name}",
        f"Regards,\n{settings.signature_name}",
        f"Thank you,\n{settings.signature_name}",
    ]

    selected_subject = subject_templates[seed % len(subject_templates)]
    if subject and company.lower() not in subject.lower():
        selected_subject = f"{selected_subject} | {subject}"

    greeting = f"Hi {name},"
    opener = opener_templates[seed % len(opener_templates)]
    value_line = value_templates[(seed // 3) % len(value_templates)]
    cta_line = cta_templates[(seed // 5) % len(cta_templates)]
    closing = closings[(seed // 7) % len(closings)]

    body_paragraphs = [
        greeting,
        opener,
        _tone_adjust(value_line, tone),
        _tone_adjust(_compress_base_body(body), tone),
        _tone_adjust(cta_line, tone),
        closing,
    ]
    final_body = "\n\n".join(part for part in body_paragraphs if part.strip())
    return EmailDraft(subject=selected_subject, body=final_body, source="local-variation", issues=issues)


def _generate_openai_compatible(
    subject: str,
    body: str,
    context: dict[str, str],
    row_index: int,
    settings: AISettings,
    issues: list[str],
) -> EmailDraft:
    prompt = _build_prompt(subject, body, context, row_index, settings)
    payload = {
        "model": settings.model,
        "temperature": 0.9,
        "messages": [
            {
                "role": "system",
                "content": "You write concise B2B outreach emails. Return JSON with keys subject and body.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }
    response_json = _post_json(settings.endpoint, payload, headers)
    try:
        content = response_json["choices"][0]["message"]["content"]
    except Exception as exc:
        raise AIWriterError(f"返回内容无法解析：{exc}") from exc
    return _draft_from_response_content(content, issues, "openai-compatible")


def _generate_gemini(
    subject: str,
    body: str,
    context: dict[str, str],
    row_index: int,
    settings: AISettings,
    issues: list[str],
) -> EmailDraft:
    prompt = _build_prompt(subject, body, context, row_index, settings)
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model}:generateContent"
        f"?key={settings.api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9},
    }
    headers = {"Content-Type": "application/json"}
    response_json = _post_json(endpoint, payload, headers)
    try:
        content = response_json["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:
        raise AIWriterError(f"Gemini 返回内容无法解析：{exc}") from exc
    return _draft_from_response_content(content, issues, "gemini")


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise AIWriterError(f"HTTP {exc.code}") from exc
    except Exception as exc:
        raise AIWriterError(str(exc)) from exc


def _draft_from_response_content(content: str, issues: list[str], source: str) -> EmailDraft:
    try:
        parsed = json.loads(content)
        subject = parsed.get("subject", "").strip()
        body = parsed.get("body", "").strip()
        if subject and body:
            return EmailDraft(subject=subject, body=body, source=source, issues=issues)
    except Exception:
        pass

    subject, body = split_subject_and_body(content)
    if not subject or not body:
        raise AIWriterError("AI 未返回有效的 subject/body")
    return EmailDraft(subject=subject, body=body, source=source, issues=issues)


def _build_prompt(
    subject: str,
    body: str,
    context: dict[str, str],
    row_index: int,
    settings: AISettings,
) -> str:
    return (
        "Write one concise B2B outreach email in English.\n"
        "Requirements:\n"
        "- Subject must be different from a generic template and specific to this lead.\n"
        "- Body must be slightly different in structure and wording from other leads.\n"
        "- Keep it professional, not spammy, 80-140 words.\n"
        "- Return JSON only: {\"subject\":\"...\",\"body\":\"...\"}\n\n"
        f"Lead index: {row_index + 1}\n"
        f"Name: {context.get('Name', '')}\n"
        f"Company: {context.get('Company', '')}\n"
        f"Product: {context.get('Product', '')}\n"
        f"Offer summary: {settings.offer_summary}\n"
        f"Tone: {settings.tone}\n"
        f"CTA: {settings.call_to_action}\n"
        f"Base subject: {subject}\n"
        f"Base body: {body}\n"
    )


def _derive_offer_summary(body: str) -> str:
    cleaned = " ".join(line.strip() for line in body.splitlines() if line.strip())
    return cleaned[:140] if cleaned else "reliable supply support"


def _compress_base_body(body: str) -> str:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]
    return lines[min(1, len(lines) - 1)]


def _tone_adjust(text: str, tone: str) -> str:
    if not text.strip():
        return text
    if tone == "direct":
        return text.replace("If useful, I can", "I can")
    if tone == "warm":
        return text.replace("I am writing", "I wanted to reach out")
    return text
