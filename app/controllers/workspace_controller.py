import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from app.constants import DEFAULT_BATCH_DELAY_SECONDS, DEFAULT_BATCH_MAX_RETRIES, UNMAPPED_OPTION
from app.services.ai_writer import AISettings, generate_email_draft, generate_subject_samples
from app.services.batch_sender import (
    BatchProgress,
    BatchSendSettings,
    run_batch_send,
)
from app.services.domain_auth import (
    DomainCheckError,
    build_email_auth_report,
    extract_domain_from_email,
)
from app.services.importer import (
    ImporterError,
    auto_map_fields,
    extract_email_address,
    format_dataset_preview,
    load_leads,
)
from app.services.preflight import build_preflight_report, format_preflight_report
from app.services.template import (
    available_placeholders,
    extract_placeholders,
    split_subject_and_body,
)


def import_action(app):
    file_path = filedialog.askopenfilename(
        filetypes=[("Excel files", "*.xlsx *.xls"), ("CSV", "*.csv")]
    )
    if file_path:
        app.load_dataset(file_path)


def reload_last_file(app):
    last_file = app.storage.get_state("last_file")
    if not last_file:
        messagebox.showinfo("提示", "当前没有保存过最近文件。")
        return
    if not Path(last_file).exists():
        messagebox.showerror("文件不存在", f"未找到文件：\n{last_file}")
        return
    app.load_dataset(last_file)


def load_dataset(app, file_path, announce=True):
    try:
        app.dataset = load_leads(file_path)
    except ImporterError as exc:
        messagebox.showerror("导入失败", str(exc))
        app.add_log(f"导入失败：{exc}", level="ERROR")
        return

    app.current_file = file_path
    app.current_preview_index = 0
    app.file_label.configure(text=f"当前文件：{Path(file_path).name}")
    app.storage.set_state("last_file", file_path)

    app.leads_display.delete("0.0", "end")
    app.leads_display.insert("0.0", format_dataset_preview(app.dataset))

    app.populate_mapping_controls()
    app.refresh_mapping_summary()
    app.refresh_template_metadata()
    app.render_current_preview(silent=True)
    app.run_preflight(silent=True)

    if announce:
        app.add_log(
            f"名单已载入：{Path(file_path).name}，共 {app.dataset.total_rows} 条线索。"
        )


def populate_mapping_controls(app):
    values = [UNMAPPED_OPTION]
    if app.dataset:
        values.extend(app.dataset.headers)

    for field, menu in app.mapping_menus.items():
        menu.configure(values=values)
        mapped = app.dataset.field_mapping.get(field) if app.dataset else None
        app.mapping_vars[field].set(mapped or UNMAPPED_OPTION)


def apply_mapping_from_ui(app):
    if not app.dataset:
        messagebox.showinfo("提示", "请先导入名单。")
        return

    mapping = {}
    for field, var in app.mapping_vars.items():
        value = var.get().strip()
        mapping[field] = None if value == UNMAPPED_OPTION else value

    app.dataset.update_mapping(mapping)
    app.refresh_mapping_summary()
    app.refresh_template_metadata()
    app.render_current_preview(silent=True)
    app.run_preflight(silent=True)
    app.add_log("字段映射已更新。")


def reset_auto_mapping(app):
    if not app.dataset:
        messagebox.showinfo("提示", "请先导入名单。")
        return
    mapping, details = auto_map_fields(app.dataset.headers, app.dataset.rows)
    app.dataset.field_mapping = mapping
    app.dataset.mapping_details = details
    app.populate_mapping_controls()
    app.refresh_mapping_summary()
    app.refresh_template_metadata()
    app.render_current_preview(silent=True)
    app.run_preflight(silent=True)
    app.add_log("字段映射已恢复为自动识别结果。")


def refresh_mapping_summary(app, report=None):
    if not app.dataset:
        app.mapping_box.delete("0.0", "end")
        app.mapping_box.insert("0.0", "字段映射：等待导入名单。\n")
        app.dataset_stats_label.configure(text="名单状态：等待导入")
        return

    app.mapping_box.delete("0.0", "end")
    app.mapping_box.insert("0.0", app.dataset.mapping_summary())
    report = report or build_preflight_report(app.dataset, app.get_template_text())
    app.dataset_stats_label.configure(
        text=(
            f"名单状态：{app.dataset.total_rows} 条线索，"
            f"{report.valid_email_rows} 条有效邮箱，"
            f"{report.missing_email_rows} 条待修正"
        )
    )


