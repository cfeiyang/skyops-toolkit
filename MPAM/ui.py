"""月度项目分配管理（MPAM）—— 现代化企业级双栏看板界面层。

保持与 excel_store.py 100% 兼容，升级特性：
1. 顶部实时 KPI 统计指标卡片（已排人员、总分配项、同月重合项目预警）；
2. 内嵌式月份前后切换器（◀ 2026年11月 ▶ + 快捷月历弹窗）；
3. 左侧卡片式录入/修改控制台 + 右侧带胶囊视觉的分配全景列表；
4. 检索中心支持人员/项目号秒级防抖联动与右侧历史轨迹审计时间轴。
"""

from __future__ import annotations

from collections import Counter
import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import List, Optional

from excel_store import (
    AssignError,
    ExcelStore,
    MonthKey,
    month_label,
    normalize_name,
    normalize_project_id,
)

FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
FONT_METRIC_VAL = ("Microsoft YaHei UI", 18, "bold")
FONT_STATUS = ("Microsoft YaHei UI", 10, "bold")
FONT_LOGIN = ("Microsoft YaHei UI", 11)

# 企业级现代配色系统
BG = "#f1f5f9"
CARD = "#ffffff"
CARD_BORDER = "#e2e8f0"
INK = "#0f172a"
MUTED = "#64748b"
OK = "#16a34a"
WARN = "#dc2626"
HINT = "#d97706"
PRIMARY = "#2563eb"
PRIMARY_DARK = "#1d4ed8"
HEADER_BG = "#0f172a"
HEADER_SUB = "#94a3b8"
FOOTER_BG = "#e2e8f0"

OLD_NONE = "不修改"

ASSIGN_COLUMNS = (
    ("person", "人员姓名", 120),
    ("project", "已分配项目号 (胶囊视图)", 320),
    ("state", "当月状态", 110),
    ("time", "最近操作时间", 170),
)
SEARCH_COLUMNS = (
    ("month", "所属月份", 130),
    ("person", "人员姓名", 130),
    ("project", "项目编号", 220),
    ("time", "分配记录时间", 180),
)
AUDIT_COLUMNS = (
    ("month", "月份", 110),
    ("project", "项目号", 150),
    ("time", "分配时间", 150),
)

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
DEFAULT_CREDENTIALS = {"username": "root", "password": "123456"}
SEARCH_DELAY_MS = 120
NAV_KEYS = {
    "Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End",
    "Return", "KP_Enter", "Escape", "Tab",
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
}


