import sys
import threading
import tkinter as tk
from datetime import datetime
import os
from pathlib import Path
import platform
from tkinter import filedialog, messagebox

# ========================================================
# 1. 环境自适应补丁
# ========================================================
try:
    import darkdetect
except (ImportError, Exception):
    class MockDarkDetect:
        @staticmethod
        def theme():
            return "Dark"

        @staticmethod
        def isDark():
            return True

        @staticmethod
        def listener(callback):
            return None

    sys.modules["darkdetect"] = MockDarkDetect

import customtkinter as ctk

from app.controllers.smtp_controller import (
    _finish_background as smtp_finish_background,
    _handle_auth_then_smtp_error,
    _handle_auth_then_smtp_success,
    _handle_domain_auth_error,
    _handle_domain_auth_success,
    _handle_smtp_test_error,
    _handle_smtp_test_success,
    apply_selected_preset,
    autofill_preset_from_email,
    choose_smtp_attachments,
    collect_smtp_config,
    clear_smtp_attachments,
    delete_selected_account,
    fill_smtp_form,
    import_accounts_to_pool,
    load_account_and_check_domain,
    load_selected_account_from_pool,
    populate_account_pool_menu,
    prepare_and_save_smtp_config,
    refresh_attachment_summary,
    run_auth_then_smtp_test,
    run_background,
    run_domain_auth_check,
    run_smtp_test,
    save_current_account_to_pool,
    set_smtp_busy,
    set_smtp_status,
    toggle_attachment_details,
    toggle_attachment_panel,
    toggle_advanced_smtp_fields,
)
from app.controllers.state_controller import (
    load_ai_state,
    load_dedupe_state,
    load_governance_state,
    load_persisted_state,
    load_smtp_state,
    load_watch_state,
    save_ai_settings,
    save_dedupe_policy,
    save_smtp_config,
)
from app.controllers.workspace_controller import (
    _handle_batch_error,
    _handle_batch_finish,
    _handle_batch_progress,
    add_suppression_entry_from_ui,
    apply_mapping_from_ui,
    generate_current_preview,
    import_action,
    jump_to_preview,
    load_dataset,
    pause_batch_send,
    refresh_duplicate_history,
    refresh_governance_summary,
    refresh_mapping_summary,
    refresh_subject_samples,
    refresh_suppression_list,
    refresh_task_results,
    refresh_template_metadata,
    reload_last_file,
    render_current_preview,
    reset_auto_mapping,
    resume_batch_send,
    run_preflight,
    save_template_draft,
    show_next_preview,
    show_previous_preview,
    start_batch_send,
    stop_batch_send,
    sync_preview_to_smtp,
    remove_suppression_entry_from_ui,
)
from app.services.ai_writer import AISettings
from app.services.folder_watch import FolderWatcher
from app.services.license_api_client import (
    LicenseAPIError,
    activate_license,
    load_license_server_settings,
    validate_license,
)
from app.services.license_service import (
    LicenseError,
    get_machine_id,
    legacy_local_license_enabled,
    verify_license,
)
from app.services.smtp_service import SMTPConfigError
from app.storage.db import AppStorage
from app.ui.builders import (
    setup_main_view,
    setup_preview_tab,
    setup_sidebar,
    setup_smtp_tab,
    setup_template_tab,
)


APP_VERSION = "2026.04.14"
APP_DISPLAY_NAME = "GlobalReach PRO"
APP_STORAGE_DIRNAME = "globalreach-pro"


def get_runtime_root() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent


def get_app_storage_dir() -> Path:
    if sys.platform == "darwin":
        base_dir = Path.home() / "Library" / "Application Support"
    elif sys.platform.startswith("win"):
        base_dir = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        base_dir = Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    storage_dir = base_dir / APP_STORAGE_DIRNAME
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def format_license_expiry(expires_at: str) -> str:
    normalized = expires_at.strip()
    if not normalized:
        return "长期有效"
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return normalized