def save_template_draft(app):
    template = app.get_template_text()
    app.storage.set_state("template_draft", template)
    app.add_log("模板草稿已保存。")


def refresh_template_metadata(app, _event=None):
    template = app.get_template_text()
    placeholders = extract_placeholders(template)
    available = sorted(available_placeholders(app.dataset)) if app.dataset else []
    settings = app.collect_ai_settings()
    lines = [
        "模板检测结果",
        "",
        "检测到的变量: " + (", ".join(placeholders) if placeholders else "无"),
        "当前可用变量: " + (", ".join(available) if available else "请先导入名单"),
        f"写信模式: {settings.mode}",
        f"语气: {settings.tone}",
        "",
        "建议使用的标准变量: Email, Name, Company, Product",
    ]
    app.variable_box.delete("0.0", "end")
    app.variable_box.insert("0.0", "\n".join(lines))
    app.refresh_subject_samples(silent=True)


def refresh_subject_samples(app, silent=False):
    app.subject_samples_box.delete("0.0", "end")
    if not app.dataset:
        app.subject_samples_box.insert("0.0", "这里会显示前 5 条线索的主题差异样例。\n")
        return
    settings = app.collect_ai_settings()
    if settings.mode != "local":
        settings = AISettings(
            mode="local",
            tone=settings.tone,
            offer_summary=settings.offer_summary,
            call_to_action=settings.call_to_action,
            signature_name=settings.signature_name,
        )
    samples = generate_subject_samples(app.get_template_text(), app.dataset, settings, count=5)
    app.subject_samples_box.insert("0.0", "\n".join(samples))
    if not silent:
        app.add_log("主题差异样例已刷新。")


def refresh_duplicate_history(app):
    app.duplicate_history_box.delete("0.0", "end")
    if not app.dataset:
        app.duplicate_history_box.insert("0.0", "这里会显示当前收件人的历史发信记录。\n")
        return
    email_field = app.dataset.field_mapping.get("email")
    row = app.dataset.row_at(app.current_preview_index)
    recipient_email = extract_email_address(row.get(email_field, "")) if email_field else ""
    if not recipient_email:
        app.duplicate_history_box.insert("0.0", "当前线索没有可用邮箱，无法进行去重检查。\n")
        return

    history = app.storage.recipient_send_history(recipient_email, limit=6)
    policy_labels = {
        "review": "提醒并审核",
        "skip": "自动忽略",
        "send": "继续发送",
    }
    header = f"当前策略: {policy_labels.get(app.dedupe_policy_var.get(), app.dedupe_policy_var.get())}\n"
    if not history:
        app.duplicate_history_box.insert("0.0", header + f"{recipient_email} 未发现历史发信记录。\n")
        return

    app.duplicate_history_box.insert(
        "0.0",
        header + f"{recipient_email} 历史记录 {len(history)} 条，最近记录如下：\n",
    )
    for item in history:
        line = (
            f"- {item['sent_at']} | {item['status']} | {item['task_label']} | "
            f"{item['account_label']} | {item['subject']}"
        )
        if item["error_message"]:
            line += f" | {item['error_message']}"
        app.duplicate_history_box.insert("end", line + "\n")


def render_current_preview(app, silent=False):
    if not app.dataset:
        if not silent:
            messagebox.showinfo("提示", "请先导入名单。")
        return

    template = app.get_template_text()
    row = app.dataset.row_at(app.current_preview_index)
    settings = app.collect_ai_settings()
    email_field = app.dataset.field_mapping.get("email")
    company_field = app.dataset.field_mapping.get("company")
    preview_email = (
        extract_email_address(row.get(email_field, "")) or row.get(email_field, "")
        if email_field
        else "未映射"
    )
    preview_company = row.get(company_field, "") if company_field else "未映射"
    uses_remote_ai = settings.mode in {"openai", "gemini"} and settings.api_key and settings.model
    if uses_remote_ai:
        app.run_background(
            work=lambda: generate_email_draft(
                template=template,
                row=row,
                dataset=app.dataset,
                row_index=app.current_preview_index,
                settings=settings,
            ),
            on_success=lambda draft: app._handle_preview_success(
                draft, preview_email, preview_company, silent
            ),
            on_error=app._handle_preview_error,
            busy_message=f"正在生成第 {app.current_preview_index + 1} 条 AI 预览",
        )
        return

    draft = generate_email_draft(
        template=template,
        row=row,
        dataset=app.dataset,
        row_index=app.current_preview_index,
        settings=settings,
    )
    app._handle_preview_success(draft, preview_email, preview_company, silent)


