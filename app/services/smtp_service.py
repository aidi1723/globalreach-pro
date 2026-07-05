from __future__ import annotations

import mimetypes
import smtplib
import socket
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path


class SMTPConfigError(Exception):
    pass


SMTP_PRESETS = {
    "自定义": {"provider": "custom", "host": "", "port": 465, "security": "ssl"},
    "Gmail / Google Workspace": {
        "provider": "gmail",
        "host": "smtp.gmail.com",
        "port": 465,
        "security": "ssl",
    },
    "Microsoft 365 / Outlook": {
        "provider": "office365",
        "host": "smtp.office365.com",
        "port": 587,
        "security": "starttls",
    },
    "阿里邮箱": {
        "provider": "aliyun",
        "host": "smtp.aliyun.com",
        "port": 465,
        "security": "ssl",
    },
    "QQ 邮箱": {
        "provider": "qq_mail",
        "host": "smtp.qq.com",
        "port": 465,
        "security": "ssl",
    },
    "腾讯企业邮箱": {
        "provider": "qq_exmail",
        "host": "smtp.exmail.qq.com",
        "port": 465,
        "security": "ssl",
    },
}


@dataclass
class SMTPConfig:
    provider: str = "custom"
    host: str = ""
    port: int = 465
    username: str = ""
    password: str = ""
    sender_email: str = ""
    sender_name: str = "GlobalReach PRO"
    security: str = "ssl"
    dkim_selector: str = ""

    @classmethod
    def from_state(cls, state: dict[str, str]) -> "SMTPConfig":
        port_value = state.get("smtp_port", "").strip()
        try:
            port = int(port_value) if port_value else 465
        except ValueError:
            port = 465

        return cls(
            provider=state.get("smtp_provider", "custom") or "custom",
            host=state.get("smtp_host", ""),
            port=port,
            username=state.get("smtp_username", ""),
            password=state.get("smtp_password", ""),
            sender_email=state.get("smtp_sender_email", ""),
            sender_name=state.get("smtp_sender_name", "GlobalReach PRO") or "GlobalReach PRO",
            security=state.get("smtp_security", "ssl") or "ssl",
            dkim_selector=state.get("smtp_dkim_selector", ""),
        )

    def to_state(self) -> dict[str, str]:
        return {
            "smtp_provider": self.provider,
            "smtp_host": self.host,
            "smtp_port": str(self.port),
            "smtp_username": self.username,
            "smtp_password": self.password,
            "smtp_sender_email": self.sender_email,
            "smtp_sender_name": self.sender_name,
            "smtp_security": self.security,
            "smtp_dkim_selector": self.dkim_selector,
        }


def send_email(
    config: SMTPConfig,
    recipient_email: str,
    subject: str,
    body: str,
    attachment_paths: list[str] | None = None,
    timeout: int = 10,
) -> None:
    _validate_config(config, recipient_email, subject, body)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = (
        f"{config.sender_name} <{config.sender_email}>"
        if config.sender_name
        else config.sender_email
    )
    message["To"] = recipient_email
    message.set_content(body)
    _attach_files(message, attachment_paths or [])

    client = None
    try:
        if config.security == "ssl":
            client = smtplib.SMTP_SSL(config.host, config.port, timeout=timeout)
        else:
            client = smtplib.SMTP(config.host, config.port, timeout=timeout)
            client.ehlo()
            if config.security == "starttls":
                client.starttls()
                client.ehlo()

        if config.username:
            client.login(config.username, config.password)
        client.send_message(message)
    except (smtplib.SMTPException, OSError, socket.error) as exc:
        raise SMTPConfigError(f"SMTP 发送失败：{exc}") from exc
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                pass


def test_smtp_delivery(
    config: SMTPConfig,
    recipient_email: str,
    subject: str,
    body: str,
    attachment_paths: list[str] | None = None,
    timeout: int = 10,
) -> str:
    try:
        send_email(
            config,
            recipient_email,
            subject,
            body,
            attachment_paths=attachment_paths,
            timeout=timeout,
        )
    except SMTPConfigError as exc:
        message = str(exc)
        if message.startswith("SMTP 发送失败："):
            message = message.replace("SMTP 发送失败：", "SMTP 测试失败：", 1)
        raise SMTPConfigError(message) from exc.__cause__
    attachment_note = f"（含 {len(attachment_paths or [])} 个附件）" if attachment_paths else ""
    return f"SMTP 测试成功：已向 {recipient_email} 发送测试邮件{attachment_note}。"