def format_license_timestamp(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return "暂无"
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return normalized


def format_license_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized == "active":
        return "正常"
    if normalized == "expired":
        return "已过期"
    if normalized == "disabled":
        return "已停用"
    if normalized == "deleted":
        return "已删除"
    return "未激活"


def format_license_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized == "server":
        return "线上授权"
    if normalized == "open_source":
        return "开源模式"
    return "本地授权"


def mask_license_key(license_key: str) -> str:
    normalized = license_key.strip().upper()
    if len(normalized) <= 8:
        return normalized or "暂无"
    return f"{normalized[:4]}...{normalized[-4:]}"


class ActivationDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        machine_id: str,
        key_label: str = "激活码",
        description: str = "请输入激活码后完成授权，系统会自动绑定当前设备。",
        placeholder_text: str = "请输入激活码",
    ):
        super().__init__(master)
        self.activated = False
        self.machine_id = machine_id

        self.title("激活 GlobalReach PRO")
        self.geometry("520x300")
        self.minsize(520, 300)
        self.resizable(True, False)
        self.transient(master)

        ctk.CTkLabel(
            self,
            text="首次启动需要激活",
            font=("Arial", 18, "bold"),
            text_color="#3B8ED0",
        ).pack(anchor="w", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            self,
            text=description,
            font=("Arial", 12),
            text_color="gray70",
            justify="left",
            wraplength=460,
        ).pack(anchor="w", padx=20, pady=(0, 14))

        ctk.CTkLabel(self, text=key_label, font=("Arial", 13, "bold")).pack(
            anchor="w", padx=20, pady=(0, 0)
        )
        self.key_entry = ctk.CTkEntry(self, placeholder_text=placeholder_text)
        self.key_entry.pack(fill="x", padx=20, pady=(5, 10))
        self.key_entry.bind("<Return>", lambda _event: self.submit())
        self.key_entry.focus_set()

        self.status_label = ctk.CTkLabel(
            self,
            text="状态：请输入激活码后点击激活",
            font=("Arial", 12),
            text_color="gray70",
            wraplength=460,
            justify="left",
        )
        self.status_label.pack(anchor="w", padx=20, pady=(0, 6))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(18, 24))
        ctk.CTkButton(
            actions,
            text="立即激活",
            fg_color="#3A7A47",
            command=self.submit,
        ).pack(side="left")
        ctk.CTkButton(
            actions,
            text="退出",
            fg_color="#8A3B3B",
            command=self.cancel,
        ).pack(side="left", padx=10)

        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def submit(self):
        key = self.key_entry.get().strip()
        if not key:
            self.status_label.configure(text="状态：激活码不能为空", text_color="#FF6B6B")
            return
        self.activated = True
        self.result_key = key
        self.destroy()

    def cancel(self):
        self.activated = False
        self.result_key = ""
        self.destroy()