def generate_current_preview(app):
    if not app.dataset:
        messagebox.showinfo("提示", "请先导入名单。")
        return

    app.tabview.set(app.preview_tab_name)
    app.activate_sidebar_section("preflight")
    app.preview_status_label.configure(
        text=f"预览状态：正在生成第 {app.current_preview_index + 1}/{app.dataset.total_rows} 条"
    )
    app.render_current_preview()


def show_previous_preview(app):
    if not app.dataset:
        messagebox.showinfo("提示", "请先导入名单。")
        return
    app.current_preview_index = max(0, app.current_preview_index - 1)
    app.render_current_preview()


def show_next_preview(app):
    if not app.dataset:
        messagebox.showinfo("提示", "请先导入名单。")
        return
    app.current_preview_index = min(app.dataset.total_rows - 1, app.current_preview_index + 1)
    app.render_current_preview()


def jump_to_preview(app):
    if not app.dataset:
        messagebox.showinfo("提示", "请先导入名单。")
        return

    value = app.preview_jump_entry.get().strip()
    if not value.isdigit():
        messagebox.showerror("输入错误", "请输入有效的正整数行号。")
        return

    index = int(value) - 1
    if index < 0 or index >= app.dataset.total_rows:
        messagebox.showerror("超出范围", "跳转行号超出当前名单范围。")
        return

    app.current_preview_index = index
    app.render_current_preview()


def run_preflight(app, silent=False):
    if not app.dataset:
        if not silent:
            messagebox.showinfo("提示", "请先导入名单。")
        return

    report = build_preflight_report(app.dataset, app.get_template_text())
    report_text = format_preflight_report(report)
    sender_domain = extract_domain_from_email(app.smtp_sender_email_entry.get().strip())
    if sender_domain:
        try:
            auth_report = build_email_auth_report(
                sender_domain,
                app.smtp_dkim_selector_entry.get().strip(),
            )
            report_text += (
                "\n\n发件域名预检摘要\n"
                f"\n- Domain: {sender_domain}"
                f"\n- SPF: {'PASS' if auth_report.spf_found else 'WARN'}"
                f"\n- DKIM: {'PASS' if auth_report.dkim_found else 'WARN'}"
                f"\n- DMARC: {'PASS' if auth_report.dmarc_found else 'WARN'}"
            )
        except DomainCheckError as exc:
            report_text += f"\n\n发件域名预检摘要\n- 查询失败: {exc}"
    app.preflight_box.delete("0.0", "end")
    app.preflight_box.insert("0.0", report_text)
    app.refresh_mapping_summary(report=report)
    if not silent:
        app.add_log("预检完成，已输出名单质量和模板检查结果。")


def start_batch_send(app):
    if not app.dataset:
        messagebox.showinfo("提示", "请先导入名单。")
        return
    if app.send_thread and app.send_thread.is_alive():
        messagebox.showinfo("提示", "当前已有发送任务在运行。")
        return
    if not app.storage.list_smtp_accounts():
        try:
            app.save_current_account_to_pool()
        except Exception:
            pass

    try:
        send_settings = _collect_batch_settings(app)
    except ValueError as exc:
        messagebox.showerror("发送配置错误", str(exc))
        return

    app.send_stop_event.clear()
    ai_settings = app.collect_ai_settings()
    template = app.get_template_text()
    task_label = f"Batch {Path(app.dataset.source_path).name} {datetime.now().strftime('%H%M%S')}"
    app.task_status_box.delete("0.0", "end")
    app.task_status_box.insert("0.0", "任务状态：准备启动...\n")
    app.add_log(f"准备启动批量发送任务：{task_label}")

    def worker():
        try:
            task_id = run_batch_send(
                storage=app.storage,
                dataset=app.dataset,
                template=template,
                ai_settings=ai_settings,
                task_label=task_label,
                duplicate_policy=app.dedupe_policy_var.get().strip() or "review",
                stop_event=app.send_stop_event,
                attachment_paths=app.smtp_attachment_paths,
                settings=send_settings,
                progress_callback=lambda progress: app.after(
                    0, lambda p=progress: app._handle_batch_progress(p)
                ),
            )
            app.after(0, lambda: app._handle_batch_finish(task_id))
        except Exception as exc:
            app.after(0, lambda e=exc: app._handle_batch_error(e))

    app.send_thread = threading.Thread(target=worker, daemon=True)
    app.send_thread.start()


def stop_batch_send(app):
    app.send_stop_event.set()
    app.add_log("已请求停止当前批量发送任务。", level="WARN")
    app.task_status_box.insert("end", "已请求停止任务，等待当前发送完成...\n")
    app.task_status_box.see("end")


