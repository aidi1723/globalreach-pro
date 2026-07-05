import threading
from pathlib import Path
from tkinter import filedialog, messagebox

from app.constants import ACCOUNT_IMPORT_HINT
from app.services.domain_auth import (
    build_email_auth_report,
    extract_domain_from_email,
    format_email_auth_report,
)
from app.services.smtp_service import (
    SMTPConfig,
    SMTPConfigError,
    build_config_from_inputs,
    infer_preset_from_email,
    preset_label_from_provider,
    summarize_config,
    test_smtp_delivery,
)


def populate_account_pool_menu(app):
    accounts = app.storage.list_smtp_accounts()
    labels = [account["label"] for account in accounts] or ["未保存账号"]
    app.smtp_account_menu.configure(values=labels)
    if app.smtp_account_var.get() not in labels:
        app.smtp_account_var.set(labels[0])


def prepare_and_save_smtp_config(app):
    try:
        sender_email = app.smtp_sender_email_entry.get().strip()
        if sender_email and app.smtp_preset_var.get().strip() == "自定义":
            app.smtp_preset_var.set(infer_preset_from_email(sender_email))
        app.apply_selected_preset(log_action=False)
        if not app.smtp_test_recipient_entry.get().strip() and sender_email:
            app._set_entry_value(app.smtp_test_recipient_entry, sender_email)
        if not app.smtp_subject_entry.get().strip():
            app._set_entry_value(app.smtp_subject_entry, "SMTP Configuration Test")
        app.save_smtp_config()
        app.set_smtp_status("配置已保存，可直接点击“预检后再测试”。")
    except SMTPConfigError as exc:
        messagebox.showerror("配置失败", str(exc))


def collect_smtp_config(app) -> SMTPConfig:
    port_value = app.smtp_port_entry.get().strip()
    try:
        port = int(port_value) if port_value else 465
    except ValueError as exc:
        raise SMTPConfigError("SMTP Port 必须是正整数。") from exc

    return build_config_from_inputs(
        preset_name=app.smtp_preset_var.get().strip() or "自定义",
        sender_email=app.smtp_sender_email_entry.get().strip(),
        password=app.smtp_password_entry.get(),
        username=app.smtp_username_entry.get().strip(),
        sender_name=app.smtp_sender_name_entry.get().strip(),
        host=app.smtp_host_entry.get().strip(),
        port=port,
        security=app.smtp_security_var.get().strip() or "ssl",
        dkim_selector=app.smtp_dkim_selector_entry.get().strip(),
    )


def apply_selected_preset(app, log_action=True):
    config = build_config_from_inputs(
        preset_name=app.smtp_preset_var.get().strip() or "自定义",
        sender_email=app.smtp_sender_email_entry.get().strip(),
        password=app.smtp_password_entry.get(),
        username=app.smtp_username_entry.get().strip(),
        sender_name=app.smtp_sender_name_entry.get().strip(),
        dkim_selector=app.smtp_dkim_selector_entry.get().strip(),
    )
    app.fill_smtp_form(config, preserve_test_fields=True)
    if log_action:
        app.add_log(f"已应用 SMTP 预设：{app.smtp_preset_var.get().strip()}。")


def autofill_preset_from_email(app):
    sender_email = app.smtp_sender_email_entry.get().strip()
    if not sender_email:
        messagebox.showinfo("提示", "请先填写发件邮箱。")
        return
    app.smtp_preset_var.set(infer_preset_from_email(sender_email))
    app.apply_selected_preset()


def fill_smtp_form(app, config: SMTPConfig, preserve_test_fields=False):
    app.smtp_preset_var.set(preset_label_from_provider(config.provider))
    app._set_entry_value(app.smtp_host_entry, config.host)
    app._set_entry_value(app.smtp_port_entry, str(config.port))
    app._set_entry_value(app.smtp_username_entry, config.username)
    app._set_entry_value(app.smtp_password_entry, config.password)
    app._set_entry_value(app.smtp_sender_name_entry, config.sender_name)
    app._set_entry_value(app.smtp_sender_email_entry, config.sender_email)
    app._set_entry_value(app.smtp_dkim_selector_entry, config.dkim_selector)
    app.smtp_security_var.set(config.security)
    app.toggle_advanced_smtp_fields()
    if not preserve_test_fields:
        app._set_entry_value(app.smtp_test_recipient_entry, "")
        app._set_entry_value(app.smtp_subject_entry, "")


def choose_smtp_attachments(app):
    file_paths = filedialog.askopenfilenames(
        title="选择邮件附件",
        filetypes=[
            ("常见附件", "*.pdf *.doc *.docx *.xls *.xlsx *.ppt *.pptx *.jpg *.jpeg *.png *.zip"),
            ("所有文件", "*.*"),
        ],
    )
    if not file_paths:
        return

    existing = list(app.smtp_attachment_paths)
    for item in file_paths:
        path = str(Path(item).expanduser())
        if path not in existing:
            existing.append(path)
    app.smtp_attachment_paths = existing
    app.refresh_attachment_summary()
    app.save_smtp_config(announce=False)
    app.add_log(f"已添加 {len(file_paths)} 个附件。")


