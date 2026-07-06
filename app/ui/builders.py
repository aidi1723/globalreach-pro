import tkinter as tk

import customtkinter as ctk

from app.constants import ACCOUNT_IMPORT_HINT, UNMAPPED_OPTION
from app.services.smtp_service import get_preset_names

APP_BG = "#07111F"
APP_PANEL = "#0C1A2B"
APP_PANEL_ALT = "#10233A"
APP_BORDER = "#1C3552"
APP_TEXT = "#EAF2FF"
APP_MUTED = "#8BA2BF"
APP_ACCENT = "#2563EB"
APP_ACCENT_ALT = "#7C3AED"
APP_SUCCESS = "#16A34A"
APP_DANGER = "#B45309"


def create_tab_content(tab):
    content = ctk.CTkScrollableFrame(tab, fg_color="transparent")
    content.pack(fill="both", expand=True, padx=0, pady=0)
    return content


def create_sidebar_nav_card(app, parent, key, title, hint, command):
    card = ctk.CTkFrame(parent, fg_color=APP_PANEL, corner_radius=16, border_width=1, border_color=APP_BORDER)
    card.pack(fill="x", padx=14, pady=5)
    top_row = ctk.CTkFrame(card, fg_color="transparent")
    top_row.pack(fill="x", padx=10, pady=(10, 2))
    badge = ctk.CTkLabel(
        top_row,
        text=str(len(app.sidebar_nav_buttons) + 1),
        width=22,
        height=22,
        corner_radius=11,
        fg_color=APP_ACCENT,
        text_color=APP_TEXT,
        font=("Arial", 11, "bold"),
    )
    badge.pack(side="left", padx=(0, 8))
    button = ctk.CTkButton(
        top_row,
        text=title,
        anchor="w",
        height=30,
        corner_radius=10,
        fg_color="transparent",
        hover_color=APP_ACCENT,
        font=("Arial", 14, "bold"),
        command=command,
    )
    button.pack(side="left", fill="x", expand=True)
    ctk.CTkLabel(
        card,
        text=hint,
        font=("Arial", 11),
        text_color=APP_MUTED,
        anchor="w",
        justify="left",
        wraplength=180,
    ).pack(fill="x", padx=12, pady=(0, 10))
    app.sidebar_nav_buttons[key] = button
    return card


def setup_sidebar(app):
    app.sidebar = ctk.CTkFrame(app, width=238, corner_radius=0, fg_color="#08111E")
    app.sidebar.grid(row=0, column=0, sticky="nsew")
    app.sidebar_nav_buttons = {}

    ctk.CTkLabel(
        app.sidebar,
        text="智贸 PRO",
        font=("Arial", 28, "bold"),
        text_color="#60A5FA",
    ).pack(pady=(30, 18))

    create_sidebar_nav_card(
        app,
        app.sidebar,
        "workbench",
        "工作台",
        "导入名单、修正映射、快速查看数据样本。",
        app.open_workbench,
    )
    create_sidebar_nav_card(
        app,
        app.sidebar,
        "template",
        "模板编排",
        "维护正文模板、AI 语气、变量和主题样例。",
        app.open_template_center,
    )
    create_sidebar_nav_card(
        app,
        app.sidebar,
        "preflight",
        "预检与发送",
        "检查风险、查看预览、控制重复发送和批量任务。",
        app.open_preflight_center,
    )
    create_sidebar_nav_card(
        app,
        app.sidebar,
        "smtp",
        "SMTP 控制台",
        "配置发件通道、跑测试、管理账号池和域名预检。",
        app.open_smtp_center,
    )

    restore_card = ctk.CTkFrame(
        app.sidebar,
        fg_color=APP_PANEL,
        corner_radius=16,
        border_width=1,
        border_color=APP_BORDER,
    )
    restore_card.pack(fill="x", padx=14, pady=(10, 5))
    ctk.CTkLabel(
        restore_card,
        text="自动恢复",
        font=("Arial", 13, "bold"),
        text_color="#93C5FD",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(10, 2))
    ctk.CTkLabel(
        restore_card,
        text="最近文件、模板草稿、SMTP 配置和授权状态会自动保存。",
        font=("Arial", 11),
        text_color=APP_MUTED,
        justify="left",
        wraplength=180,
    ).pack(fill="x", padx=12, pady=(0, 10))

    ctk.CTkLabel(
        app.sidebar,
        text="Build: 2026.04.14\nControl Console",
        text_color="gray50",
        font=("Arial", 10),
    ).pack(side="bottom", pady=18)


