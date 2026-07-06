import json
from pathlib import Path

from app.constants import (
    AI_STATE_KEYS,
    BATCH_STATE_KEYS,
    DEFAULT_BATCH_DELAY_SECONDS,
    DEFAULT_BATCH_MAX_RETRIES,
    DEFAULT_TEMPLATE,
    GOVERNANCE_STATE_KEYS,
    SMTP_STATE_KEYS,
)
from app.services.ai_writer import AISettings
from app.services.smtp_service import SMTPConfig, preset_label_from_provider


def _set_entry_value(app, entry, value: str):
    if hasattr(app, "_set_entry_value"):
        app._set_entry_value(entry, value)
        return
    entry.delete(0, "end")
    entry.insert(0, value)


def _set_textbox_value(textbox, value: str):
    textbox.delete("0.0", "end")
    textbox.insert("0.0", value)


def load_persisted_state(app):
    template = app.storage.get_state("template_draft") or DEFAULT_TEMPLATE
    _set_textbox_value(app.strategy_box, template)
    app.load_recent_logs()
    app.load_watch_state()
    app.load_dedupe_state()
    load_batch_state(app)
    load_governance_state(app)
    app.load_ai_state()
    app.load_smtp_state()
    app.refresh_task_results()
    app.refresh_template_metadata()

    last_file = app.storage.get_state("last_file")
    if last_file and Path(last_file).exists():
        app.load_dataset(last_file, announce=False)
        app.add_log(f"已恢复上次载入文件：{Path(last_file).name}")
    else:
        app.add_log("工作台初始化完成，等待名单载入。")


def load_watch_state(app):
    folder = app.storage.get_state("watch_folder_path") or ""
    app.watch_folder_var.set(folder)
    if folder:
        app.watch_status_var.set(f"监听状态：已配置 {folder}")
        app.after(200, app.start_folder_watch)


def load_dedupe_state(app):
    policy = app.storage.get_state("dedupe_policy") or "review"
    app.dedupe_policy_var.set(policy)


def save_dedupe_policy(app):
    app.storage.set_state("dedupe_policy", app.dedupe_policy_var.get().strip() or "review")
    app.refresh_duplicate_history()


def load_batch_state(app):
    state = {key: app.storage.get_state(key) or "" for key in BATCH_STATE_KEYS}
    app._set_entry_value(
        app.batch_delay_entry,
        state.get("batch_delay_seconds", "") or DEFAULT_BATCH_DELAY_SECONDS,
    )
    app._set_entry_value(
        app.batch_retries_entry,
        state.get("batch_max_retries", "") or DEFAULT_BATCH_MAX_RETRIES,
    )


def load_governance_state(app):
    state = {key: app.storage.get_state(key) or "" for key in GOVERNANCE_STATE_KEYS}
    _set_entry_value(
        app,
        app.daily_limit_entry,
        state.get("daily_limit_per_account", "") or "0",
    )
    _set_entry_value(
        app,
        app.hourly_limit_entry,
        state.get("hourly_limit_per_account", "") or "0",
    )


def load_ai_state(app):
    state = {key: app.storage.get_state(key) or "" for key in AI_STATE_KEYS}
    settings = AISettings.from_state(state)
    app.ai_mode_var.set(settings.mode)
    app.ai_tone_var.set(settings.tone)
    _set_entry_value(app, app.ai_model_entry, settings.model)
    _set_entry_value(app, app.ai_endpoint_entry, settings.endpoint)
    _set_entry_value(app, app.ai_api_key_entry, settings.api_key)
    _set_entry_value(app, app.ai_offer_entry, settings.offer_summary)
    _set_entry_value(app, app.ai_cta_entry, settings.call_to_action)
    _set_entry_value(app, app.ai_signature_entry, settings.signature_name)


def save_ai_settings(app, announce=True):
    settings = app.collect_ai_settings()
    for key, value in settings.to_state().items():
        app.storage.set_state(key, value)
    if announce:
        app.add_log("AI 写信设置已保存。")
    app.refresh_subject_samples()


def load_smtp_state(app):
    state = {key: app.storage.get_state(key) or "" for key in SMTP_STATE_KEYS}
    config = SMTPConfig.from_state(state)
    app.smtp_preset_var.set(preset_label_from_provider(config.provider))
    app.populate_account_pool_menu()
    _set_entry_value(app, app.smtp_host_entry, config.host)
    _set_entry_value(app, app.smtp_port_entry, str(config.port))
    _set_entry_value(app, app.smtp_username_entry, config.username)
    _set_entry_value(app, app.smtp_password_entry, config.password)
    _set_entry_value(app, app.smtp_sender_name_entry, config.sender_name)
    _set_entry_value(app, app.smtp_sender_email_entry, config.sender_email)
    _set_entry_value(app, app.smtp_dkim_selector_entry, config.dkim_selector)
    _set_entry_value(app, app.smtp_test_recipient_entry, state.get("smtp_test_recipient", ""))
    _set_entry_value(app, app.smtp_subject_entry, state.get("smtp_test_subject", ""))
    app.smtp_security_var.set(config.security)
    app.smtp_attachment_paths = _load_attachment_paths(state.get("smtp_attachment_paths", ""))
    _set_textbox_value(app.smtp_body_box, "先生成预览，再把正文同步到 SMTP 测试区域。\n")
    _set_textbox_value(app.domain_auth_box, "这里会显示 SPF / DKIM / DMARC 预检结果。\n")
    app.refresh_attachment_summary()
    app.toggle_advanced_smtp_fields()


def save_smtp_config(app, announce=True):
    config = app.collect_smtp_config()
    for key, value in config.to_state().items():
        app.storage.set_state(key, value)
    app.storage.set_state("smtp_test_recipient", app.smtp_test_recipient_entry.get().strip())
    app.storage.set_state("smtp_test_subject", app.smtp_subject_entry.get().strip())
    app.storage.set_state(
        "smtp_attachment_paths",
        json.dumps(app.smtp_attachment_paths, ensure_ascii=False),
    )
    if announce:
        app.add_log("SMTP 配置已保存。")


def _load_attachment_paths(raw_value: str) -> list[str]:
    if not raw_value:
        return []
    try:
        payload = json.loads(raw_value)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload if str(item).strip()]