def clear_smtp_attachments(app):
    app.smtp_attachment_paths = []
    app.refresh_attachment_summary()
    app.save_smtp_config(announce=False)
    app.add_log("已清空邮件附件。")


def toggle_attachment_details(app):
    app.smtp_attachment_details_var.set(not app.smtp_attachment_details_var.get())
    app.refresh_attachment_summary()


def toggle_attachment_panel(app):
    app.smtp_attachment_section_var.set(not app.smtp_attachment_section_var.get())
    if app.smtp_attachment_section_var.get():
        app.smtp_attachment_content_frame.pack(fill="x", padx=12, pady=(0, 12))
        app.smtp_attachment_section_toggle_button.configure(text="收起")
    else:
        app.smtp_attachment_content_frame.pack_forget()
        app.smtp_attachment_section_toggle_button.configure(text="展开")


def refresh_attachment_summary(app):
    app.smtp_attachment_summary_label.configure(
        text=_build_attachment_summary_line(app.smtp_attachment_paths)
    )
    detail_visible = bool(app.smtp_attachment_paths) and app.smtp_attachment_details_var.get()
    app.smtp_attachment_toggle_button.configure(
        text="收起详情" if detail_visible else "查看详情",
        state="normal" if app.smtp_attachment_paths else "disabled",
    )
    if detail_visible:
        app.smtp_attachment_box.pack(fill="x", padx=12, pady=(0, 12))
    else:
        app.smtp_attachment_box.pack_forget()

    app.smtp_attachment_box.delete("0.0", "end")
    if not app.smtp_attachment_paths:
        app.smtp_attachment_details_var.set(False)
        return

    lines = [f"当前附件 {len(app.smtp_attachment_paths)} 个："]
    for path in app.smtp_attachment_paths:
        file_path = Path(path)
        exists = "OK" if file_path.exists() and file_path.is_file() else "MISSING"
        lines.append(f"- [{exists}] {file_path.name}")
        lines.append(f"  {file_path}")
    app.smtp_attachment_box.insert("0.0", "\n".join(lines))


def _build_attachment_summary_line(paths: list[str]) -> str:
    if not paths:
        return "当前未选择附件。批量发送和 SMTP 测试都会复用这里的附件。"
    names = [Path(path).name for path in paths[:2]]
    extra = f" 等 {len(paths)} 个附件" if len(paths) > 2 else f" 共 {len(paths)} 个附件"
    return "已选附件：" + "、".join(names) + extra


def toggle_advanced_smtp_fields(app):
    show_advanced = (
        app.smtp_show_advanced_var.get() or app.smtp_preset_var.get().strip() == "自定义"
    )
    if show_advanced:
        app.smtp_advanced_frame.grid()
    else:
        app.smtp_advanced_frame.grid_remove()


def set_smtp_status(app, message: str, level: str = "info"):
    colors = {
        "info": "gray70",
        "busy": "#3B8ED0",
        "success": "#3A7A47",
        "error": "#FF6B6B",
        "warn": "#D1A200",
    }
    app.smtp_status_label.configure(text=f"状态：{message}", text_color=colors.get(level, "gray70"))


def set_smtp_busy(app, busy: bool, message: str):
    app.smtp_busy = busy
    state = "disabled" if busy else "normal"
    for button in (
        app.smtp_autofill_button,
        app.smtp_save_button,
        app.smtp_attachment_button,
        app.smtp_clear_attachments_button,
        app.smtp_attachment_toggle_button,
        app.smtp_auth_button,
        app.smtp_test_button,
        app.smtp_auth_test_button,
    ):
        button.configure(state=state)
    app.set_smtp_status(message, "busy" if busy else "info")


def run_background(app, work, on_success, on_error, busy_message: str):
    if app.smtp_busy:
        return

    app.set_smtp_busy(True, busy_message)

    def target():
        try:
            result = work()
        except Exception as exc:
            app.after(0, lambda: app._finish_background(on_error, exc))
            return
        app.after(0, lambda: app._finish_background(on_success, result))

    threading.Thread(target=target, daemon=True).start()


def _finish_background(app, callback, payload):
    app.set_smtp_busy(False, "等待操作")
    callback(payload)


