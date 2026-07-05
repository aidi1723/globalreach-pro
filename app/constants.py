DEFAULT_TEMPLATE = (
    "Subject: Quality Aluminum Windows for {Company}\n\n"
    "Hi {Name},\n\n"
    "I noticed {Company} may be expanding its product mix in {Product}. "
    "We help distributors source reliable aluminum window systems with stable lead times.\n\n"
    "If useful, I can share a short catalog and a pricing sample.\n\n"
    "Best regards,\n"
    "GlobalReach PRO"
)

UNMAPPED_OPTION = "未映射"

FIELD_LABELS = {
    "email": "邮箱字段",
    "company": "公司字段",
    "name": "联系人字段",
    "product": "产品字段",
}

SMTP_STATE_KEYS = [
    "smtp_provider",
    "smtp_host",
    "smtp_port",
    "smtp_username",
    "smtp_password",
    "smtp_sender_email",
    "smtp_sender_name",
    "smtp_security",
    "smtp_dkim_selector",
    "smtp_test_recipient",
    "smtp_test_subject",
    "smtp_attachment_paths",
]

ACCOUNT_IMPORT_HINT = (
    "批量导入格式：每行一个账号，支持\n"
    "服务商,邮箱,授权码[,发件人名称][,DKIM selector]\n"
    "例如：Gmail / Google Workspace,sales@example.com,app-password,Sales Team,selector1"
)

AI_STATE_KEYS = [
    "ai_mode",
    "ai_endpoint",
    "ai_model",
    "ai_api_key",
    "ai_tone",
    "ai_offer_summary",
    "ai_call_to_action",
    "ai_signature_name",
]

LICENSE_STATE_KEYS = [
    "license_provider",
    "license_api_base_url",
    "license_product_code",
    "license_activation_token",
    "license_status",
    "license_expires_at",
    "license_last_error",
]

WATCH_STATE_KEYS = [
    "watch_folder_path",
]

DEDUPE_STATE_KEYS = [
    "dedupe_policy",
]

BATCH_STATE_KEYS = [
    "batch_delay_seconds",
    "batch_max_retries",
]

DEFAULT_BATCH_DELAY_SECONDS = "1"
DEFAULT_BATCH_MAX_RETRIES = "1"