def setup_main_view(app):
    app.view = ctk.CTkFrame(app, corner_radius=20, fg_color=APP_BG)
    app.view.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
    app.view.grid_columnconfigure(0, weight=1)

    guide_frame = ctk.CTkFrame(
        app.view,
        fg_color=APP_PANEL,
        border_width=1,
        border_color=APP_BORDER,
        corner_radius=18,
    )
    guide_frame.pack(fill="x", padx=20, pady=(18, 14))
    guide_head = ctk.CTkFrame(guide_frame, fg_color="transparent")
    guide_head.pack(fill="x", padx=18, pady=(14, 8))
    guide_text = ctk.CTkFrame(guide_head, fg_color="transparent")
    guide_text.pack(side="left", fill="x", expand=True)

    ctk.CTkLabel(
        guide_text,
        text="群发控制台",
        font=("Arial", 16, "bold"),
        text_color="#60A5FA",
    ).pack(anchor="w")
    ctk.CTkLabel(
        guide_text,
        text="先定名单，再编排模板，随后预检发送，最后进入 SMTP 控制台做通道验证。",
        font=("Arial", 11),
        justify="left",
        text_color=APP_MUTED,
    ).pack(anchor="w", pady=(2, 0))

    quick_actions = ctk.CTkFrame(guide_head, fg_color="transparent")
    quick_actions.pack(side="right")
    ctk.CTkButton(
        quick_actions,
        text="导入名单",
        width=86,
        fg_color=APP_ACCENT,
        command=app.import_action,
    ).pack(side="left")
    ctk.CTkButton(
        quick_actions,
        text="生成预览",
        width=86,
        fg_color=APP_ACCENT_ALT,
        command=app.generate_current_preview,
    ).pack(side="left", padx=8)
    ctk.CTkButton(
        quick_actions,
        text="运行预检",
        width=86,
        fg_color="#0F766E",
        command=app.run_preflight,
    ).pack(side="left")

    license_frame = ctk.CTkFrame(
        app.view,
        fg_color=APP_PANEL_ALT,
        border_width=1,
        border_color=APP_BORDER,
        corner_radius=18,
    )
    license_frame.pack(fill="x", padx=20, pady=(0, 12))
    header_row = ctk.CTkFrame(license_frame, fg_color="transparent")
    header_row.pack(fill="x", padx=14, pady=(10, 10))
    ctk.CTkLabel(
        header_row,
        text="授权状态",
        font=("Arial", 13, "bold"),
        text_color="#86EFAC",
        width=72,
    ).pack(side="left", padx=(0, 10))
    ctk.CTkLabel(
        header_row,
        textvariable=app.license_summary_var,
        font=("Arial", 11),
        text_color=APP_TEXT,
        justify="left",
        anchor="w",
    ).pack(side="left", fill="x", expand=True)
    ctk.CTkButton(
        header_row,
        text="刷新",
        width=72,
        fg_color=APP_ACCENT,
        command=app.refresh_license_status,
    ).pack(side="right")

    workspace = ctk.CTkFrame(app.view, fg_color="transparent")
    workspace.pack(fill="both", expand=True, padx=20)

    app.left_col = ctk.CTkScrollableFrame(
        workspace,
        fg_color=APP_PANEL,
        corner_radius=18,
        border_width=1,
        border_color=APP_BORDER,
    )
    app.left_col.pack(side="left", fill="both", expand=True, padx=(0, 10))

    ctk.CTkLabel(
        app.left_col,
        text="名单工作区",
        font=("Arial", 15, "bold"),
        text_color=APP_TEXT,
    ).pack(pady=(10, 4), padx=15, anchor="w")
    status_row = ctk.CTkFrame(app.left_col, fg_color="transparent")
    status_row.pack(fill="x", padx=15, pady=(0, 3))
    app.file_label = ctk.CTkLabel(
        status_row,
        text="当前文件：未载入",
        font=("Arial", 10),
        text_color=APP_MUTED,
        anchor="w",
    )
    app.file_label.pack(side="left", fill="x", expand=True)

    app.dataset_stats_label = ctk.CTkLabel(
        status_row,
        text="名单状态：等待导入",
        font=("Arial", 10),
        text_color=APP_MUTED,
        anchor="e",
    )
    app.dataset_stats_label.pack(side="right", padx=(10, 0))

    app.leads_display = ctk.CTkTextbox(
        app.left_col,
        height=132,
        fg_color="#08111E",
        font=("Menlo", 12),
        text_color="#00FF99",
        border_width=1,
        border_color=APP_BORDER,
    )
    app.leads_display.pack(fill="x", padx=15, pady=(3, 4))
    app.leads_display.insert("0.0", "请载入 Excel 或 CSV 文件。\n")

    ctk.CTkLabel(app.left_col, text="字段映射", font=("Arial", 13, "bold"), text_color=APP_TEXT).pack(
        anchor="w", padx=15, pady=(6, 3)
    )
    mapping_controls = ctk.CTkFrame(app.left_col, fg_color="transparent")
    mapping_controls.pack(fill="x", padx=15)
    compact_labels = {
        "email": "邮箱",
        "company": "公司",
        "name": "联系人",
        "product": "产品",
    }
    for column_index in range(4):
        mapping_controls.grid_columnconfigure(column_index, weight=1)

    for column_index, field in enumerate(("email", "company", "name", "product")):
        field_frame = ctk.CTkFrame(mapping_controls, fg_color="transparent")
        field_frame.grid(row=0, column=column_index, sticky="ew", padx=(0 if column_index == 0 else 6, 0))
        var = tk.StringVar(value=UNMAPPED_OPTION)
        ctk.CTkLabel(
            field_frame,
            text=compact_labels[field],
            font=("Arial", 11),
            text_color=APP_MUTED,
        ).pack(anchor="w", pady=(0, 2))
        menu = ctk.CTkOptionMenu(
            field_frame,
            values=[UNMAPPED_OPTION],
            variable=var,
            width=120,
            height=30,
            fg_color=APP_PANEL_ALT,
            button_color=APP_ACCENT,
            button_hover_color="#1D4ED8",
        )
        menu.pack(fill="x")
        app.mapping_vars[field] = var
        app.mapping_menus[field] = menu

    mapping_actions = ctk.CTkFrame(app.left_col, fg_color="transparent")
    mapping_actions.pack(fill="x", padx=15, pady=(6, 4))
    ctk.CTkButton(
        mapping_actions,
        text="应用映射",
        fg_color=APP_ACCENT,
        command=app.apply_mapping_from_ui,
    ).pack(side="left")
    ctk.CTkButton(
        mapping_actions,
        text="恢复自动识别",
        fg_color="#334155",
        command=app.reset_auto_mapping,
    ).pack(side="left", padx=10)

    app.mapping_box = ctk.CTkTextbox(
        app.left_col,
        height=56,
        fg_color="#08111E",
        font=("Menlo", 11),
        text_color="#D6D6D6",
        border_width=1,
        border_color=APP_BORDER,
    )
    app.mapping_box.pack(fill="x", padx=15, pady=(0, 6))
    app.mapping_box.insert("0.0", "字段映射：等待导入名单。\n")

    import_actions = ctk.CTkFrame(app.left_col, fg_color="transparent")
    import_actions.pack(fill="x", padx=15, pady=(0, 8))
    ctk.CTkButton(
        import_actions,
        text="导入 Excel / CSV",
        fg_color=APP_ACCENT,
        command=app.import_action,
    ).pack(side="left")
    ctk.CTkButton(
        import_actions,
        text="重新载入上次文件",
        fg_color=APP_SUCCESS,
        command=app.reload_last_file,
    ).pack(side="left", padx=10)

    watch_frame = ctk.CTkFrame(app.left_col, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    watch_frame.pack(fill="x", padx=15, pady=(0, 8))
    watch_frame.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(watch_frame, text="导出监听", font=("Arial", 12, "bold"), text_color=APP_TEXT).grid(
        row=0, column=0, sticky="w", padx=(12, 8), pady=(10, 6)
    )
    app.watch_folder_entry = ctk.CTkEntry(
        watch_frame,
        textvariable=app.watch_folder_var,
        placeholder_text="选择获客系统导出目录",
    )
    app.watch_folder_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(10, 6))
    ctk.CTkButton(
        watch_frame,
        text="目录",
        width=58,
        fg_color=APP_ACCENT,
        command=app.choose_watch_folder,
    ).grid(row=0, column=2, sticky="ew", padx=(0, 6), pady=(10, 6))
    ctk.CTkButton(
        watch_frame,
        text="开始",
        width=58,
        fg_color=APP_SUCCESS,
        command=app.start_folder_watch,
    ).grid(row=0, column=3, sticky="ew", padx=(0, 6), pady=(10, 6))
    ctk.CTkButton(
        watch_frame,
        text="停止",
        width=58,
        fg_color=APP_DANGER,
        command=app.stop_folder_watch,
    ).grid(row=0, column=4, sticky="ew", padx=(0, 12), pady=(10, 6))
    ctk.CTkLabel(
        watch_frame,
        textvariable=app.watch_status_var,
        font=("Arial", 10),
        text_color=APP_MUTED,
    ).grid(row=1, column=0, columnspan=5, sticky="w", padx=12, pady=(0, 10))

    app.right_col = ctk.CTkFrame(workspace, width=520, fg_color="transparent")
    app.right_col.pack(side="left", fill="both", expand=False)

    app.tabview = ctk.CTkTabview(
        app.right_col,
        width=500,
        fg_color=APP_PANEL,
        corner_radius=18,
        border_width=1,
        border_color=APP_BORDER,
        segmented_button_fg_color="#0B1625",
        segmented_button_selected_color=APP_ACCENT,
        segmented_button_selected_hover_color="#1D4ED8",
        segmented_button_unselected_color="#0B1625",
        segmented_button_unselected_hover_color=APP_PANEL_ALT,
        text_color=APP_TEXT,
    )
    app.tabview.pack(fill="both", expand=True, padx=10, pady=10)
    app.template_tab_name = "模板编排"
    app.preview_tab_name = "预检与发送"
    app.smtp_tab_name = "SMTP 控制台"
    app.template_tab = app.tabview.add(app.template_tab_name)
    app.preview_tab = app.tabview.add(app.preview_tab_name)
    app.smtp_tab = app.tabview.add(app.smtp_tab_name)

    app.setup_template_tab()
    app.setup_preview_tab()
    app.setup_smtp_tab()

    log_panel = ctk.CTkFrame(
        app.view,
        corner_radius=18,
        fg_color=APP_PANEL,
        border_width=1,
        border_color=APP_BORDER,
    )
    log_panel.pack(fill="x", padx=20, pady=(8, 10))
    ctk.CTkLabel(log_panel, text="执行日志", font=("Arial", 12, "bold"), text_color=APP_TEXT).pack(
        anchor="w", padx=20, pady=(8, 0)
    )
    app.log_console = ctk.CTkTextbox(
        log_panel,
        height=56,
        fg_color="#08111E",
        text_color="#00FF99",
        font=("Menlo", 11),
        border_width=1,
        border_color=APP_BORDER,
    )
    app.log_console.pack(fill="x", padx=20, pady=(6, 10))