def refresh_task_results(app):
    task = app.storage.latest_send_task()
    app.task_status_box.delete("0.0", "end")
    if not task:
        app.task_status_box.insert("0.0", "任务状态：等待启动。\n")
        return
    app.active_task_id = int(task["id"])
    status_counts = app.storage.summarize_task_results(app.active_task_id)
    header = (
        f"任务: {task['label']}\n"
        f"状态: {task['status']}\n"
        f"来源: {Path(task['source_file']).name}\n"
        f"进度: sent={status_counts.get('sent', 0)} "
        f"failed={status_counts.get('failed', 0)} "
        f"skipped={status_counts.get('skipped_duplicate', 0)} "
        f"review={status_counts.get('review_required', 0)} "
        f"total={task['total_count']}\n"
    )
    app.task_status_box.insert("0.0", header + "\n最近结果:\n")
    for item in reversed(app.storage.list_send_results(app.active_task_id, limit=8)):
        line = (
            f"- #{int(item['row_index']) + 1} {item['recipient_email']} | "
            f"{item['account_label']} | {item['status']}"
        )
        if item["error_message"]:
            line += f" | {item['error_message']}"
        app.task_status_box.insert("end", line + "\n")


def _handle_batch_progress(app, progress: BatchProgress):
    line = (
        f"#{progress.row_index + 1}/{progress.total_count} "
        f"{progress.recipient_email} | {progress.account_label} | {progress.status}"
    )
    if progress.attempt_number:
        line += f" | attempt={progress.attempt_number}/{progress.max_attempts}"
    if progress.duplicate_count:
        line += f" | duplicate={progress.duplicate_count}"
    if progress.error_message:
        line += f" | {progress.error_message}"
    app.task_status_box.insert("end", line + "\n")
    app.task_status_box.see("end")

    if progress.status == "sent":
        level = "INFO"
    elif progress.status == "failed":
        level = "ERROR"
    else:
        level = "WARN"
    app.add_log(f"批量发送进度：{line}", level=level)


def _handle_batch_finish(app, task_id: int):
    app.active_task_id = task_id
    app.refresh_task_results()
    app.add_log(f"批量发送任务已结束，任务 ID={task_id}")


def _handle_batch_error(app, exc):
    message = str(exc)
    app.task_status_box.insert("end", f"任务失败：{message}\n")
    app.task_status_box.see("end")
    app.add_log(f"批量发送任务失败：{message}", level="ERROR")
    messagebox.showerror("批量发送失败", message)


def sync_preview_to_smtp(app):
    if not app.dataset:
        messagebox.showinfo("提示", "请先导入名单并生成预览。")
        return

    rendered = app.preview_box.get("0.0", "end").strip()
    if not rendered:
        app.render_current_preview(silent=True)
        rendered = app.preview_box.get("0.0", "end").strip()

    subject, body = split_subject_and_body(rendered)
    email_field = app.dataset.field_mapping.get("email")
    row = app.dataset.row_at(app.current_preview_index)
    recipient = row.get(email_field, "") if email_field else ""

    app.smtp_subject_entry.delete(0, "end")
    app.smtp_subject_entry.insert(0, subject)
    app.smtp_test_recipient_entry.delete(0, "end")
    app.smtp_test_recipient_entry.insert(0, recipient)
    app.smtp_body_box.delete("0.0", "end")
    app.smtp_body_box.insert("0.0", body)
    app.tabview.set(app.smtp_tab_name)
    app.activate_sidebar_section("smtp")
    app.add_log("已将当前预览同步到 SMTP 测试区域。")


def _collect_batch_settings(app) -> BatchSendSettings:
    delay_value = app.batch_delay_entry.get().strip() or DEFAULT_BATCH_DELAY_SECONDS
    retries_value = app.batch_retries_entry.get().strip() or DEFAULT_BATCH_MAX_RETRIES

    try:
        per_email_delay_seconds = float(delay_value)
    except ValueError as exc:
        raise ValueError("发送间隔必须是非负数字。") from exc
    if per_email_delay_seconds < 0:
        raise ValueError("发送间隔必须是非负数字。")

    if not retries_value.isdigit():
        raise ValueError("最大重试次数必须是非负整数。")
    max_retries = int(retries_value)

    app.storage.set_state("batch_delay_seconds", str(per_email_delay_seconds))
    app.storage.set_state("batch_max_retries", str(max_retries))
    return BatchSendSettings(
        per_email_delay_seconds=per_email_delay_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=max(1.0, per_email_delay_seconds or 1.0),
    )