def _validate_config(config: SMTPConfig, recipient_email: str, subject: str, body: str):
    if not config.host.strip():
        raise SMTPConfigError("SMTP Host 不能为空。")
    if not config.sender_email.strip():
        raise SMTPConfigError("发件邮箱不能为空。")
    if config.port <= 0:
        raise SMTPConfigError("SMTP Port 必须是正整数。")
    if config.username and not config.password:
        raise SMTPConfigError("已填写用户名时，密码不能为空。")
    if not recipient_email.strip():
        raise SMTPConfigError("测试收件邮箱不能为空。")
    if not subject.strip():
        raise SMTPConfigError("测试主题不能为空。")
    if not body.strip():
        raise SMTPConfigError("测试正文不能为空。")


def _attach_files(message: EmailMessage, attachment_paths: list[str]) -> None:
    for raw_path in attachment_paths:
        path = Path(str(raw_path)).expanduser()
        if not path.exists() or not path.is_file():
            raise SMTPConfigError(f"附件不存在或不可读：{path}")

        mime_type, _encoding = mimetypes.guess_type(path.name)
        maintype, subtype = (mime_type.split("/", 1) if mime_type else ("application", "octet-stream"))
        try:
            payload = path.read_bytes()
        except Exception as exc:
            raise SMTPConfigError(f"读取附件失败：{path.name} ({exc})") from exc

        message.add_attachment(
            payload,
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )


def is_retryable_smtp_error(exc: Exception) -> bool:
    root = exc.__cause__ if isinstance(exc, SMTPConfigError) and exc.__cause__ else exc

    if isinstance(root, (socket.timeout, TimeoutError, smtplib.SMTPServerDisconnected)):
        return True
    if isinstance(root, smtplib.SMTPConnectError):
        return True
    if isinstance(root, smtplib.SMTPAuthenticationError):
        return False
    if isinstance(root, smtplib.SMTPRecipientsRefused):
        return False
    if isinstance(root, smtplib.SMTPResponseException):
        try:
            return 400 <= int(root.smtp_code) < 500
        except Exception:
            return False
    if isinstance(root, OSError):
        return True
    return False


def get_preset_names() -> list[str]:
    return list(SMTP_PRESETS.keys())


def get_preset_by_name(name: str) -> dict[str, str | int]:
    return SMTP_PRESETS.get(name, SMTP_PRESETS["自定义"])


def preset_label_from_provider(provider: str) -> str:
    for label, preset in SMTP_PRESETS.items():
        if preset["provider"] == provider:
            return label
    return "自定义"


def infer_preset_from_email(sender_email: str) -> str:
    email = sender_email.strip().lower()
    if email.endswith("@gmail.com") or email.endswith("@googlemail.com"):
        return "Gmail / Google Workspace"
    if email.endswith("@outlook.com") or email.endswith("@hotmail.com") or email.endswith("@live.com"):
        return "Microsoft 365 / Outlook"
    if email.endswith("@aliyun.com"):
        return "阿里邮箱"
    if email.endswith("@qq.com"):
        return "QQ 邮箱"
    return "自定义"


def build_config_from_inputs(
    preset_name: str,
    sender_email: str,
    password: str,
    username: str = "",
    sender_name: str = "",
    host: str = "",
    port: int | None = None,
    security: str = "",
    dkim_selector: str = "",
) -> SMTPConfig:
    preset = get_preset_by_name(preset_name)
    resolved_host = host.strip() or str(preset["host"])
    resolved_port = port if port is not None else int(preset["port"])
    resolved_security = security.strip() or str(preset["security"])
    resolved_username = username.strip() or sender_email.strip()
    resolved_sender_name = sender_name.strip() or _derive_sender_name(sender_email)

    return SMTPConfig(
        provider=str(preset["provider"]),
        host=resolved_host,
        port=resolved_port,
        username=resolved_username,
        password=password,
        sender_email=sender_email.strip(),
        sender_name=resolved_sender_name,
        security=resolved_security,
        dkim_selector=dkim_selector.strip(),
    )


def summarize_config(config: SMTPConfig) -> str:
    return (
        f"Provider={config.provider}, Host={config.host}, Port={config.port}, "
        f"Security={config.security}, Username={config.username}, Sender={config.sender_email}"
    )


def _derive_sender_name(sender_email: str) -> str:
    local_part = sender_email.strip().split("@", 1)[0] if "@" in sender_email else ""
    normalized = local_part.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    return normalized.title() if normalized else "GlobalReach PRO"