def setup_template_tab(app):
    parent = create_tab_content(app.template_tab)

    template_header = ctk.CTkFrame(parent, fg_color="transparent")
    template_header.pack(fill="x", padx=15, pady=(12, 8))
    ctk.CTkLabel(template_header, text="邮件模板", font=("Arial", 14, "bold")).pack(
        side="left"
    )
    ctk.CTkButton(
        template_header,
        text="生成预览",
        width=86,
        fg_color="#7D5FFF",
        command=app.generate_current_preview,
    ).pack(side="right")
    ctk.CTkButton(
        template_header,
        text="保存",
        width=72,
        fg_color="#5A6472",
        command=app.save_template_draft,
    ).pack(side="right", padx=8)
    ctk.CTkButton(
        template_header,
        text="刷新变量",
        width=86,
        fg_color="#3A7A47",
        command=app.refresh_template_metadata,
    ).pack(side="right", padx=(0, 8))

    app.strategy_box = ctk.CTkTextbox(
        parent,
        height=180,
        fg_color="#000000",
        font=("Arial", 13),
    )
    app.strategy_box.pack(fill="x", padx=15, pady=(0, 6))
    app.strategy_box.bind("<KeyRelease>", app.refresh_template_metadata)

    ai_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    ai_frame.pack(fill="x", padx=15, pady=(0, 8))
    ai_frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(ai_frame, text="AI 写信设置", font=("Arial", 13, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 6)
    )
    ctk.CTkLabel(
        ai_frame,
        text="默认本地差异化模式；不填 API 也能生成逐封不同内容。",
        font=("Arial", 11),
        text_color="gray70",
    ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6))

    ctk.CTkLabel(ai_frame, text="写信模式", font=("Arial", 12)).grid(
        row=2, column=0, sticky="w", padx=12, pady=6
    )
    app.ai_mode_menu = ctk.CTkOptionMenu(
        ai_frame,
        values=["local", "openai", "gemini"],
        variable=app.ai_mode_var,
    )
    app.ai_mode_menu.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=6)

    ctk.CTkLabel(ai_frame, text="语气", font=("Arial", 12)).grid(
        row=3, column=0, sticky="w", padx=12, pady=6
    )
    app.ai_tone_menu = ctk.CTkOptionMenu(
        ai_frame,
        values=["professional", "warm", "direct"],
        variable=app.ai_tone_var,
    )
    app.ai_tone_menu.grid(row=3, column=1, sticky="ew", padx=(0, 12), pady=6)

    app.ai_model_entry = create_labeled_entry(ai_frame, "模型(可选)", 4)
    app.ai_endpoint_entry = create_labeled_entry(ai_frame, "接口地址(可选)", 5)
    app.ai_api_key_entry = create_labeled_entry(ai_frame, "API Key(可选)", 6, show="*")
    app.ai_offer_entry = create_labeled_entry(ai_frame, "产品卖点摘要", 7)
    app.ai_cta_entry = create_labeled_entry(ai_frame, "行动引导 CTA", 8)
    app.ai_signature_entry = create_labeled_entry(ai_frame, "落款名称", 9)

    ai_actions = ctk.CTkFrame(ai_frame, fg_color="transparent")
    ai_actions.grid(row=10, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 10))
    ctk.CTkButton(
        ai_actions,
        text="保存 AI 设置",
        fg_color="#5A6472",
        command=app.save_ai_settings,
    ).pack(side="left")
    ctk.CTkButton(
        ai_actions,
        text="生成 5 条主题样例",
        fg_color="#3A7A47",
        command=app.refresh_subject_samples,
    ).pack(side="left", padx=10)

    ctk.CTkLabel(parent, text="变量面板", font=("Arial", 13, "bold")).pack(
        anchor="w", padx=15, pady=(6, 0)
    )
    app.variable_box = ctk.CTkTextbox(
        parent,
        height=84,
        fg_color="#08111E",
        font=("Menlo", 12),
        text_color="#D6D6D6",
        border_width=1,
        border_color=APP_BORDER,
    )
    app.variable_box.pack(fill="x", padx=15, pady=(4, 8))

    ctk.CTkLabel(parent, text="主题差异样例", font=("Arial", 13, "bold")).pack(
        anchor="w", padx=15, pady=(0, 0)
    )
    app.subject_samples_box = ctk.CTkTextbox(
        parent,
        height=84,
        fg_color="#08111E",
        font=("Menlo", 12),
        text_color="#00FF99",
        border_width=1,
        border_color=APP_BORDER,
    )
    app.subject_samples_box.pack(fill="both", expand=True, padx=15, pady=(4, 12))
    app.subject_samples_box.insert("0.0", "这里会显示前 5 条线索的主题差异样例。\n")