def save_current_account_to_pool(app):
    try:
        config = app.collect_smtp_config()
    except SMTPConfigError as exc:
        messagebox.showerror("保存失败", str(exc))
        return

    if not config.sender_email:
        messagebox.showerror("保存失败", "请先填写发件邮箱。")
        return

    preset_name = app.smtp_preset_var.get().strip() or "自定义"
    label = f"{config.sender_email} ({preset_name})"
    app.storage.save_smtp_account(
        {
            "label": label,
            "provider": config.provider,
            "sender_email": config.sender_email,
            "sender_name": config.sender_name,
            "username": config.username,
            "password": config.password,
            "host": config.host,
            "port": str(config.port),
            "security": config.security,
            "dkim_selector": config.dkim_selector,
        }
    )
    app.populate_account_pool_menu()
    app.smtp_account_var.set(label)
    app.add_log(f"账号池已保存：{label}")


def load_selected_account_from_pool(app):
    label = app.smtp_account_var.get().strip()
    if not label or label == "未保存账号":
        messagebox.showinfo("提示", "请先选择一个已保存账号。")
        return
    account = app.storage.get_smtp_account(label)
    if not account:
        messagebox.showerror("读取失败", "未找到选中的账号。")
        app.populate_account_pool_menu()
        return

    config = SMTPConfig.from_state(
        {
            "smtp_provider": account["provider"],
            "smtp_host": account["host"],
            "smtp_port": account["port"],
            "smtp_username": account["username"],
            "smtp_password": account["password"],
            "smtp_sender_email": account["sender_email"],
            "smtp_sender_name": account["sender_name"],
            "smtp_security": account["security"],
            "smtp_dkim_selector": account["dkim_selector"],
        }
    )
    app.fill_smtp_form(config, preserve_test_fields=True)
    app.add_log(f"已载入账号池配置：{label}")


def delete_selected_account(app):
    label = app.smtp_account_var.get().strip()
    if not label or label == "未保存账号":
        messagebox.showinfo("提示", "当前没有可删除的已保存账号。")
        return
    app.storage.delete_smtp_account(label)
    app.populate_account_pool_menu()
    app.add_log(f"账号池已删除：{label}")


def import_accounts_to_pool(app):
    raw_text = app.smtp_bulk_import_box.get("0.0", "end").strip()
    if not raw_text or raw_text == ACCOUNT_IMPORT_HINT:
        messagebox.showinfo("提示", "请先粘贴批量导入内容。")
        return

    imported = 0
    failed_lines = []
    for index, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            failed_lines.append(f"第 {index} 行格式不足")
            continue

        preset_name, sender_email, password = parts[:3]
        sender_name = parts[3] if len(parts) > 3 else ""
        dkim_selector = parts[4] if len(parts) > 4 else ""
        try:
            config = build_config_from_inputs(
                preset_name=preset_name,
                sender_email=sender_email,
                password=password,
                sender_name=sender_name,
                dkim_selector=dkim_selector,
            )
            label = f"{config.sender_email} ({preset_name})"
            app.storage.save_smtp_account(
                {
                    "label": label,
                    "provider": config.provider,
                    "sender_email": config.sender_email,
                    "sender_name": config.sender_name,
                    "username": config.username,
                    "password": config.password,
                    "host": config.host,
                    "port": str(config.port),
                    "security": config.security,
                    "dkim_selector": config.dkim_selector,
                }
            )
            imported += 1
        except Exception:
            failed_lines.append(f"第 {index} 行无法解析")

    app.populate_account_pool_menu()
    result_message = f"批量导入完成：成功 {imported} 条。"
    if failed_lines:
        result_message += " 失败：" + "；".join(failed_lines[:5])
    app.smtp_result_box.delete("0.0", "end")
    app.smtp_result_box.insert("0.0", result_message)
    app.add_log(result_message)


def run_domain_auth_check(app):
    sender_email = app.smtp_sender_email_entry.get().strip()
    domain = extract_domain_from_email(sender_email)
    if not domain:
        messagebox.showerror("预检失败", "请先填写有效的发件邮箱。")
        return False
    selector = app.smtp_dkim_selector_entry.get().strip()
    app.run_background(
        work=lambda: (domain, format_email_auth_report(build_email_auth_report(domain, selector))),
        on_success=app._handle_domain_auth_success,
        on_error=app._handle_domain_auth_error,
        busy_message=f"正在检查域名 {domain}",
    )
    return True


def load_account_and_check_domain(app):
    app.load_selected_account_from_pool()
    app.run_domain_auth_check()