class App(tk.Tk):
    def __init__(self, store: Optional[ExcelStore] = None, skip_login: bool = False) -> None:
        super().__init__()
        self.store = store
        self.month_key: Optional[MonthKey] = None
        self.person_var = tk.StringVar()
        self.old_var = tk.StringVar()
        self.pid_var = tk.StringVar()
        self.search_mode = tk.StringVar(value="person")
        self.search_person = tk.StringVar()
        self.search_project = tk.StringVar()
        self.login_user_var = tk.StringVar()
        self.login_pass_var = tk.StringVar()

        self._search_job: Optional[str] = None
        self._all_ids: List[str] = []
        self._login_failures = 0
        self.current_user: Optional[str] = None

        self.title("月度项目分配管理 (MPAM Pro)")
        self.geometry("1160x780")
        self.minsize(1020, 680)
        self.configure(bg=BG)

        self._setup_style()
        if skip_login:
            self.current_user = "root"
            self._build_main()
        else:
            self._show_login()

    # ------------------------------------------------------------------ 样式
    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, foreground=INK, font=FONT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD, relief="solid", borderwidth=1)
        style.configure("TLabel", background=BG, foreground=INK, font=FONT)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Card.TLabel", background=CARD, foreground=INK, font=FONT)
        style.configure("CardBold.TLabel", background=CARD, foreground=INK, font=FONT_BOLD)
        style.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("MetricVal.TLabel", background=CARD, foreground=PRIMARY, font=FONT_METRIC_VAL)
        style.configure("MetricWarn.TLabel", background=CARD, foreground=HINT, font=FONT_METRIC_VAL)
        style.configure("Card.TRadiobutton", background=CARD, foreground=INK, font=FONT)
        style.configure("Title.TLabel", background=BG, foreground=INK, font=FONT_TITLE)

        style.configure("Header.TFrame", background=HEADER_BG)
        style.configure("HeaderTitle.TLabel", background=HEADER_BG, foreground="#ffffff", font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("HeaderSub.TLabel", background=HEADER_BG, foreground=HEADER_SUB, font=("Microsoft YaHei UI", 9))
        style.configure("Footer.TFrame", background=FOOTER_BG)
        style.configure("Footer.TLabel", background=FOOTER_BG, foreground=MUTED, font=("Microsoft YaHei UI", 9))

        style.configure("TButton", font=FONT, padding=(12, 6), background=CARD, foreground=INK)
        style.map("TButton", background=[("active", "#e0e7ff"), ("disabled", "#f1f5f9")])
        style.configure("Primary.TButton", font=FONT_BOLD, padding=(14, 7), background=PRIMARY, foreground="#ffffff", borderwidth=0)
        style.map("Primary.TButton", background=[("active", PRIMARY_DARK), ("disabled", "#93c5fd")], foreground=[("disabled", "#ffffff")])

        style.configure("TCombobox", padding=5)
        style.configure("TEntry", padding=5)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=FONT_BOLD, padding=(20, 9))
        style.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", PRIMARY)])

        style.configure("Status.TLabel", background=CARD, foreground=MUTED, font=FONT_STATUS)
        style.configure("StatusOk.TLabel", background=CARD, foreground=OK, font=FONT_STATUS)
        style.configure("StatusWarn.TLabel", background=CARD, foreground=WARN, font=FONT_STATUS)
        style.configure("StatusHint.TLabel", background=CARD, foreground=HINT, font=FONT_STATUS)

        style.configure("Treeview", font=FONT, rowheight=34, background=CARD, fieldbackground=CARD, borderwidth=0)
        style.configure("Treeview.Heading", font=FONT_BOLD, padding=(10, 8), background="#e2e8f0", foreground=INK, relief="flat")
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", INK)])

    # ------------------------------------------------------------------ 登录
    def _credentials(self) -> dict:
        try:
            if CONFIG_FILE.is_file():
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("username") and data.get("password") is not None:
                    return {"username": str(data["username"]), "password": str(data["password"])}
            CONFIG_FILE.write_text(json.dumps(DEFAULT_CREDENTIALS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except (OSError, ValueError):
            pass
        return dict(DEFAULT_CREDENTIALS)

    def _show_login(self) -> None:
        self.login_frame = ttk.Frame(self, padding=30)
        self.login_frame.pack(fill="both", expand=True)

        inner = ttk.Frame(self.login_frame)
        inner.place(relx=0.5, rely=0.45, anchor="center")

        card = ttk.Frame(inner, style="Card.TFrame", padding=(38, 32, 38, 28))
        card.pack()
        ttk.Label(card, text="📊 月度项目分配管理", style="CardBold.TLabel", font=FONT_TITLE).grid(row=0, column=0, columnspan=2, pady=(0, 4))
        ttk.Label(card, text="Monthly Project Allocation Management · 安全单机版", style="CardMuted.TLabel").grid(row=1, column=0, columnspan=2, pady=(0, 22))

        ttk.Label(card, text="登录账号", style="CardBold.TLabel").grid(row=2, column=0, sticky="w", pady=8)
        user_entry = ttk.Entry(card, textvariable=self.login_user_var, width=26, font=FONT_LOGIN)
        user_entry.grid(row=2, column=1, padx=(14, 0), pady=8, ipady=3)

        ttk.Label(card, text="安全密码", style="CardBold.TLabel").grid(row=3, column=0, sticky="w", pady=8)
        pass_entry = ttk.Entry(card, textvariable=self.login_pass_var, width=26, show="•", font=FONT_LOGIN)
        pass_entry.grid(row=3, column=1, padx=(14, 0), pady=8, ipady=3)

        self.login_msg = ttk.Label(card, text="", style="Card.TLabel", foreground=WARN)
        self.login_msg.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        buttons = ttk.Frame(card, style="Card.TFrame")
        buttons.grid(row=5, column=0, columnspan=2, pady=(18, 2))
        ttk.Button(buttons, text="立即登录", style="Primary.TButton", command=self._try_login).pack(side="left", padx=6)
        ttk.Button(buttons, text="退出程序", command=self.destroy).pack(side="left", padx=6)

        for entry in (user_entry, pass_entry):
            entry.bind("<Return>", lambda _e: self._try_login())
        user_entry.focus_set()

    def _try_login(self) -> None:
        expected = self._credentials()
        user = self.login_user_var.get().strip()
        password = self.login_pass_var.get()
        if user == expected["username"] and password == expected["password"]:
            self.current_user = user
            self.login_frame.destroy()
            self.login_frame = None
            self._build_main()
            return
        self._login_failures += 1
        self.login_pass_var.set("")
        if self._login_failures >= 3:
            messagebox.showerror("登录失败", "连续 3 次输入错误，程序退出。", parent=self)
            self.destroy()
            return
        self.login_msg.configure(text=f"⚠️ 用户名或密码错误，第 {self._login_failures}/3 次")

    # ------------------------------------------------------------------ 布局
    def _build_main(self) -> None:
        header = ttk.Frame(self, style="Header.TFrame", padding=(22, 14, 22, 14))
        header.pack(fill="x")
        left_h = ttk.Frame(header, style="Header.TFrame")
        left_h.pack(side="left")
        ttk.Label(left_h, text="📊 月度项目分配管理工作台", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(left_h, text="Monthly Project Allocation Management · 自动判重 / 原子保存 / 备份审计", style="HeaderSub.TLabel").pack(anchor="w", pady=(2, 0))

        right_h = ttk.Frame(header, style="Header.TFrame")
        right_h.pack(side="right")
        ttk.Button(right_h, text="📂 导入 Excel 工作簿…", style="Primary.TButton", command=self._import_excel).pack(side="right")
        self.file_label = ttk.Label(right_h, text="尚未加载工作簿", style="HeaderSub.TLabel")
        self.file_label.pack(side="right", padx=(0, 14))

        footer = ttk.Frame(self, style="Footer.TFrame", padding=(20, 6))
        footer.pack(fill="x", side="bottom")
        self.footer_left = ttk.Label(footer, text="", style="Footer.TLabel")
        self.footer_left.pack(side="left")
        self.footer_right = ttk.Label(footer, text="", style="Footer.TLabel")
        self.footer_right.pack(side="right")

        outer = ttk.Frame(self, padding=(18, 12, 18, 10))
        outer.pack(fill="both", expand=True)

        # 顶部 3 张 KPI 指标卡
        kpi_row = ttk.Frame(outer)
        kpi_row.pack(fill="x", pady=(0, 12))
        self.kpi_people_val, self.kpi_people_sub = self._create_kpi_card(kpi_row, "👥 当月已分配人员", "0 / 0 人", "覆盖率 0%")
        self.kpi_proj_val, self.kpi_proj_sub = self._create_kpi_card(kpi_row, "🏷️ 当月分配项目总数", "0 项", "人均 0.0 项")
        self.kpi_dup_val, self.kpi_dup_sub = self._create_kpi_card(kpi_row, "⚠️ 同月多人重合项目", "0 项", "无跨人员重复项目", warn=True)

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)
        self.assign_tab = ttk.Frame(self.notebook, padding=(10, 10))
        self.search_tab = ttk.Frame(self.notebook, padding=(10, 10))
        self.notebook.add(self.assign_tab, text="  📝 月度分配与修改工作台  ")
        self.notebook.add(self.search_tab, text="  🔍 全局历史检索与审计  ")
        self.notebook.enable_traversal()
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._build_assign_tab()
        self._build_search_tab()

        if self.store is not None:
            self._load_options()
        else:
            self._enter_empty_state()

    def _create_kpi_card(self, parent, title: str, init_val: str, init_sub: str, warn: bool = False):
        card = ttk.Frame(parent, style="Card.TFrame", padding=(16, 10))
        card.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Label(card, text=title, style="CardMuted.TLabel").pack(anchor="w")
        val_lbl = ttk.Label(card, text=init_val, style="MetricWarn.TLabel" if warn else "MetricVal.TLabel")
        val_lbl.pack(anchor="w", pady=(2, 2))
        sub_lbl = ttk.Label(card, text=init_sub, style="CardMuted.TLabel")
        sub_lbl.pack(anchor="w")
        return val_lbl, sub_lbl

    def _build_assign_tab(self) -> None:
        tab = self.assign_tab
        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True)

        # 左侧操作控制台卡片
        left_card = ttk.Frame(body, style="Card.TFrame", padding=(18, 16))
        left_card.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(left_card, text="1. 选择分配月份", style="CardBold.TLabel").pack(anchor="w", pady=(0, 6))
        m_row = ttk.Frame(left_card, style="Card.TFrame")
        m_row.pack(fill="x", pady=(0, 14))
        self.prev_m_btn = ttk.Button(m_row, text="◀", width=3, command=lambda: self._step_month(-1))
        self.prev_m_btn.pack(side="left")
        self.month_btn = ttk.Button(m_row, text="选择月份", command=self._open_month_picker, width=16)
        self.month_btn.pack(side="left", padx=6)
        self.next_m_btn = ttk.Button(m_row, text="▶", width=3, command=lambda: self._step_month(1))
        self.next_m_btn.pack(side="left")

        ttk.Label(left_card, text="2. 选择或新增人员", style="CardBold.TLabel").pack(anchor="w", pady=(0, 6))
        p_row = ttk.Frame(left_card, style="Card.TFrame")
        p_row.pack(fill="x", pady=(0, 14))
        self.person_box = ttk.Combobox(p_row, textvariable=self.person_var, width=16, font=FONT)
        self.person_box.pack(side="left")
        self.person_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh())
        self.person_box.bind("<KeyRelease>", self._on_assign_person_key)
        self.add_person_btn = ttk.Button(p_row, text="＋ 人员", width=8, command=self._add_person)
        self.add_person_btn.pack(side="left", padx=(8, 0))

        ttk.Label(left_card, text="3. 录入项目编号", style="CardBold.TLabel").pack(anchor="w", pady=(0, 6))
        pid_row = ttk.Frame(left_card, style="Card.TFrame")
        pid_row.pack(fill="x", pady=(0, 14))
        self.pid_box = ttk.Combobox(pid_row, textvariable=self.pid_var, width=16, font=FONT)
        self.pid_box.pack(side="left")
        self.pid_box.bind("<Return>", lambda _e: self._do_assign())
        self.pid_box.bind("<KeyRelease>", self._on_pid_change)
        self.pid_box.bind("<<ComboboxSelected>>", lambda _e: self._update_status())
        self.add_project_btn = ttk.Button(pid_row, text="＋ 项目号", width=8, command=self._add_project)
        self.add_project_btn.pack(side="left", padx=(8, 0))

        ttk.Label(left_card, text="4. 手误修改 (可选原项目号替换)", style="CardBold.TLabel").pack(anchor="w", pady=(0, 6))
        self.old_box = ttk.Combobox(left_card, textvariable=self.old_var, state="readonly", width=26, font=FONT)
        self.old_box.pack(anchor="w", pady=(0, 16))
        self.old_box.bind("<<ComboboxSelected>>", lambda _e: self._update_status())

        act_row = ttk.Frame(left_card, style="Card.TFrame")
        act_row.pack(fill="x", pady=(4, 12))
        self.assign_btn = ttk.Button(act_row, text="✓ 确认分配", style="Primary.TButton", command=self._do_assign)
        self.assign_btn.pack(side="left", fill="x", expand=True)
        self.modify_btn = ttk.Button(act_row, text="✎ 替换修改", command=self._do_modify)
        self.modify_btn.pack(side="left", padx=(8, 0))

        self.status = ttk.Label(left_card, text="", style="Status.TLabel", wraplength=260)
        self.status.pack(anchor="w", pady=(8, 0))

        # 右侧当月分配全景表
        right_card = ttk.Frame(body, style="Card.TFrame", padding=(14, 12))
        right_card.pack(side="left", fill="both", expand=True)

        top_bar = ttk.Frame(right_card, style="Card.TFrame")
        top_bar.pack(fill="x", pady=(0, 8))
        self.summary = ttk.Label(top_bar, text="请先点击右上角「导入 Excel 工作簿…」", style="CardBold.TLabel")
        self.summary.pack(side="left")

        wrap = ttk.Frame(right_card, style="Card.TFrame")
        wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in ASSIGN_COLUMNS], show="headings", height=14)
        for key, title, width in ASSIGN_COLUMNS:
            self.tree.heading(key, text=title, anchor="w")
            self.tree.column(key, width=width, anchor="w", stretch=(key == "project"))
        self.tree.tag_configure("done", foreground=INK)
        self.tree.tag_configure("dup", background="#fef3c7", foreground="#92400e")
        self.tree.tag_configure("todo", foreground="#94a3b8")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select_person)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_search_tab(self) -> None:
        tab = self.search_tab
        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True)

        # 左侧：检索条件 + 结果表
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        card = ttk.Frame(left, style="Card.TFrame", padding=(18, 16))
        card.pack(fill="x")

        row1 = ttk.Frame(card, style="Card.TFrame")
        row1.pack(fill="x", pady=(0, 10))
        ttk.Label(row1, text="检索方式", style="Card.TLabel").pack(side="left")
        ttk.Radiobutton(
            row1, text="按人员", value="person",
            variable=self.search_mode, style="Card.TRadiobutton", command=self._on_mode_changed,
        ).pack(side="left", padx=(10, 0))
        ttk.Radiobutton(
            row1, text="按项目号", value="project",
            variable=self.search_mode, style="Card.TRadiobutton", command=self._on_mode_changed,
        ).pack(side="left", padx=(18, 0))

        row2 = ttk.Frame(card, style="Card.TFrame")
        row2.pack(fill="x")
        ttk.Label(row2, text="人员", style="Card.TLabel").pack(side="left")
        self.search_person_box = ttk.Combobox(row2, textvariable=self.search_person, width=18, font=FONT)
        self.search_person_box.pack(side="left", padx=(8, 18))
        ttk.Label(row2, text="项目号", style="Card.TLabel").pack(side="left")
        self.search_project_box = ttk.Combobox(row2, textvariable=self.search_project, width=24, font=FONT)
        self.search_project_box.pack(side="left", padx=(8, 14))
        ttk.Button(row2, text="查询", style="Primary.TButton", command=self._do_search).pack(side="left")

        self.search_count = ttk.Label(card, text="导入文件后，这里会显示检索结果", style="Muted.TLabel")
        self.search_count.pack(anchor="w", pady=(10, 0))

        # 输入即查（防抖），不用点「查询」；下拉选择后立即查
        self.search_person_box.bind("<KeyRelease>", self._on_person_key)
        self.search_person_box.bind("<<ComboboxSelected>>", lambda _e: self._schedule_search(0))
        self.search_person_box.bind("<Return>", lambda _e: self._do_search())
        self.search_project_box.bind("<KeyRelease>", self._on_project_key)
        self.search_project_box.bind("<<ComboboxSelected>>", lambda _e: self._schedule_search(0))
        self.search_project_box.bind("<Return>", lambda _e: self._do_search())

        wrap = ttk.Frame(left)
        wrap.pack(fill="both", expand=True)
        self.search_tree = ttk.Treeview(wrap, columns=[c[0] for c in SEARCH_COLUMNS], show="headings", height=16)
        for key, title, width in SEARCH_COLUMNS:
            self.search_tree.heading(key, text=title, anchor="w")
            self.search_tree.column(key, width=width, anchor="w", stretch=(key == "project"))
        self.search_tree.bind("<<TreeviewSelect>>", self._on_search_select)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.search_tree.yview)
        self.search_tree.configure(yscrollcommand=scroll.set)
        self.search_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # 右侧：审计时间轴卡片
        right_card = ttk.Frame(body, style="Card.TFrame", padding=(14, 12))
        right_card.pack(side="right", fill="y", padx=(12, 0))
        ttk.Label(right_card, text="📜 分配轨迹审计", style="CardBold.TLabel").pack(anchor="w", pady=(0, 6))
        self.audit_title = ttk.Label(
            right_card, text="选中左侧任意记录，这里显示该人员的全部历史分配", style="CardMuted.TLabel", wraplength=280
        )
        self.audit_title.pack(anchor="w", pady=(0, 8))
        awrap = ttk.Frame(right_card, style="Card.TFrame")
        awrap.pack(fill="both", expand=True)
        self.audit_tree = ttk.Treeview(awrap, columns=[c[0] for c in AUDIT_COLUMNS], show="headings", height=22)
        for key, title, width in AUDIT_COLUMNS:
            self.audit_tree.heading(key, text=title, anchor="w")
            self.audit_tree.column(key, width=width, anchor="w")
        ascroll = ttk.Scrollbar(awrap, orient="vertical", command=self.audit_tree.yview)
        self.audit_tree.configure(yscrollcommand=ascroll.set)
        self.audit_tree.pack(side="left", fill="both", expand=True)
        ascroll.pack(side="right", fill="y")

    # ------------------------------------------------------------------ 月份选择
    def _open_month_picker(self) -> None:
        top = tk.Toplevel(self)
        top.title("选择月份")
        top.transient(self)
        top.resizable(False, False)
        try:
            top.grab_set()
        except tk.TclError:
            pass

        state = {"year": self.month_key[0] if self.month_key else datetime.now().year}

        header = ttk.Frame(top, padding=(10, 10, 10, 4))
        header.pack(fill="x")
        ttk.Button(header, text="◀", width=3, command=lambda: step(-1)).pack(side="left")
        year_label = ttk.Label(
            header, text="", width=10, anchor="center",
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        year_label.pack(side="left", expand=True)
        ttk.Button(header, text="▶", width=3, command=lambda: step(1)).pack(side="right")

        body = ttk.Frame(top, padding=(10, 4, 10, 12))
        body.pack()

        def choose(month: int) -> None:
            self._set_month((state["year"], month))
            top.destroy()

        def render() -> None:
            for child in body.winfo_children():
                child.destroy()
            year_label.configure(text=f"{state['year']} 年")
            for index in range(1, 13):
                row_no, col_no = divmod(index - 1, 4)
                mark = " ●" if self.month_key == (state["year"], index) else ""
                ttk.Button(
                    body, text=f"{index} 月{mark}", width=8,
                    command=lambda m=index: choose(m),
                ).grid(row=row_no, column=col_no, padx=3, pady=3)

        def step(delta: int) -> None:
            state["year"] += delta
            render()

        top.bind("<Escape>", lambda _e: top.destroy())
        render()
        self.update_idletasks()
        x = self.month_btn.winfo_rootx()
        y = self.month_btn.winfo_rooty() + self.month_btn.winfo_height() + 2
        top.geometry(f"+{x}+{y}")

    def _set_month(self, key: MonthKey) -> None:
        self.month_key = key
        self._update_month_button()
        self._refresh()

    def _step_month(self, delta: int) -> None:
        if self.store is None:
            return
        year, month = self.month_key if self.month_key else (datetime.now().year, datetime.now().month)
        total = year * 12 + (month - 1) + delta
        self._set_month((total // 12, total % 12 + 1))

    def _update_month_button(self) -> None:
        text = month_label(self.month_key) if self.month_key else "选择月份"
        self.month_btn.configure(text=text)

    def _current_key(self) -> Optional[MonthKey]:
        key = self.month_key
        if not key:
            return None
        year, month = key
        if not 1900 <= year <= 2200 or not 1 <= month <= 12:
            return None
        return key

    # ------------------------------------------------------------------ 导入
    def _import_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要编辑的 Excel 文件",
            parent=self,
            filetypes=[("Excel 工作簿", "*.xlsx"), ("所有文件", "*.*")],
        )
        if not path:
            return
        self._open_workbook(path, notify=True)

    def _open_workbook(self, path, notify: bool = False) -> None:
        try:
            store = ExcelStore(path).load()
        except AssignError as error:
            messagebox.showerror("导入失败", str(error), parent=self)
            return
        except Exception as error:  # 文件损坏、格式不对等
            messagebox.showerror("导入失败", f"{type(error).__name__}: {error}", parent=self)
            return
        self.store = store
        self._load_options()
        if notify:
            messagebox.showinfo(
                "导入成功", "文件已打开。\n\n之后的分配会直接写回这个 Excel 文件。", parent=self
            )

    # ------------------------------------------------------------------ 数据
    def _load_options(self) -> None:
        keys = self.store.month_keys()
        today = datetime.now()
        today_key = (today.year, today.month)
        if today_key in keys:
            self.month_key = today_key
        elif keys:
            earlier = [key for key in keys if key <= today_key]
            self.month_key = earlier[-1] if earlier else keys[0]
        else:
            self.month_key = today_key
        self._update_month_button()

        people = self.store.people()
        self.person_box["values"] = people
        if people:
            self.person_var.set(people[0])
        self.search_person_box["values"] = people
        self._all_ids = self.store.all_project_ids()
        self.search_project_box["values"] = self._all_ids
        self.pid_box["values"] = self._all_ids

        self.file_label.configure(text="")
        self.search_count.configure(text="输入条件即自动检索")
        self._apply_enabled(True)
        self._refresh()

    def _enter_empty_state(self) -> None:
        today = datetime.now()
        self.month_key = (today.year, today.month)
        self._update_month_button()

        self.person_box["values"] = []
        self.person_var.set("")
        self.old_box["values"] = [OLD_NONE]
        self.old_var.set(OLD_NONE)
        self.pid_var.set("")
        self.search_person.set("")
        self.search_project.set("")
        self.search_person_box["values"] = []
        self.search_project_box["values"] = []
        self.pid_box["values"] = []
        self._all_ids = []

        self.tree.delete(*self.tree.get_children())
        self.search_tree.delete(*self.search_tree.get_children())
        self.audit_tree.delete(*self.audit_tree.get_children())
        self.file_label.configure(text="尚未加载工作簿")
        self.summary.configure(text="请先点击右上角「导入 Excel 工作簿…」")
        self.audit_title.configure(text="选中左侧任意记录，这里显示该人员的全部历史分配")
        self.search_count.configure(text="导入文件后，这里会显示检索结果")
        self._apply_enabled(False)
        self._set_status("请先点击右上角「导入 Excel 工作簿…」选择 Excel 文件", MUTED)
        self._zero_kpi()
        self._update_footer()

    def _apply_enabled(self, enabled: bool) -> None:
        state = ["!disabled"] if enabled else ["disabled"]
        for widget in (
            self.prev_m_btn, self.next_m_btn, self.month_btn,
            self.person_box, self.add_person_btn, self.old_box,
            self.pid_box, self.add_project_btn,
            self.search_person_box, self.search_project_box,
        ):
            widget.state(state)
        if not enabled:
            self.assign_btn.state(["disabled"])
            self.modify_btn.state(["disabled"])

    def _update_footer(self) -> None:
        if not hasattr(self, "footer_left"):
            return
        self.footer_left.configure(text=f"账号：{self.current_user or '—'}")
        if self.store is not None:
            self.footer_right.configure(
                text=f"上次保存：{self.store.last_saved}" if self.store.last_saved else "数据已加载"
            )
        else:
            self.footer_right.configure(text="尚未加载数据")

    # ------------------------------------------------------------------ KPI
    def _update_kpi(self, assigned: int, total_people: int, total_projects: int, dup_count: int) -> None:
        coverage = (assigned * 100.0 / total_people) if total_people else 0.0
        per_capita = (total_projects / total_people) if total_people else 0.0
        self.kpi_people_val.configure(text=f"{assigned} / {total_people} 人")
        self.kpi_people_sub.configure(text=f"覆盖率 {coverage:.0f}%")
        self.kpi_proj_val.configure(text=f"{total_projects} 项")
        self.kpi_proj_sub.configure(text=f"人均 {per_capita:.1f} 项")
        self.kpi_dup_val.configure(text=f"{dup_count} 项")
        self.kpi_dup_sub.configure(text="存在跨人员重复项目" if dup_count else "无跨人员重复项目")

    def _zero_kpi(self) -> None:
        if not hasattr(self, "kpi_people_val"):
            return
        self.kpi_people_val.configure(text="0 / 0 人")
        self.kpi_people_sub.configure(text="覆盖率 0%")
        self.kpi_proj_val.configure(text="0 项")
        self.kpi_proj_sub.configure(text="人均 0.0 项")
        self.kpi_dup_val.configure(text="0 项")
        self.kpi_dup_sub.configure(text="无跨人员重复项目")

    # ------------------------------------------------------------------ 刷新
    def _refresh(self) -> None:
        if self.store is None:
            self._zero_kpi()
            return
        key = self._current_key()
        self.tree.delete(*self.tree.get_children())
        if key is None:
            self.summary.configure(text="请选择有效的月份")
            self._zero_kpi()
            return
        people = self.store.people()
        assigned_people = 0
        total_projects = 0
        max_display = 0

        # 当月跨人员重复项目统计（与高亮同口径）
        cross_counter: Counter = Counter()
        for name in people:
            for project in self.store.projects_of(key, name):
                cross_counter[project] += 1

        for name in people:
            projects = self.store.projects_of(key, name)
            joined = "  ".join(f"[{p}]" for p in projects)
            max_display = max(max_display, len(joined))
            if projects:
                assigned_people += 1
                total_projects += len(projects)
                dup_hit = any(cross_counter[p] > 1 for p in projects)
                self.tree.insert(
                    "", "end",
                    values=(name, joined, f"{len(projects)} 个", self.store.assigned_at(key, name) or "—"),
                    tags=("done", "dup") if dup_hit else ("done",),
                )
            else:
                self.tree.insert("", "end", values=(name, "—", "未分配", ""), tags=("todo",))
        self.tree.column("project", width=max(260, min(max_display * 13 + 24, 760)))
        self.summary.configure(text=f"{month_label(key)} 分配情况　{assigned_people}/{len(people)} 人已分配")

        dup_count = sum(1 for count in cross_counter.values() if count > 1)
        self._update_kpi(assigned_people, len(people), total_projects, dup_count)

        self._all_ids = self.store.all_project_ids()
        self.search_project_box["values"] = self._all_ids
        self.pid_box["values"] = self._all_ids
        self._refresh_old_options()
        self._update_status()
        self._update_footer()

    def _refresh_old_options(self) -> None:
        key, person = self._current_key(), normalize_name(self.person_var.get())
        projects = self.store.projects_of(key, person) if key and person else []
        values = [OLD_NONE] + projects
        self.old_box["values"] = values
        if self.old_var.get() not in values:
            self.old_var.set(OLD_NONE)

    def _selected_old(self) -> str:
        value = self.old_var.get()
        return "" if value in ("", OLD_NONE) else value

    def _update_status(self) -> None:
        if self.store is None:
            return
        key = self._current_key()
        person = normalize_name(self.person_var.get())
        project = normalize_project_id(self.pid_var.get())
        old = self._selected_old()
        if key is None or not person:
            self._set_status("请选择月份和人员", MUTED)
            self.assign_btn.state(["disabled"])
            self.modify_btn.state(["disabled"])
            return

        existing = self.store.projects_of(key, person)
        self.assign_btn.state(["!disabled"] if (project and project not in existing) else ["disabled"])
        modify_ok = bool(old and project and project != old and project not in existing)
        self.modify_btn.state(["!disabled"] if modify_ok else ["disabled"])

        if old:
            if not project:
                self._set_status(f"修改：请为「{old}」输入新项目号", HINT)
            elif project == old:
                self._set_status(f"✗ 新项目号与「{old}」相同，无需修改", WARN)
            elif project in existing:
                self._set_status(f"⚠ {person} · {month_label(key)} 已分配过「{project}」，不能重复", WARN)
            else:
                self._set_status(f"✓ 将把「{old}」修改为「{project}」", OK)
            return

        if project and project in existing:
            self._set_status(f"⚠ {person} · {month_label(key)} 已分配过项目号「{project}」，不能重复分配", WARN)
        elif project:
            others = [name for name in self.store.who_has(key, project) if name != person]
            if others:
                self._set_status(
                    f"提示：项目号「{project}」{month_label(key)} 已分配给 {'、'.join(others)}，请确认是否重复使用",
                    HINT,
                )
            else:
                self._set_status(f"✓ {person} · {month_label(key)} 可以分配「{project}」", OK)
        else:
            if existing:
                self._set_status(
                    f"{person} · {month_label(key)} 已有 {len(existing)} 个项目号：{'、'.join(existing)}",
                    HINT,
                )
            else:
                self._set_status(f"✓ {person} · {month_label(key)} 尚未分配，可录入项目号", OK)

    def _set_status(self, text: str, color: str) -> None:
        style = {
            OK: "StatusOk.TLabel",
            WARN: "StatusWarn.TLabel",
            HINT: "StatusHint.TLabel",
        }.get(color, "Status.TLabel")
        self.status.configure(text=text, style=style)

    def _on_pid_change(self, event=None) -> None:
        if event is not None and event.keysym in NAV_KEYS:
            self._update_status()
            return
        if self.store is not None:
            self._autocomplete(
                self.pid_box, normalize_project_id(self.pid_var.get()), self._all_ids
            )
        self._update_status()

    def _on_assign_person_key(self, event=None) -> None:
        if event is not None and event.keysym in NAV_KEYS:
            return
        if self.store is None:
            return
        self._autocomplete(
            self.person_box, normalize_name(self.person_var.get()), self.store.people()
        )
        self._refresh_old_options()
        self._update_status()

    def _on_tree_select_person(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], "values")
        if values:
            self.person_var.set(values[0])
            self._refresh_old_options()
            self._update_status()

    # ------------------------------------------------------------------ 动作
    def _add_person(self) -> None:
        if self.store is None:
            return
        name = simpledialog.askstring("新增人员", "输入姓名：", parent=self)
        if not name:
            return
        try:
            person = self.store.add_person(name)
        except AssignError as error:
            messagebox.showwarning("无法新增", str(error), parent=self)
            return
        people = self.store.people()
        self.person_box["values"] = people
        self.search_person_box["values"] = people
        self.person_var.set(person)
        self._refresh()
        self._set_status(f"✓ 已新增人员：{person}", OK)

    def _add_project(self) -> None:
        if self.store is None:
            return
        project = simpledialog.askstring(
            "新增项目号", "输入项目号：", parent=self, initialvalue=self.pid_var.get().strip()
        )
        if not project:
            return
        try:
            added = self.store.add_project(project)
        except AssignError as error:
            messagebox.showwarning("无法新增", str(error), parent=self)
            return
        self._all_ids = self.store.all_project_ids()
        self.pid_box["values"] = self._all_ids
        self.search_project_box["values"] = self._all_ids
        self.pid_var.set(added)
        self._update_status()
        self._set_status(f"✓ 已新增项目号：{added}", OK)

    def _ensure_person(self) -> Optional[str]:
        """分配人员：表里没有就自动新增，返回归一化后的姓名。"""
        person = normalize_name(self.person_var.get())
        if not person:
            return None
        if person in self.store.people():
            return person
        if person in self.store.duplicate_people:
            messagebox.showwarning("无法分配", f"「{person}」有重名行，请先手工处理。", parent=self)
            return None
        try:
            added = self.store.add_person(person)
        except AssignError as error:
            messagebox.showwarning("无法新增人员", str(error), parent=self)
            return None
        people = self.store.people()
        self.person_box["values"] = people
        self.search_person_box["values"] = people
        self.person_var.set(added)
        self._set_status(f"✓ 已新增人员：{added}", OK)
        return added

    def _do_assign(self) -> None:
        if self.store is None:
            return
        key = self._current_key()
        person = self._ensure_person()
        if key is None or not person:
            return
        try:
            project = self.store.assign(key, person, self.pid_var.get())
        except AssignError as error:
            self._refresh()
            self._set_status(f"✗ {error}", WARN)
            messagebox.showwarning("无法分配", str(error), parent=self)
            return
        self.pid_var.set("")
        self._refresh()
        self._set_status(f"✓ 分配成功：{person} · {month_label(key)} · 项目号 {project}", OK)

    def _do_modify(self) -> None:
        if self.store is None:
            return
        key, person = self._current_key(), normalize_name(self.person_var.get())
        old = self._selected_old()
        if key is None or not person or not old:
            messagebox.showwarning("无法修改", "请先选择要修改的原项目号。", parent=self)
            return
        try:
            new = self.store.replace_project(key, person, old, self.pid_var.get())
        except AssignError as error:
            self._refresh()
            self._set_status(f"✗ {error}", WARN)
            messagebox.showwarning("无法修改", str(error), parent=self)
            return
        self.pid_var.set("")
        self._refresh()
        self._set_status(f"✓ 已修改：{person} · {month_label(key)} · {old} → {new}", OK)

    # ------------------------------------------------------------------ 检索
    def _on_tab_changed(self, _event=None) -> None:
        """切到检索页时自动按当前条件刷新一次，不用再点「查询」。"""
        if self.store is None or not hasattr(self, "search_tree"):
            return
        try:
            current = self.notebook.index(self.notebook.select())
        except tk.TclError:
            return
        if current == 1:
            self._search_now()

    def _on_mode_changed(self) -> None:
        box = self.search_person_box if self.search_mode.get() == "person" else self.search_project_box
        try:
            box.focus()
        except tk.TclError:
            pass
        self._schedule_search(0)

    def _on_person_key(self, event=None) -> None:
        if event is not None and event.keysym in NAV_KEYS:
            self._schedule_search()
            return
        self._filter_person_values()
        self._schedule_search()

    def _on_project_key(self, event=None) -> None:
        if event is not None and event.keysym in NAV_KEYS:
            self._schedule_search()
            return
        self._filter_project_values()
        self._schedule_search()

    def _autocomplete(self, box, text: str, candidates: List[str]) -> None:
        """输入即联想：前缀命中的排前面、包含命中的排后面，并自动展开下拉。"""
        if text:
            prefix = [c for c in candidates if c.startswith(text)]
            contains = [c for c in candidates if text in c and not c.startswith(text)]
            values = prefix + contains
        else:
            values = list(candidates)
        box["values"] = values
        if text and values:
            box.event_generate("<Down>")

    def _filter_person_values(self) -> None:
        """按已输入的文本过滤人员下拉候选。"""
        if self.store is None:
            return
        self._autocomplete(
            self.search_person_box, normalize_name(self.search_person.get()), self.store.people()
        )

    def _filter_project_values(self) -> None:
        """按已输入的文本过滤项目号下拉候选。"""
        if self.store is None:
            return
        self._autocomplete(
            self.search_project_box, normalize_project_id(self.search_project.get()), self._all_ids
        )

    def _schedule_search(self, delay_ms: int = SEARCH_DELAY_MS) -> None:
        """防抖：停笔 delay_ms 毫秒后才查询。"""
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except tk.TclError:
                pass
            self._search_job = None
        self._search_job = self.after(delay_ms, self._search_now)

    def _search_now(self) -> None:
        self._search_job = None
        self._do_search()

    def _do_search(self) -> None:
        self.search_tree.delete(*self.search_tree.get_children())
        if self.store is None:
            self.search_count.configure(text="请先导入 Excel 文件")
            return

        if self.search_mode.get() == "person":
            text = normalize_name(self.search_person.get())
            if not text:
                self.search_count.configure(text="输入姓名或从下拉选择")
                return
            rows = self.store.search_people(text)
            for key, name, pid, when in rows:
                self.search_tree.insert("", "end", values=(month_label(key), name, pid, when or "—"))
            self.search_count.configure(text=f"人员「{text}」：共 {len(rows)} 条记录")
            return

        project = normalize_project_id(self.search_project.get())
        if not project:
            self.search_count.configure(text="输入项目号或从下拉选择")
            return
        rows = self.store.search_by_project(project)
        if not rows:
            close = [pid for pid in self._all_ids if project in pid]
            if close:
                self.search_count.configure(
                    text=f"没有「{project}」，相近的有：{'、'.join(close[:8])}"
                )
            else:
                self.search_count.configure(text=f"项目号「{project}」：共 0 条记录")
            return
        for key, name, pid, when in rows:
            self.search_tree.insert("", "end", values=(month_label(key), name, pid, when or "—"))
        self.search_count.configure(text=f"项目号「{project}」：共 {len(rows)} 条记录")

    # ------------------------------------------------------------------ 审计时间轴
    def _on_search_select(self, _event=None) -> None:
        self.audit_tree.delete(*self.audit_tree.get_children())
        if self.store is None:
            return
        sel = self.search_tree.selection()
        if not sel:
            return
        values = self.search_tree.item(sel[0], "values")
        if not values:
            return
        name = values[1]  # SEARCH_COLUMNS: 月份, 人员, 项目号, 时间
        rows = self.store.search_by_person(name)
        self.audit_title.configure(text=f"「{name}」全部历史分配，共 {len(rows)} 条")
        for key, person, pid, when in rows:
            self.audit_tree.insert("", "end", values=(month_label(key), pid, when or "—"))


def run(store: Optional[ExcelStore] = None) -> None:
    App(store).mainloop()