def setup_preview_tab(app):
    parent = create_tab_content(app.preview_tab)

    preview_top = ctk.CTkFrame(parent, fg_color="transparent")
    preview_top.pack(fill="x", padx=15, pady=(12, 8))
    app.preview_status_label = ctk.CTkLabel(
        preview_top,
        text="预览状态：等待载入名单",
        font=("Arial", 11),
        text_color="gray70",
    )
    app.preview_status_label.pack(side="left", fill="x", expand=True)

    navigation = ctk.CTkFrame(preview_top, fg_color="transparent")
    navigation.pack(side="right")
    ctk.CTkButton(
        navigation,
        text="上一条",
        width=72,
        fg_color="#5A6472",
        command=app.show_previous_preview,
    ).pack(side="left")
    ctk.CTkButton(
        navigation,
        text="下一条",
        width=72,
        fg_color="#1F538D",
        command=app.show_next_preview,
    ).pack(side="left", padx=8)
    app.preview_jump_entry = ctk.CTkEntry(navigation, width=72, placeholder_text="行号")
    app.preview_jump_entry.pack(side="left", padx=(10, 6))
    ctk.CTkButton(
        navigation,
        text="跳转",
        width=58,
        fg_color="#3A7A47",
        command=app.jump_to_preview,
    ).pack(side="left")

    app.preview_box = ctk.CTkTextbox(
        parent,
        height=180,
        fg_color="#101010",
        font=("Arial", 13),
    )
    app.preview_box.pack(fill="x", padx=15, pady=(0, 8))
    app.preview_box.insert("0.0", "这里会显示当前线索渲染后的邮件内容。\n")

    preflight_actions = ctk.CTkFrame(parent, fg_color="transparent")
    preflight_actions.pack(fill="x", padx=15, pady=(0, 8))
    ctk.CTkButton(
        preflight_actions,
        text="执行任务预检",
        fg_color="#3B8ED0",
        command=app.run_preflight,
    ).pack(side="left")
    ctk.CTkButton(
        preflight_actions,
        text="开始批量发送",
        fg_color="#3A7A47",
        command=app.start_batch_send,
    ).pack(side="left", padx=10)
    ctk.CTkButton(
        preflight_actions,
        text="同步到 SMTP 测试",
        fg_color="#7D5FFF",
        command=app.sync_preview_to_smtp,
    ).pack(side="left")

    governance_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    governance_frame.pack(fill="x", padx=15, pady=(0, 8))
    governance_frame.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
        governance_frame,
        text="发送治理摘要",
        font=("Arial", 13, "bold"),
    ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))
    app.governance_summary_box = ctk.CTkTextbox(
        governance_frame,
        height=104,
        fg_color="#101010",
        font=("Menlo", 11),
        text_color="#D6D6D6",
    )
    app.governance_summary_box.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
    app.governance_summary_box.insert("0.0", "发送治理摘要：等待刷新。\n")

    attachment_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    attachment_frame.pack(fill="x", padx=15, pady=(0, 8))
    attachment_header = ctk.CTkFrame(attachment_frame, fg_color="transparent")
    attachment_header.pack(fill="x", padx=12, pady=(10, 6))
    ctk.CTkLabel(attachment_header, text="发送附件", font=("Arial", 13, "bold")).pack(side="left")
    app.smtp_attachment_section_toggle_button = ctk.CTkButton(
        attachment_header,
        text="展开",
        width=72,
        fg_color="#5A6472",
        command=app.toggle_attachment_panel,
    )
    app.smtp_attachment_section_toggle_button.pack(side="right")
    ctk.CTkLabel(
        attachment_frame,
        text="附件会同时用于 SMTP 测试和批量发送。",
        font=("Arial", 11),
        text_color="gray70",
        justify="left",
    ).pack(anchor="w", padx=12, pady=(0, 6))
    
    app.smtp_attachment_summary_label = ctk.CTkLabel(
        attachment_frame,
        text="当前未选择附件。批量发送和 SMTP 测试都会复用这里的附件。",
        font=("Arial", 11),
        text_color="gray70",
        justify="left",
        wraplength=460,
    )
    app.smtp_attachment_summary_label.pack(anchor="w", padx=12, pady=(0, 6))

    app.smtp_attachment_content_frame = ctk.CTkFrame(attachment_frame, fg_color="transparent")
    attachment_actions = ctk.CTkFrame(app.smtp_attachment_content_frame, fg_color="transparent")
    attachment_actions.pack(fill="x", pady=(0, 8))
    app.smtp_attachment_button = ctk.CTkButton(
        attachment_actions,
        text="添加附件",
        fg_color="#3A7A47",
        command=app.choose_smtp_attachments,
    )
    app.smtp_attachment_button.pack(side="left")
    app.smtp_clear_attachments_button = ctk.CTkButton(
        attachment_actions,
        text="清空附件",
        fg_color="#8A3B3B",
        command=app.clear_smtp_attachments,
    )
    app.smtp_clear_attachments_button.pack(side="left", padx=10)
    app.smtp_attachment_toggle_button = ctk.CTkButton(
        attachment_actions,
        text="查看详情",
        fg_color="#5A6472",
        command=app.toggle_attachment_details,
        state="disabled",
    )
    app.smtp_attachment_toggle_button.pack(side="left")

    app.smtp_attachment_box = ctk.CTkTextbox(
        app.smtp_attachment_content_frame,
        height=68,
        fg_color="#101010",
        font=("Menlo", 11),
        text_color="#D6D6D6",
    )
    app.smtp_attachment_box.insert("0.0", "当前未选择附件。批量发送和 SMTP 测试都会复用这里的附件。\n")

    ctk.CTkLabel(parent, text="预检报告", font=("Arial", 13, "bold")).pack(
        anchor="w", padx=15, pady=(4, 0)
    )
    app.preflight_box = ctk.CTkTextbox(
        parent,
        height=140,
        fg_color="#08111E",
        font=("Menlo", 12),
        text_color="#00FF99",
        border_width=1,
        border_color=APP_BORDER,
    )
    app.preflight_box.pack(fill="both", expand=True, padx=15, pady=(4, 10))
    app.preflight_box.insert("0.0", "这里会显示名单预检结果。\n")

    dedupe_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    dedupe_frame.pack(fill="x", padx=15, pady=(0, 10))
    dedupe_frame.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(dedupe_frame, text="重复收件人控制", font=("Arial", 13, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 6)
    )
    ctk.CTkLabel(
        dedupe_frame,
        text="历史已发送邮箱可审核、忽略或继续发送。",
        font=("Arial", 11),
        text_color="gray70",
    ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6))
    ctk.CTkLabel(dedupe_frame, text="重复策略", font=("Arial", 12)).grid(
        row=2, column=0, sticky="w", padx=12, pady=6
    )
    app.dedupe_policy_menu = ctk.CTkOptionMenu(
        dedupe_frame,
        values=["review", "skip", "send"],
        variable=app.dedupe_policy_var,
        command=lambda _value: (app.save_dedupe_policy(), app.refresh_governance_summary()),
    )
    app.dedupe_policy_menu.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=6)
    app.duplicate_history_box = ctk.CTkTextbox(
        dedupe_frame,
        height=72,
        fg_color="#101010",
        font=("Menlo", 11),
        text_color="#D6D6D6",
    )
    app.duplicate_history_box.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 10))
    app.duplicate_history_box.insert("0.0", "这里会显示当前收件人的历史发信记录。\n")

    suppression_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    suppression_frame.pack(fill="x", padx=15, pady=(0, 10))
    suppression_frame.grid_columnconfigure(1, weight=1)
    suppression_frame.grid_columnconfigure(3, weight=1)
    ctk.CTkLabel(suppression_frame, text="抑制名单", font=("Arial", 13, "bold")).grid(
        row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 4)
    )
    app.suppression_count_label = ctk.CTkLabel(
        suppression_frame,
        text="抑制名单：0 条",
        font=("Arial", 11),
        text_color=APP_MUTED,
    )
    app.suppression_count_label.grid(row=1, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 6))
    ctk.CTkLabel(suppression_frame, text="邮箱", font=("Arial", 12)).grid(
        row=2, column=0, sticky="w", padx=12, pady=4
    )
    app.suppression_email_entry = ctk.CTkEntry(suppression_frame)
    app.suppression_email_entry.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=4)
    ctk.CTkLabel(suppression_frame, text="原因", font=("Arial", 12)).grid(
        row=2, column=2, sticky="w", padx=(0, 8), pady=4
    )
    app.suppression_reason_entry = ctk.CTkEntry(suppression_frame)
    app.suppression_reason_entry.grid(row=2, column=3, sticky="ew", padx=(0, 12), pady=4)
    ctk.CTkLabel(suppression_frame, text="来源", font=("Arial", 12)).grid(
        row=3, column=0, sticky="w", padx=12, pady=4
    )
    app.suppression_source_entry = ctk.CTkEntry(suppression_frame)
    app.suppression_source_entry.grid(row=3, column=1, sticky="ew", padx=(0, 12), pady=4)
    suppression_actions = ctk.CTkFrame(suppression_frame, fg_color="transparent")
    suppression_actions.grid(row=3, column=2, columnspan=2, sticky="e", padx=12, pady=4)
    ctk.CTkButton(
        suppression_actions,
        text="加入",
        width=64,
        fg_color="#3A7A47",
        command=app.add_suppression_entry_from_ui,
    ).pack(side="left")
    ctk.CTkButton(
        suppression_actions,
        text="移除",
        width=64,
        fg_color="#8A3B3B",
        command=app.remove_suppression_entry_from_ui,
    ).pack(side="left", padx=8)
    ctk.CTkButton(
        suppression_actions,
        text="刷新",
        width=64,
        fg_color="#5A6472",
        command=app.refresh_suppression_list,
    ).pack(side="left")
    app.suppression_list_box = ctk.CTkTextbox(
        suppression_frame,
        height=86,
        fg_color="#101010",
        font=("Menlo", 11),
        text_color="#D6D6D6",
    )
    app.suppression_list_box.grid(row=4, column=0, columnspan=4, sticky="ew", padx=12, pady=(4, 10))
    app.suppression_list_box.insert("0.0", "暂无抑制名单记录。\n")

    task_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    task_frame.pack(fill="x", padx=15, pady=(0, 10))
    task_frame.grid_columnconfigure(0, weight=1)
    task_frame.grid_columnconfigure(1, weight=1)
    task_frame.grid_columnconfigure(2, weight=1)
    task_frame.grid_columnconfigure(3, weight=1)
    task_frame.grid_columnconfigure(4, weight=1)
    ctk.CTkLabel(task_frame, text="批量发送任务", font=("Arial", 13, "bold")).grid(
        row=0, column=0, columnspan=5, sticky="w", padx=12, pady=(10, 6)
    )
    app.task_summary_label = ctk.CTkLabel(
        task_frame,
        text="任务摘要：等待启动",
        font=("Arial", 11),
        text_color=APP_MUTED,
        anchor="w",
    )
    app.task_summary_label.grid(row=1, column=0, columnspan=5, sticky="w", padx=12, pady=(0, 4))
    app.task_status_box = ctk.CTkTextbox(
        task_frame,
        height=64,
        fg_color="#101010",
        font=("Menlo", 11),
        text_color="#D6D6D6",
    )
    app.task_status_box.grid(row=2, column=0, columnspan=5, sticky="ew", padx=12, pady=(0, 8))
    app.task_status_box.insert("0.0", "任务状态：等待启动。\n")

    task_settings = ctk.CTkFrame(task_frame, fg_color="transparent")
    task_settings.grid(row=3, column=0, columnspan=5, sticky="ew", padx=12, pady=(0, 8))
    task_settings.grid_columnconfigure(1, weight=1)
    task_settings.grid_columnconfigure(3, weight=1)
    ctk.CTkLabel(task_settings, text="发送间隔(秒)", font=("Arial", 12)).grid(
        row=0, column=0, sticky="w", pady=4
    )
    app.batch_delay_entry = ctk.CTkEntry(task_settings)
    app.batch_delay_entry.grid(row=0, column=1, sticky="ew", padx=(10, 18), pady=4)
    ctk.CTkLabel(task_settings, text="最大重试次数", font=("Arial", 12)).grid(
        row=0, column=2, sticky="w", pady=4
    )
    app.batch_retries_entry = ctk.CTkEntry(task_settings)
    app.batch_retries_entry.grid(row=0, column=3, sticky="ew", padx=(10, 0), pady=4)
    ctk.CTkLabel(task_settings, text="每日/账号(0=不限制)", font=("Arial", 12)).grid(
        row=1, column=0, sticky="w", pady=4
    )
    app.daily_limit_entry = ctk.CTkEntry(task_settings)
    app.daily_limit_entry.grid(row=1, column=1, sticky="ew", padx=(10, 18), pady=4)
    ctk.CTkLabel(task_settings, text="每小时/账号(0=不限制)", font=("Arial", 12)).grid(
        row=1, column=2, sticky="w", pady=4
    )
    app.hourly_limit_entry = ctk.CTkEntry(task_settings)
    app.hourly_limit_entry.grid(row=1, column=3, sticky="ew", padx=(10, 0), pady=4)

    ctk.CTkButton(
        task_frame,
        text="开始批量发送",
        width=82,
        fg_color="#3A7A47",
        command=app.start_batch_send,
    ).grid(row=4, column=0, sticky="ew", padx=(12, 4), pady=(0, 10))
    ctk.CTkButton(
        task_frame,
        text="停止当前任务",
        width=82,
        fg_color="#8A3B3B",
        command=app.stop_batch_send,
    ).grid(row=4, column=1, sticky="ew", padx=4, pady=(0, 10))
    ctk.CTkButton(
        task_frame,
        text="暂停任务",
        width=82,
        fg_color="#B45309",
        command=app.pause_batch_send,
    ).grid(row=4, column=2, sticky="ew", padx=4, pady=(0, 10))
    ctk.CTkButton(
        task_frame,
        text="恢复任务",
        width=82,
        fg_color="#5A6472",
        command=app.resume_batch_send,
    ).grid(row=4, column=3, sticky="ew", padx=4, pady=(0, 10))
    ctk.CTkButton(
        task_frame,
        text="刷新任务结果",
        width=82,
        fg_color="#1F538D",
        command=app.refresh_task_results,
    ).grid(row=4, column=4, sticky="ew", padx=(4, 12), pady=(0, 10))

    app.refresh_suppression_list()


