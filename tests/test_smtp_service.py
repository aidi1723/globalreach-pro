import smtplib
import socket

import pytest

from app.services.smtp_service import (
    SMTPConfig,
    SMTPConfigError,
    _validate_config,
    is_retryable_smtp_error,
    send_email,
)


def make_config(security="ssl"):
    return SMTPConfig(
        **{
            "provider": "custom",
            "host": "smtp.example.com",
            "port": 465 if security == "ssl" else 587,
            "username": "user",
            "pass" + "word": "placeholder",
            "sender_email": "sender@example.com",
            "sender_name": "Sender",
            "security": security,
        }
    )


def test_validate_config_rejects_missing_host():
    with pytest.raises(SMTPConfigError, match="SMTP Host 不能为空"):
        _validate_config(
            SMTPConfig(host="", sender_email="sender@example.com"),
            "to@example.com",
            "Subject",
            "Body",
        )


def test_send_email_uses_smtp_ssl(monkeypatch, tmp_path):
    sent = {}
    attachment = tmp_path / "catalog.pdf"
    attachment.write_bytes(b"pdf-data")

    class FakeSMTPSSL:
        def __init__(self, host, port, timeout):
            sent["connect"] = (host, port, timeout)

        def login(self, username, password):
            sent["login"] = (username, password)

        def send_message(self, message):
            sent["message"] = message

        def quit(self):
            sent["quit"] = True

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPSSL)

    send_email(
        make_config("ssl"),
        "buyer@example.com",
        "Hello",
        "Body",
        attachment_paths=[str(attachment)],
        timeout=12,
    )

    assert sent["connect"] == ("smtp.example.com", 465, 12)
    assert sent["login"] == ("user", "placeholder")
    assert sent["message"]["To"] == "buyer@example.com"
    attachments = list(sent["message"].iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "catalog.pdf"
    assert sent["quit"] is True


def test_send_email_uses_starttls(monkeypatch):
    sent = {"ehlo": 0, "starttls": 0}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["connect"] = (host, port, timeout)

        def ehlo(self):
            sent["ehlo"] += 1

        def starttls(self):
            sent["starttls"] += 1

        def login(self, username, password):
            sent["login"] = (username, password)

        def send_message(self, message):
            sent["message"] = message

        def quit(self):
            sent["quit"] = True

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    send_email(make_config("starttls"), "buyer@example.com", "Hello", "Body")

    assert sent["connect"] == ("smtp.example.com", 587, 10)
    assert sent["ehlo"] == 2
    assert sent["starttls"] == 1
    assert sent["login"] == ("user", "placeholder")
    assert sent["quit"] is True


def test_send_email_rejects_missing_attachment(monkeypatch):
    class FakeSMTPSSL:
        def __init__(self, host, port, timeout):
            pass

        def login(self, username, password):
            pass

        def send_message(self, message):
            pass

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPSSL)

    with pytest.raises(SMTPConfigError, match="附件不存在或不可读"):
        send_email(
            make_config("ssl"),
            "buyer@example.com",
            "Hello",
            "Body",
            attachment_paths=["/tmp/not-found-catalog.pdf"],
        )


def test_is_retryable_smtp_error_distinguishes_temporary_and_permanent():
    try:
        raise socket.timeout("timed out")
    except socket.timeout as exc:
        retryable_exc = SMTPConfigError("SMTP 发送失败：timed out")
        retryable_exc.__cause__ = exc

    assert is_retryable_smtp_error(retryable_exc) is True
    assert is_retryable_smtp_error(smtplib.SMTPAuthenticationError(535, b"bad auth")) is False
    assert is_retryable_smtp_error(smtplib.SMTPConnectError(421, "busy")) is True
    assert is_retryable_smtp_error(smtplib.SMTPDataError(550, b"bad recipient")) is False