class OutreachPro(ctk.CTk):
    setup_sidebar = setup_sidebar
    setup_main_view = setup_main_view
    setup_template_tab = setup_template_tab
    setup_preview_tab = setup_preview_tab
    setup_smtp_tab = setup_smtp_tab

    load_persisted_state = load_persisted_state
    load_watch_state = load_watch_state
    load_dedupe_state = load_dedupe_state
    save_dedupe_policy = save_dedupe_policy
    load_ai_state = load_ai_state
    load_governance_state = load_governance_state
    save_ai_settings = save_ai_settings
    load_smtp_state = load_smtp_state
    save_smtp_config = save_smtp_config

    import_action = import_action
    reload_last_file = reload_last_file
    load_dataset = load_dataset
    apply_mapping_from_ui = apply_mapping_from_ui
    reset_auto_mapping = reset_auto_mapping
    refresh_mapping_summary = refresh_mapping_summary
    save_template_draft = save_template_draft
    refresh_template_metadata = refresh_template_metadata
    refresh_subject_samples = refresh_subject_samples
    refresh_duplicate_history = refresh_duplicate_history
    render_current_preview = render_current_preview
    generate_current_preview = generate_current_preview
    show_previous_preview = show_previous_preview
    show_next_preview = show_next_preview
    jump_to_preview = jump_to_preview
    run_preflight = run_preflight
    refresh_governance_summary = refresh_governance_summary
    refresh_suppression_list = refresh_suppression_list
    add_suppression_entry_from_ui = add_suppression_entry_from_ui
    remove_suppression_entry_from_ui = remove_suppression_entry_from_ui
    start_batch_send = start_batch_send
    pause_batch_send = pause_batch_send
    resume_batch_send = resume_batch_send
    stop_batch_send = stop_batch_send
    refresh_task_results = refresh_task_results
    _handle_batch_progress = _handle_batch_progress
    _handle_batch_finish = _handle_batch_finish
    _handle_batch_error = _handle_batch_error
    sync_preview_to_smtp = sync_preview_to_smtp

    populate_account_pool_menu = populate_account_pool_menu
    prepare_and_save_smtp_config = prepare_and_save_smtp_config
    collect_smtp_config = collect_smtp_config
    apply_selected_preset = apply_selected_preset
    autofill_preset_from_email = autofill_preset_from_email
    fill_smtp_form = fill_smtp_form
    choose_smtp_attachments = choose_smtp_attachments
    clear_smtp_attachments = clear_smtp_attachments
    refresh_attachment_summary = refresh_attachment_summary
    toggle_attachment_details = toggle_attachment_details
    toggle_attachment_panel = toggle_attachment_panel
    toggle_advanced_smtp_fields = toggle_advanced_smtp_fields
    set_smtp_status = set_smtp_status
    set_smtp_busy = set_smtp_busy
    run_background = run_background
    _finish_background = smtp_finish_background
    save_current_account_to_pool = save_current_account_to_pool
    load_selected_account_from_pool = load_selected_account_from_pool
    delete_selected_account = delete_selected_account
    import_accounts_to_pool = import_accounts_to_pool
    run_domain_auth_check = run_domain_auth_check
    load_account_and_check_domain = load_account_and_check_domain
    run_smtp_test = run_smtp_test
    run_auth_then_smtp_test = run_auth_then_smtp_test
    _handle_domain_auth_success = _handle_domain_auth_success
    _handle_domain_auth_error = _handle_domain_auth_error
    _handle_smtp_test_success = _handle_smtp_test_success
    _handle_smtp_test_error = _handle_smtp_test_error
    _handle_auth_then_smtp_success = _handle_auth_then_smtp_success
    _handle_auth_then_smtp_error = _handle_auth_then_smtp_error

    def __init__(self):
        super().__init__()
        self.project_root = get_runtime_root()
        self.storage = AppStorage(get_app_storage_dir() / "globalreach.db")
        self.dataset = None
        self.current_file = None
        self.current_preview_index = 0
        self.mapping_vars = {}
        self.mapping_menus = {}
        self.smtp_account_var = tk.StringVar(value="未保存账号")
        self.smtp_preset_var = tk.StringVar(value="自定义")
        self.smtp_show_advanced_var = tk.BooleanVar(value=False)
        self.smtp_attachment_details_var = tk.BooleanVar(value=False)
        self.smtp_attachment_section_var = tk.BooleanVar(value=False)
        self.smtp_busy = False
        self.smtp_attachment_paths = []
        self.ai_mode_var = tk.StringVar(value="local")
        self.ai_tone_var = tk.StringVar(value="professional")
        self.current_draft = None
        self.folder_watcher = FolderWatcher()
        self.watch_thread = None
        self.watch_stop_event = threading.Event()
        self.watch_folder_var = tk.StringVar(value="")
        self.watch_status_var = tk.StringVar(value="监听状态：未开启")
        self.license_summary_var = tk.StringVar(value="授权状态：未激活")
        self.license_meta_var = tk.StringVar(value="项目：暂无  到期：暂无")
        self.license_detail_var = tk.StringVar(value="最近校验：暂无  激活码：暂无")
        self.license_error_var = tk.StringVar(value="授权提示：首次启动后请输入激活码。")
        self.sidebar_nav_buttons = {}
        self.active_sidebar_section = "workbench"
        self.active_task_id = None
        self.send_stop_event = threading.Event()
        self.send_pause_event = threading.Event()
        self.send_thread = None
        self.dedupe_policy_var = tk.StringVar(value="review")

        ctk.set_appearance_mode("dark")
        self.title("GlobalReach PRO - 外贸邮件工作台")
        self.geometry("1380x940")
        self.minsize(1200, 820)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_sidebar()
        self.setup_main_view()
        self.load_persisted_state()
        self.refresh_license_panel()
        self.activate_sidebar_section("workbench")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(120, self.ensure_activation)

    def activate_sidebar_section(self, section_key: str):
        self.active_sidebar_section = section_key
        active_fg = "#2563EB"
        active_hover = "#2563EB"
        inactive_fg = "transparent"
        inactive_hover = "#1D4ED8"
        for key, button in self.sidebar_nav_buttons.items():
            selected = key == section_key
            button.configure(
                fg_color=active_fg if selected else inactive_fg,
                hover_color=active_hover if selected else inactive_hover,
                text_color="#F8FAFC" if selected else "#E5E7EB",
            )

    def open_workbench(self):
        self.activate_sidebar_section("workbench")
        if hasattr(self, "tabview") and hasattr(self, "preview_tab_name"):
            self.tabview.set(self.preview_tab_name)

    def open_template_center(self):
        self.activate_sidebar_section("template")
        if hasattr(self, "tabview") and hasattr(self, "template_tab_name"):
            self.tabview.set(self.template_tab_name)

    def open_preflight_center(self):
        self.activate_sidebar_section("preflight")
        if hasattr(self, "tabview") and hasattr(self, "preview_tab_name"):
            self.tabview.set(self.preview_tab_name)

    def open_smtp_center(self):
        self.activate_sidebar_section("smtp")
        if hasattr(self, "tabview") and hasattr(self, "smtp_tab_name"):
            self.tabview.set(self.smtp_tab_name)

    def choose_watch_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.watch_folder_var.set(folder)
            self.storage.set_state("watch_folder_path", folder)
            self.watch_status_var.set(f"监听状态：已配置 {folder}")
            self.add_log(f"已选择监听目录：{folder}")

    def start_folder_watch(self):
        folder = self.watch_folder_var.get().strip()
        if not folder:
            messagebox.showinfo("提示", "请先选择监听目录。")
            return
        watch_path = Path(folder)
        if not watch_path.exists() or not watch_path.is_dir():
            messagebox.showerror("目录无效", "监听目录不存在或不是文件夹。")
            return
        if self.watch_thread and self.watch_thread.is_alive():
            self.watch_status_var.set("监听状态：已在运行")
            return

        self.storage.set_state("watch_folder_path", folder)
        self.folder_watcher.prime(folder)
        self.watch_stop_event.clear()

        def worker():
            while not self.watch_stop_event.wait(5):
                for new_file in self.folder_watcher.poll(folder):
                    self.after(0, lambda path=new_file: self._handle_new_watch_file(path))

        self.watch_thread = threading.Thread(target=worker, daemon=True)
        self.watch_thread.start()
        self.watch_status_var.set(f"监听状态：运行中 ({folder})")
        self.add_log(f"已开始监听导出目录：{folder}")

    def stop_folder_watch(self):
        self.watch_stop_event.set()
        self.watch_status_var.set("监听状态：已停止")
        self.add_log("已停止监听导出目录。")

    def _handle_new_watch_file(self, file_path: str):
        self.watch_status_var.set(f"发现新名单：{Path(file_path).name}")
        self.add_log(f"检测到新名单文件：{Path(file_path).name}")
        self.load_dataset(file_path)

    def collect_ai_settings(self) -> AISettings:
        return AISettings(
            mode=self.ai_mode_var.get().strip() or "local",
            endpoint=self.ai_endpoint_entry.get().strip(),
            model=self.ai_model_entry.get().strip(),
            api_key=self.ai_api_key_entry.get().strip(),
            tone=self.ai_tone_var.get().strip() or "professional",
            offer_summary=self.ai_offer_entry.get().strip(),
            call_to_action=self.ai_cta_entry.get().strip()
            or "If useful, I can share a short catalog and pricing sample.",
            signature_name=self.ai_signature_entry.get().strip() or "GlobalReach PRO",
        )

    def populate_mapping_controls(self):
        values = ["未映射"]
        if self.dataset:
            values.extend(self.dataset.headers)

        for field, menu in self.mapping_menus.items():
            menu.configure(values=values)
            mapped = self.dataset.field_mapping.get(field) if self.dataset else None
            self.mapping_vars[field].set(mapped or "未映射")

    def ensure_activation(self):
        try:
            machine_id = get_machine_id()
        except LicenseError as exc:
            messagebox.showerror("激活失败", str(exc))
            self.storage.set_state("license_last_error", str(exc))
            self.refresh_license_panel()
            self.destroy()
            return

        stored_key = self.storage.get_state("license_key") or ""
        stored_machine = self.storage.get_state("license_machine_id") or ""
        license_settings = load_license_server_settings(self.storage)
        if license_settings.enabled:
            self.storage.set_state("license_provider", "server")
            stored_token = self.storage.get_state("license_activation_token") or ""
            if stored_key and stored_machine == machine_id and stored_token:
                try:
                    snapshot = validate_license(
                        license_settings,
                        stored_key,
                        stored_token,
                        machine_id,
                        APP_VERSION,
                    )
                    if snapshot.ok:
                        self.storage.set_state("license_status", snapshot.license_status or "active")
                        self.storage.set_state("license_expires_at", snapshot.expires_at)
                        self.storage.set_state("license_last_error", "")
                        self.storage.set_state(
                            "license_verified_at",
                            datetime.now().isoformat(timespec="seconds"),
                        )
                        self.add_log(f"服务端授权验证通过，到期时间：{format_license_expiry(snapshot.expires_at)}。")
                        self.refresh_license_panel()
                        return
                    self.storage.set_state("license_last_error", snapshot.message)
                    self.add_log(f"服务端授权校验失败：{snapshot.message}", level="WARN")
                    self.refresh_license_panel()
                except LicenseAPIError as exc:
                    self.storage.set_state("license_last_error", str(exc))
                    self.add_log(f"服务端授权校验异常：{exc}", level="WARN")
                    self.refresh_license_panel()
        else:
            if not legacy_local_license_enabled():
                self.storage.set_state("license_provider", "open_source")
                self.storage.set_state("license_status", "active")
                self.storage.set_state("license_last_error", "")
                self.add_log("未配置线上授权，已进入开源模式。")
                self.refresh_license_panel()
                return
            self.storage.set_state("license_provider", "local")
            if stored_key and stored_machine == machine_id and verify_license(stored_key, machine_id):
                self.storage.set_state("license_status", "active")
                self.storage.set_state("license_last_error", "")
                self.add_log("本地授权验证通过。")
                self.refresh_license_panel()
                return
        if stored_key and stored_machine and stored_machine != machine_id:
            self.add_log("检测到机器码变化，需重新激活。", level="WARN")
        elif stored_key:
            self.add_log("已保存授权码校验失败，需重新激活。", level="WARN")
        else:
            self.add_log("当前未发现有效授权记录，进入激活流程。", level="WARN")

        key_label = "激活码"
        description = "请输入激活码后完成授权，系统会自动绑定当前设备。"
        placeholder_text = "请输入激活码"
        dialog = ActivationDialog(
            self,
            machine_id,
            key_label=key_label,
            description=description,
            placeholder_text=placeholder_text,
        )
        dialog.grab_set()
        self.wait_window(dialog)
        if not dialog.activated:
            self.add_log("用户取消激活，程序退出。", level="WARN")
            self.refresh_license_panel()
            self.destroy()
            return

        if license_settings.enabled:
            try:
                snapshot = activate_license(
                    license_settings,
                    dialog.result_key,
                    machine_id,
                    APP_VERSION,
                )
            except LicenseAPIError as exc:
                messagebox.showerror("激活失败", str(exc))
                self.storage.set_state("license_last_error", str(exc))
                self.add_log(f"服务端授权激活异常：{exc}", level="ERROR")
                self.refresh_license_panel()
                self.after(50, self.ensure_activation)
                return

            if not snapshot.ok:
                messagebox.showerror("激活失败", snapshot.message or "激活码无效，请检查后重试。")
                self.storage.set_state("license_last_error", snapshot.message)
                self.add_log(f"服务端授权激活失败：{snapshot.message}", level="ERROR")
                self.refresh_license_panel()
                self.after(50, self.ensure_activation)
                return

            self.storage.set_state("license_key", dialog.result_key.strip().upper())
            self.storage.set_state("license_machine_id", machine_id)
            self.storage.set_state("license_activation_token", snapshot.activation_token)
            self.storage.set_state("license_status", snapshot.license_status or "active")
            self.storage.set_state("license_expires_at", snapshot.expires_at)
            self.storage.set_state("license_last_error", "")
            self.storage.set_state("license_verified_at", datetime.now().isoformat(timespec="seconds"))
            self.add_log(
                "服务端授权已完成："
                f"product={license_settings.product_code} "
                f"status={snapshot.license_status or 'active'} "
                f"expires={format_license_expiry(snapshot.expires_at)}"
            )
            messagebox.showinfo(
                "激活成功",
                "激活已完成。\n"
                f"当前状态：{format_license_status(snapshot.license_status)}\n"
                f"到期时间：{format_license_expiry(snapshot.expires_at)}",
            )
            self.refresh_license_panel()
            return

        if not verify_license(dialog.result_key, machine_id):
            messagebox.showerror("激活失败", "激活码无效，请检查后重试。")
            self.storage.set_state("license_last_error", "local_mismatch")
            self.add_log("激活码校验失败。", level="ERROR")
            self.refresh_license_panel()
            self.after(50, self.ensure_activation)
            return

        self.storage.set_state("license_key", dialog.result_key.strip().upper())
        self.storage.set_state("license_machine_id", machine_id)
        self.storage.set_state("license_status", "active")
        self.storage.set_state("license_expires_at", "")
        self.storage.set_state("license_last_error", "")
        self.storage.set_state("license_verified_at", datetime.now().isoformat(timespec="seconds"))
        self.add_log("软件已完成激活。")
        self.refresh_license_panel()

    def refresh_license_panel(self):
        settings = load_license_server_settings(self.storage)
        product_code = settings.product_code or "未配置"
        provider = self.storage.get_state("license_provider") or ("server" if settings.enabled else "local")
        status_text = format_license_status(self.storage.get_state("license_status") or "")
        expires_text = format_license_expiry(self.storage.get_state("license_expires_at") or "")
        verified_text = format_license_timestamp(self.storage.get_state("license_verified_at") or "")
        license_key = mask_license_key(self.storage.get_state("license_key") or "")
        error_text = (self.storage.get_state("license_last_error") or "").strip()

        summary = (
            f"授权：{status_text}"
            f"  项目：{product_code}"
            f"  方式：{format_license_provider(provider)}"
            f"  到期：{expires_text}"
            f"  最近校验：{verified_text}"
            f"  激活码：{license_key}"
        )
        if error_text:
            summary += f"  提示：{error_text}"

        self.license_summary_var.set(summary)
        self.license_meta_var.set(
            f"项目：{product_code}  授权方式：{format_license_provider(provider)}  到期：{expires_text}"
        )
        self.license_detail_var.set(f"最近校验：{verified_text}  激活码：{license_key}")
        self.license_error_var.set(f"授权提示：{error_text or '当前授权状态正常。'}")

    def refresh_license_status(self):
        settings = load_license_server_settings(self.storage)
        self.storage.set_state("license_provider", "server" if settings.enabled else "local")
        if not settings.enabled:
            if not legacy_local_license_enabled():
                self.storage.set_state("license_provider", "open_source")
                self.storage.set_state("license_status", "active")
                self.storage.set_state("license_last_error", "当前以开源模式运行，未启用线上授权。")
                self.refresh_license_panel()
                messagebox.showinfo("授权状态", "当前以开源模式运行，未启用线上授权。")
                return
            self.storage.set_state("license_last_error", "当前未启用线上授权。")
            self.refresh_license_panel()
            messagebox.showinfo("授权状态", "当前客户端未启用线上授权配置。")
            return

        try:
            machine_id = get_machine_id()
        except LicenseError as exc:
            self.storage.set_state("license_last_error", str(exc))
            self.refresh_license_panel()
            messagebox.showerror("授权状态", str(exc))
            return

        stored_key = self.storage.get_state("license_key") or ""
        stored_machine = self.storage.get_state("license_machine_id") or ""
        stored_token = self.storage.get_state("license_activation_token") or ""
        if not stored_key or not stored_token or stored_machine != machine_id:
            self.storage.set_state("license_last_error", "当前设备还没有可校验的授权记录，请先激活。")
            self.refresh_license_panel()
            messagebox.showinfo("授权状态", "当前设备还没有可校验的授权记录，请先完成激活。")
            return

        try:
            snapshot = validate_license(
                settings,
                stored_key,
                stored_token,
                machine_id,
                APP_VERSION,
            )
        except LicenseAPIError as exc:
            self.storage.set_state("license_last_error", str(exc))
            self.refresh_license_panel()
            self.add_log(f"手动刷新授权状态失败：{exc}", level="WARN")
            messagebox.showerror("授权状态", str(exc))
            return

        self.storage.set_state("license_verified_at", datetime.now().isoformat(timespec="seconds"))
        self.storage.set_state("license_expires_at", snapshot.expires_at)
        self.storage.set_state("license_status", snapshot.license_status or ("active" if snapshot.ok else ""))
        self.storage.set_state("license_last_error", "" if snapshot.ok else (snapshot.message or "授权校验失败。"))
        self.refresh_license_panel()
        if snapshot.ok:
            self.add_log(f"手动刷新授权状态成功，到期时间：{format_license_expiry(snapshot.expires_at)}。")
            messagebox.showinfo(
                "授权状态",
                "授权校验通过。\n"
                f"当前状态：{format_license_status(snapshot.license_status)}\n"
                f"到期时间：{format_license_expiry(snapshot.expires_at)}",
            )
            return

        self.add_log(f"手动刷新授权状态失败：{snapshot.message}", level="WARN")
        messagebox.showwarning("授权状态", snapshot.message or "授权校验失败。")

    def load_recent_logs(self):
        for created_at, level, message in self.storage.list_recent_events(limit=8):
            self._append_log(f"[{created_at}] {level}: {message}")

    def add_log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._append_log(f"[{timestamp}] {level}: {message}")
        self.storage.log_event(level, message)

    def _append_log(self, message):
        self.log_console.insert("end", f"{message}\n")
        self.log_console.see("end")

    def get_template_text(self):
        return self.strategy_box.get("0.0", "end").strip()

    def _set_entry_value(self, entry, value: str):
        entry.delete(0, "end")
        entry.insert(0, value)

    def _handle_preview_success(self, draft, preview_email, preview_company, silent):
        self.current_draft = draft
        self.preview_box.delete("0.0", "end")
        self.preview_box.insert("0.0", draft.as_text())
        self.refresh_duplicate_history()
        self.preview_status_label.configure(
            text=(
                f"预览状态：第 {self.current_preview_index + 1}/{self.dataset.total_rows} 条，"
                f"Email={preview_email or '空值'}，Company={preview_company or '空值'}，"
                f"Source={draft.source}"
            )
        )
        if draft.issues:
            self.add_log(
                f"当前预览存在变量问题或回退提示：{', '.join(draft.issues)}",
                level="WARN",
            )
        elif not silent:
            self.add_log("当前线索预览已刷新。")

    def _handle_preview_error(self, exc):
        message = str(exc)
        self.add_log(f"AI 预览生成失败：{message}", level="ERROR")
        messagebox.showerror("AI 预览失败", message)

    def on_close(self):
        self.stop_folder_watch()
        self.stop_batch_send()
        self.save_template_draft()
        self.save_ai_settings(announce=False)
        try:
            self.save_smtp_config(announce=False)
        except SMTPConfigError:
            pass
        self.destroy()


if __name__ == "__main__":
    app = OutreachPro()
    app.mainloop()