def run_smtp_test(app):
    try:
        config = app.collect_smtp_config()
        recipient = app.smtp_test_recipient_entry.get().strip()
        subject = app.smtp_subject_entry.get().strip()
        body = app.smtp_body_box.get("0.0", "end").strip()
        attachment_paths = list(app.smtp_attachment_paths)
        if not recipient and config.sender_email:
            recipient = config.sender_email
            app._set_entry_value(app.smtp_test_recipient_entry, recipient)
        if not subject:
            subject = "SMTP Configuration Test"
            app._set_entry_value(app.smtp_subject_entry, subject)
        if not body:
            body = "This is a GlobalReach PRO SMTP test email."
            app.smtp_body_box.delete("0.0", "end")
            app.smtp_body_box.insert("0.0", body)
        app.save_smtp_config(announce=False)
    except SMTPConfigError as exc:
        app.smtp_result_box.delete("0.0", "end")
        app.smtp_result_box.insert("0.0", str(exc))
        app.add_log(str(exc), level="ERROR")
        messagebox.showerror("SMTP 测试失败", str(exc))
        return

    app.run_background(
        work=lambda: (
            config,
            test_smtp_delivery(
                config,
                recipient,
                subject,
                body,
                attachment_paths=attachment_paths,
            ),
        ),
        on_success=app._handle_smtp_test_success,
        on_error=app._handle_smtp_test_error,
        busy_message=f"正在测试 SMTP: {config.sender_email or config.host}",
    )


def run_auth_then_smtp_test(app):
    sender_email = app.smtp_sender_email_entry.get().strip()
    domain = extract_domain_from_email(sender_email)
    if not domain:
        messagebox.showerror("预检失败", "请先填写有效的发件邮箱。")
        return
    selector = app.smtp_dkim_selector_entry.get().strip()
    try:
        smtp_config = app.collect_smtp_config()
        recipient = app.smtp_test_recipient_entry.get().strip() or smtp_config.sender_email
        subject = app.smtp_subject_entry.get().strip() or "SMTP Configuration Test"
        body = (
            app.smtp_body_box.get("0.0", "end").strip()
            or "This is a GlobalReach PRO SMTP test email."
        )
        attachment_paths = list(app.smtp_attachment_paths)
    except SMTPConfigError as exc:
        app._handle_smtp_test_error(exc)
        return

    def work():
        auth_report = build_email_auth_report(domain, selector)
        smtp_result = test_smtp_delivery(
            smtp_config,
            recipient,
            subject,
            body,
            attachment_paths=attachment_paths,
        )
        return auth_report, smtp_config, smtp_result, recipient, subject, body

    app.run_background(
        work=work,
        on_success=app._handle_auth_then_smtp_success,
        on_error=app._handle_auth_then_smtp_error,
        busy_message=f"正在预检并测试 {domain}",
    )


def _handle_domain_auth_success(app, payload):
    domain, result = payload
    app.domain_auth_box.delete("0.0", "end")
    app.domain_auth_box.insert("0.0", result)
    app.add_log(f"域名认证预检完成：{domain}")
    app.set_smtp_status("域名认证预检完成", "success")


def _handle_domain_auth_error(app, exc):
    result = str(exc)
    app.domain_auth_box.delete("0.0", "end")
    app.domain_auth_box.insert("0.0", result)
    app.add_log(result, level="ERROR")
    app.set_smtp_status("域名预检失败", "error")
    messagebox.showerror("域名预检失败", result)


def _handle_smtp_test_success(app, payload):
    config, result = payload
    app.smtp_result_box.delete("0.0", "end")
    app.smtp_result_box.insert("0.0", result + "\n" + summarize_config(config))
    app.add_log(result)
    app.set_smtp_status("SMTP 测试成功", "success")
    messagebox.showinfo("SMTP 测试完成", result)


def _handle_smtp_test_error(app, exc):
    result = str(exc)
    app.smtp_result_box.delete("0.0", "end")
    app.smtp_result_box.insert("0.0", result)
    app.add_log(result, level="ERROR")
    app.set_smtp_status("SMTP 测试失败", "error")
    messagebox.showerror("SMTP 测试失败", result)


def _handle_auth_then_smtp_success(app, payload):
    auth_report, smtp_config, smtp_result, recipient, subject, body = payload
    app._set_entry_value(app.smtp_test_recipient_entry, recipient)
    app._set_entry_value(app.smtp_subject_entry, subject)
    app.smtp_body_box.delete("0.0", "end")
    app.smtp_body_box.insert("0.0", body)
    app.domain_auth_box.delete("0.0", "end")
    app.domain_auth_box.insert("0.0", format_email_auth_report(auth_report))
    app.smtp_result_box.delete("0.0", "end")
    app.smtp_result_box.insert("0.0", smtp_result + "\n" + summarize_config(smtp_config))
    app.add_log(f"域名预检和 SMTP 测试已完成：{smtp_config.sender_email}")
    app.set_smtp_status("预检与 SMTP 测试都已完成", "success")
    messagebox.showinfo("完成", smtp_result)


def _handle_auth_then_smtp_error(app, exc):
    result = str(exc)
    app.smtp_result_box.delete("0.0", "end")
    app.smtp_result_box.insert("0.0", result)
    app.add_log(result, level="ERROR")
    app.set_smtp_status("预检或 SMTP 测试失败", "error")
    messagebox.showerror("执行失败", result)