def setup_smtp_tab(app):
    parent = create_tab_content(app.smtp_tab)

    header_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    header_frame.pack(fill="x", padx=15, pady=(12, 8))
    header_row = ctk.CTkFrame(header_frame, fg_color="transparent")
    header_row.pack(fill="x", padx=14, pady=(10, 8))
    ctk.CTkLabel(
        header_row,
        text="SMTP 测试工作区",
        font=("Arial", 15, "bold"),
    ).pack(side="left")
    app.smtp_status_label = ctk.CTkLabel(
        header_row,
        text="状态：等待配置",
        font=("Arial", 11),
        text_color="gray70",
    )
    app.smtp_status_label.pack(side="right")

    config_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    config_frame.pack(fill="x", padx=15, pady=(0, 8))
    config_frame.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(config_frame, text="1. 发件配置", font=("Arial", 13, "bold")).grid(
        row=0, column=0, sticky="w", padx=12, pady=(10, 6)
    )

    provider_row = ctk.CTkFrame(config_frame, fg_color="transparent")
    provider_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
    provider_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(provider_row, text="服务商", font=("Arial", 12)).grid(
        row=0, column=0, sticky="w", pady=4
    )
    app.smtp_preset_menu = ctk.CTkOptionMenu(
        provider_row,
        values=get_preset_names(),
        variable=app.smtp_preset_var,
        command=lambda _value: app.apply_selected_preset(),
    )
    app.smtp_preset_menu.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=4)

    config_columns = ctk.CTkFrame(config_frame, fg_color="transparent")
    config_columns.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
    config_columns.grid_columnconfigure(0, weight=1)
    config_columns.grid_columnconfigure(1, weight=1)

    sender_col = ctk.CTkFrame(config_columns, fg_color="transparent")
    sender_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    sender_col.grid_columnconfigure(1, weight=1)
    app.smtp_sender_email_entry = create_labeled_entry(sender_col, "发件邮箱", 0)
    app.smtp_password_entry = create_labeled_entry(sender_col, "授权码 / 密码", 1, show="*")
    app.smtp_sender_name_entry = create_labeled_entry(sender_col, "发件人名称(可选)", 2)

    test_meta_col = ctk.CTkFrame(config_columns, fg_color="transparent")
    test_meta_col.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
    test_meta_col.grid_columnconfigure(1, weight=1)
    app.smtp_test_recipient_entry = create_labeled_entry(test_meta_col, "测试收件邮箱", 0)
    app.smtp_subject_entry = create_labeled_entry(test_meta_col, "测试主题", 1)

    config_actions = ctk.CTkFrame(config_frame, fg_color="transparent")
    config_actions.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 10))
    app.smtp_autofill_button = ctk.CTkButton(
        config_actions,
        text="根据邮箱智能识别",
        fg_color="#3A7A47",
        command=app.autofill_preset_from_email,
    )
    app.smtp_autofill_button.pack(side="left")
    app.smtp_save_button = ctk.CTkButton(
        config_actions,
        text="智能补全并保存",
        fg_color="#5A6472",
        command=app.prepare_and_save_smtp_config,
    )
    app.smtp_save_button.pack(side="left", padx=10)
    ctk.CTkButton(
        config_actions,
        text="使用当前预览填充",
        fg_color="#7D5FFF",
        command=app.sync_preview_to_smtp,
    ).pack(side="left")

    message_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    message_frame.pack(fill="x", padx=15, pady=(0, 8))
    ctk.CTkLabel(message_frame, text="2. 测试邮件", font=("Arial", 13, "bold")).pack(
        anchor="w", padx=12, pady=(10, 6)
    )
    app.smtp_body_box = ctk.CTkTextbox(
        message_frame,
        height=120,
        fg_color="#101010",
        font=("Arial", 13),
    )
    app.smtp_body_box.pack(fill="x", padx=12, pady=(0, 8))

    message_actions = ctk.CTkFrame(message_frame, fg_color="transparent")
    message_actions.pack(fill="x", padx=12, pady=(0, 10))
    app.smtp_test_button = ctk.CTkButton(
        message_actions,
        text="执行 SMTP 测试",
        fg_color="#3A7A47",
        command=app.run_smtp_test,
    )
    app.smtp_test_button.pack(side="left")
    app.smtp_auth_test_button = ctk.CTkButton(
        message_actions,
        text="预检后再测试",
        fg_color="#1F538D",
        command=app.run_auth_then_smtp_test,
    )
    app.smtp_auth_test_button.pack(side="left", padx=10)

    advanced_card = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    advanced_card.pack(fill="x", padx=15, pady=(0, 8))
    ctk.CTkLabel(advanced_card, text="3. 高级连接参数", font=("Arial", 13, "bold")).grid(
        row=0, column=0, sticky="w", padx=12, pady=(10, 6)
    )
    app.smtp_advanced_switch = ctk.CTkSwitch(
        advanced_card,
        text="显示高级参数",
        variable=app.smtp_show_advanced_var,
        command=app.toggle_advanced_smtp_fields,
    )
    app.smtp_advanced_switch.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 6))

    app.smtp_advanced_frame = ctk.CTkFrame(advanced_card, fg_color="transparent")
    app.smtp_advanced_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
    app.smtp_advanced_frame.grid_columnconfigure(1, weight=1)
    app.smtp_username_entry = create_labeled_entry(app.smtp_advanced_frame, "登录用户名", 0)
    app.smtp_host_entry = create_labeled_entry(app.smtp_advanced_frame, "SMTP Host", 1)
    app.smtp_port_entry = create_labeled_entry(app.smtp_advanced_frame, "SMTP Port", 2)
    app.smtp_dkim_selector_entry = create_labeled_entry(
        app.smtp_advanced_frame, "DKIM Selector(选填)", 3
    )
    ctk.CTkLabel(app.smtp_advanced_frame, text="Security", font=("Arial", 12)).grid(
        row=4, column=0, sticky="w", pady=6
    )
    app.smtp_security_var = tk.StringVar(value="ssl")
    app.smtp_security_menu = ctk.CTkOptionMenu(
        app.smtp_advanced_frame,
        values=["ssl", "starttls", "plain"],
        variable=app.smtp_security_var,
    )
    app.smtp_security_menu.grid(row=4, column=1, sticky="ew", padx=(12, 0), pady=6)

    pool_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    pool_frame.pack(fill="x", padx=15, pady=(0, 8))
    pool_frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(pool_frame, text="4. SMTP 账号池", font=("Arial", 13, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 6)
    )
    ctk.CTkLabel(pool_frame, text="已保存账号", font=("Arial", 12)).grid(
        row=1, column=0, sticky="w", padx=12, pady=6
    )
    app.smtp_account_menu = ctk.CTkOptionMenu(
        pool_frame,
        values=["未保存账号"],
        variable=app.smtp_account_var,
    )
    app.smtp_account_menu.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=6)

    pool_actions = ctk.CTkFrame(pool_frame, fg_color="transparent")
    pool_actions.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 8))
    ctk.CTkButton(
        pool_actions,
        text="保存到账号池",
        fg_color="#1F538D",
        command=app.save_current_account_to_pool,
    ).pack(side="left")
    ctk.CTkButton(
        pool_actions,
        text="载入选中账号",
        fg_color="#5A6472",
        command=app.load_selected_account_from_pool,
    ).pack(side="left", padx=10)
    ctk.CTkButton(
        pool_actions,
        text="删除选中账号",
        fg_color="#8A3B3B",
        command=app.delete_selected_account,
    ).pack(side="left")

    app.smtp_bulk_import_box = ctk.CTkTextbox(
        pool_frame,
        height=68,
        fg_color="#101010",
        font=("Menlo", 11),
        text_color="#D6D6D6",
    )
    app.smtp_bulk_import_box.grid(
        row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 6)
    )
    app.smtp_bulk_import_box.insert("0.0", ACCOUNT_IMPORT_HINT)
    ctk.CTkButton(
        pool_frame,
        text="批量导入账号池",
        fg_color="#3A7A47",
        command=app.import_accounts_to_pool,
    ).grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10))

    auth_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    auth_frame.pack(fill="x", padx=15, pady=(0, 8))
    ctk.CTkLabel(auth_frame, text="5. 发件域预检", font=("Arial", 13, "bold")).pack(
        anchor="w", padx=12, pady=(10, 6)
    )
    auth_actions = ctk.CTkFrame(auth_frame, fg_color="transparent")
    auth_actions.pack(fill="x", padx=12, pady=(0, 8))
    app.smtp_auth_button = ctk.CTkButton(
        auth_actions,
        text="检查当前发件域名",
        fg_color="#3B8ED0",
        command=app.run_domain_auth_check,
    )
    app.smtp_auth_button.pack(side="left")
    ctk.CTkButton(
        auth_actions,
        text="从账号池载入并检查",
        fg_color="#7D5FFF",
        command=app.load_account_and_check_domain,
    ).pack(side="left", padx=10)
    app.domain_auth_box = ctk.CTkTextbox(
        auth_frame,
        height=96,
        fg_color="#000000",
        font=("Menlo", 12),
        text_color="#00FF99",
    )
    app.domain_auth_box.pack(fill="x", padx=12, pady=(0, 10))
    app.domain_auth_box.insert("0.0", "这里会显示 SPF / DKIM / DMARC 预检结果。\n")

    result_frame = ctk.CTkFrame(parent, fg_color=APP_PANEL_ALT, border_width=1, border_color=APP_BORDER)
    result_frame.pack(fill="both", expand=True, padx=15, pady=(0, 12))
    ctk.CTkLabel(result_frame, text="6. SMTP 测试结果", font=("Arial", 13, "bold")).pack(
        anchor="w", padx=12, pady=(10, 6)
    )
    app.smtp_result_box = ctk.CTkTextbox(
        result_frame,
        height=96,
        fg_color="#000000",
        font=("Menlo", 12),
        text_color="#00FF99",
    )
    app.smtp_result_box.pack(fill="both", expand=True, padx=12, pady=(0, 10))
    app.smtp_result_box.insert("0.0", "这里会显示 SMTP 测试结果。\n")
    app.toggle_advanced_smtp_fields()


def create_labeled_entry(parent, label, row, show=None):
    ctk.CTkLabel(parent, text=label, font=("Arial", 12), text_color=APP_MUTED).grid(
        row=row, column=0, sticky="w", pady=6
    )
    entry = ctk.CTkEntry(
        parent,
        show=show or "",
        fg_color="#08111E",
        border_width=1,
        border_color=APP_BORDER,
        text_color=APP_TEXT,
    )
    entry.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=6)
    return entry
