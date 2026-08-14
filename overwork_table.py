"""
團隊加班與請假管理系統
Run: python overwork_table.py
Build: pyinstaller --onefile --noconsole overwork_table.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import csv
import os
import io
from datetime import datetime

import database
import parser as att_parser

# ─────────────────────────── 共用常數 ───────────────────────────

LEAVE_TYPES = ["黑假", "WFH", "病假", "事假", "特休", "生理假", "因公外出", "出勤確認", "備註說明"]

COLORS = {
    "bg": "#f4f6fb",
    "header": "#4f46e5",
    "header_text": "#ffffff",
    "row_odd": "#ffffff",
    "row_even": "#f0f0ff",
    "weekend": "#e8f4ff",
    "select": "#c7d2fe",
    "danger": "#ef4444",
    "success": "#10b981",
    "warning": "#f59e0b",
    "accent": "#6366f1",
}

FONT_MAIN  = ("Microsoft JhengHei UI", 10)
FONT_BOLD  = ("Microsoft JhengHei UI", 10, "bold")
FONT_TITLE = ("Microsoft JhengHei UI", 12, "bold")
FONT_MONO  = ("Consolas", 10)


# ─────────────────────────── 工具函式 ───────────────────────────

def make_months_list():
    """產生最近 24 個月的 YYYY/MM 選項清單（由新到舊）"""
    now = datetime.now()
    result = []
    for i in range(24):
        m = (now.month - i - 1) % 12 + 1
        y = now.year - ((now.month - i - 1) // 12 if (now.month - i - 1) >= 0 else (now.month - i) // 12 + 1)
        result.append(f"{y}/{m:02d}")
    return result


def current_ym():
    now = datetime.now()
    return f"{now.year}/{now.month:02d}"


# ─────────────────────────── 主視窗 ────────────────────────────

class OverworkApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("團隊加班與請假管理系統")
        self.geometry("1300x820")
        self.minsize(1000, 600)
        self.configure(bg=COLORS["bg"])

        # 初始化資料庫
        database.init_db()

        self._build_style()
        self._build_header()
        self._build_notebook()
        self._build_statusbar()

        # 初始載入
        self.after(100, self.refresh_all)

    # ────────── 樣式 ──────────

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background=COLORS["bg"])
        style.configure("TLabel", background=COLORS["bg"], font=FONT_MAIN)
        style.configure("TButton", font=FONT_MAIN, padding=4)
        style.configure("Accent.TButton", background=COLORS["accent"], foreground="#fff", font=FONT_BOLD, padding=(8, 4))
        style.map("Accent.TButton", background=[("active", "#4338ca")])

        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", font=FONT_BOLD, padding=(12, 6), background="#e2e5f0")
        style.map("TNotebook.Tab", background=[("selected", COLORS["header"])],
                  foreground=[("selected", "#fff")])

        style.configure("Heading.TLabel", font=FONT_TITLE, background=COLORS["bg"], foreground=COLORS["header"])
        style.configure("Card.TFrame", background="#ffffff", relief="groove")

        style.configure("Treeview", rowheight=26, font=FONT_MAIN, background=COLORS["row_odd"],
                        fieldbackground=COLORS["row_odd"])
        style.configure("Treeview.Heading", font=FONT_BOLD, background=COLORS["header"],
                        foreground=COLORS["header_text"], relief="flat")
        style.map("Treeview", background=[("selected", COLORS["select"])], foreground=[("selected", "#000")])

    # ────────── 頂部標題 ──────────

    def _build_header(self):
        hdr = tk.Frame(self, bg=COLORS["header"], height=56)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="📊  團隊加班與請假管理系統",
                 bg=COLORS["header"], fg="#fff",
                 font=("Microsoft JhengHei UI", 14, "bold")).pack(side="left", padx=20, pady=10)
        tk.Label(hdr, text="Overwork & Leave Management",
                 bg=COLORS["header"], fg="#c7d2fe",
                 font=("Microsoft JhengHei UI", 10)).pack(side="left", pady=10)

    # ────────── Notebook 頁籤 ──────────

    def _build_notebook(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(6, 0))
        self.nb = nb

        self.tab_import  = self._tab_import(nb)
        self.tab_ot      = self._tab_overtime(nb)
        self.tab_leave   = self._tab_leave(nb)
        self.tab_stats   = self._tab_stats(nb)

        nb.add(self.tab_import, text="  📥 批量匯入  ")
        nb.add(self.tab_ot,     text="  ⏱ 加班紀錄  ")
        nb.add(self.tab_leave,  text="  📅 請假紀錄  ")
        nb.add(self.tab_stats,  text="  📈 月度統計  ")

    # ────────── 狀態列 ──────────

    def _build_statusbar(self):
        sb = tk.Frame(self, bg="#e2e5f0", height=24)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self.status_var = tk.StringVar(value="就緒")
        tk.Label(sb, textvariable=self.status_var, bg="#e2e5f0", fg="#555",
                 font=("Microsoft JhengHei UI", 9), anchor="w").pack(side="left", padx=10, pady=3)
        tk.Label(sb, text="attendance.db", bg="#e2e5f0", fg="#999",
                 font=("Microsoft JhengHei UI", 9)).pack(side="right", padx=10)

    def set_status(self, msg):
        self.status_var.set(msg)
        self.update_idletasks()

    # ═══════════════════════════════════════════════
    # Tab 1：批量匯入
    # ═══════════════════════════════════════════════

    def _tab_import(self, nb):
        f = ttk.Frame(nb)

        # ── 頂部控制列 ──
        ctrl = ttk.Frame(f)
        ctrl.pack(fill="x", padx=12, pady=(10, 4))

        ttk.Label(ctrl, text="預設年份：", font=FONT_BOLD).pack(side="left")
        self.import_year_var = tk.StringVar(value=str(datetime.now().year))
        ttk.Spinbox(ctrl, from_=2020, to=2030, textvariable=self.import_year_var,
                    width=6, font=FONT_MAIN).pack(side="left", padx=(0, 12))

        ttk.Button(ctrl, text="🔍 智能解析（預覽）", style="Accent.TButton",
                   command=self._do_parse_preview).pack(side="left", padx=4)
        ttk.Button(ctrl, text="📋 載入範例資料", command=self._load_sample).pack(side="left", padx=4)
        ttk.Button(ctrl, text="🗑 清空輸入", command=self._clear_import).pack(side="left", padx=4)

        # ── 主要內容區（左輸入 / 右預覽）──
        panes = ttk.PanedWindow(f, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=12, pady=6)

        # 左：文字輸入
        left_card = ttk.LabelFrame(panes, text=" 貼上原始打卡記錄文字 ", padding=6)
        self.import_text = tk.Text(left_card, font=FONT_MONO, wrap="word", undo=True,
                                   bg="#fafafa", relief="flat", borderwidth=1)
        self.import_text.pack(fill="both", expand=True)
        panes.add(left_card, weight=1)

        # 右：預覽區（兩個子 Treeview）
        right_card = ttk.LabelFrame(panes, text=" 解析預覽 ", padding=6)
        panes.add(right_card, weight=2)

        self.preview_nb = ttk.Notebook(right_card)
        self.preview_nb.pack(fill="both", expand=True)

        # 加班預覽表
        ot_frame = ttk.Frame(self.preview_nb)
        self.preview_nb.add(ot_frame, text="  加班記錄  ")
        self.prev_ot_tree = self._make_ot_treeview(ot_frame, readonly=True)

        # 請假預覽表
        lv_frame = ttk.Frame(self.preview_nb)
        self.preview_nb.add(lv_frame, text="  請假記錄  ")
        self.prev_lv_tree = self._make_lv_treeview(lv_frame, readonly=True)

        # ── 底部確認列 ──
        btn_row = ttk.Frame(f)
        btn_row.pack(fill="x", padx=12, pady=(4, 10))
        self.import_count_var = tk.StringVar(value="尚未解析")
        ttk.Label(btn_row, textvariable=self.import_count_var, foreground="#555").pack(side="left", padx=6)
        ttk.Button(btn_row, text="✅ 確認匯入資料庫", style="Accent.TButton",
                   command=self._do_import).pack(side="right", padx=4)
        ttk.Button(btn_row, text="❌ 取消 / 清除預覽", command=self._clear_preview).pack(side="right", padx=4)

        # 儲存解析結果
        self._parsed_ot = []
        self._parsed_lv = []

        return f

    def _do_parse_preview(self):
        raw = self.import_text.get("1.0", "end").strip()
        if not raw:
            messagebox.showwarning("提示", "請先輸入打卡記錄文字", parent=self)
            return

        year = int(self.import_year_var.get() or datetime.now().year)
        self.set_status("解析中...")
        try:
            ot_list, lv_list, *_ = att_parser.parse_raw_text(raw, default_year=year)
        except Exception as e:
            messagebox.showerror("解析失敗", str(e), parent=self)
            self.set_status("解析失敗")
            return

        self._parsed_ot = ot_list
        self._parsed_lv = lv_list

        self._refresh_preview_trees()
        self.import_count_var.set(f"解析完成：加班 {len(ot_list)} 筆 / 請假 {len(lv_list)} 筆")
        self.set_status(f"解析完成：加班 {len(ot_list)} 筆，請假 {len(lv_list)} 筆")

    def _refresh_preview_trees(self):
        self.prev_ot_tree.delete(*self.prev_ot_tree.get_children())
        for i, r in enumerate(self._parsed_ot):
            tag = "even" if i % 2 == 0 else "odd"
            if "假日" in r.get("note", ""):
                tag = "weekend"
            self.prev_ot_tree.insert("", "end", values=(
                r["date"], r["name"], r["time"], f"{r['hours']:.1f}",
                r["note"], r["reason"]
            ), tags=(tag,))

        self.prev_lv_tree.delete(*self.prev_lv_tree.get_children())
        for i, r in enumerate(self._parsed_lv):
            tag = "even" if i % 2 == 0 else "odd"
            self.prev_lv_tree.insert("", "end", values=(
                r["date"], r["name"], r["leave_type"], r["duration"],
                f"{r['google_comp_days']:.1f}", r["reason"]
            ), tags=(tag,))

    def _do_import(self):
        if not self._parsed_ot and not self._parsed_lv:
            messagebox.showwarning("提示", "請先按「智能解析」確認資料", parent=self)
            return

        try:
            database.bulk_insert(self._parsed_ot, self._parsed_lv)
        except Exception as e:
            messagebox.showerror("匯入失敗", str(e), parent=self)
            return

        messagebox.showinfo("匯入完成",
                            f"已匯入：加班 {len(self._parsed_ot)} 筆、請假 {len(self._parsed_lv)} 筆",
                            parent=self)
        self._parsed_ot.clear()
        self._parsed_lv.clear()
        self._clear_preview()
        self.refresh_all()
        self.set_status("資料匯入完成")

    def _load_sample(self):
        sample = """\
7/27 Benny Daniel 19:00-22:30 處理 GDL L10 + L11 Pre dry run Eden 早上未刷卡，申請出勤確認

7/28 Benny Daniel 19:00-22:30 處理 GDL L11 Test YiWen 生理假一天 Xavier 黑假一天

7/29 Benny Daniel 19:00-22:30 處理 GDL L11 Test Eden 早上未刷卡，申請出勤確認

0731 Eden 特休一天 Winnie 事假一天，處理搬家事宜

7/20 Benny 19:00-23:00 整理 GDL SFC 與 MTF init Winnie 病假一天 Cora 忘了帶卡，待補出勤確認

7/24 Winnie 病假一天 Eden 黑假半天，ＷＦＨ Benny 19:00-22:00 處理 RMC issue
"""
        self.import_text.delete("1.0", "end")
        self.import_text.insert("1.0", sample)

    def _clear_import(self):
        self.import_text.delete("1.0", "end")
        self._clear_preview()

    def _clear_preview(self):
        self._parsed_ot = []
        self._parsed_lv = []
        self.prev_ot_tree.delete(*self.prev_ot_tree.get_children())
        self.prev_lv_tree.delete(*self.prev_lv_tree.get_children())
        self.import_count_var.set("尚未解析")

    # ═══════════════════════════════════════════════
    # Tab 2：加班紀錄
    # ═══════════════════════════════════════════════

    def _tab_overtime(self, nb):
        f = ttk.Frame(nb)

        # ── 篩選列 ──
        flt = ttk.LabelFrame(f, text=" 篩選條件 ", padding=(8, 4))
        flt.pack(fill="x", padx=12, pady=(8, 4))

        ttk.Label(flt, text="月份：").grid(row=0, column=0, sticky="w")
        self.ot_month_var = tk.StringVar(value="")
        months = ["（全部）"] + make_months_list()
        ot_cb = ttk.Combobox(flt, textvariable=self.ot_month_var, values=months, width=11, state="readonly")
        ot_cb.grid(row=0, column=1, padx=(0, 12))
        ot_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_ot())

        ttk.Label(flt, text="姓名：").grid(row=0, column=2, sticky="w")
        self.ot_name_var = tk.StringVar()
        ttk.Entry(flt, textvariable=self.ot_name_var, width=12).grid(row=0, column=3, padx=(0, 12))

        ttk.Label(flt, text="搜尋：").grid(row=0, column=4, sticky="w")
        self.ot_search_var = tk.StringVar()
        ttk.Entry(flt, textvariable=self.ot_search_var, width=16).grid(row=0, column=5, padx=(0, 12))

        ttk.Button(flt, text="🔍 篩選", command=self.refresh_ot).grid(row=0, column=6, padx=4)
        ttk.Button(flt, text="⟳ 重設", command=self._reset_ot_filter).grid(row=0, column=7, padx=4)

        # ── 加班表 ──
        tree_frame = ttk.Frame(f)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=4)
        self.ot_tree = self._make_ot_treeview(tree_frame, readonly=False)

        # ── 底部操作列 ──
        bot = ttk.Frame(f)
        bot.pack(fill="x", padx=12, pady=(0, 8))
        self.ot_count_var = tk.StringVar(value="")
        ttk.Label(bot, textvariable=self.ot_count_var, foreground="#555").pack(side="left")
        ttk.Button(bot, text="➕ 新增", style="Accent.TButton",
                   command=self._ot_add).pack(side="right", padx=4)
        ttk.Button(bot, text="✏️ 編輯選取", command=self._ot_edit).pack(side="right", padx=4)
        ttk.Button(bot, text="🗑 刪除選取", command=self._ot_delete).pack(side="right", padx=4)
        ttk.Button(bot, text="📤 匯出 CSV", command=self._ot_export_csv).pack(side="right", padx=4)

        return f

    def _reset_ot_filter(self):
        self.ot_month_var.set("（全部）")
        self.ot_name_var.set("")
        self.ot_search_var.set("")
        self.refresh_ot()

    def refresh_ot(self):
        month = self.ot_month_var.get()
        if month == "（全部）" or not month:
            month = None
        name = self.ot_name_var.get().strip() or None
        search = self.ot_search_var.get().strip() or None

        rows = database.get_overtime_records(month=month, name=name, search=search)
        self.ot_tree.delete(*self.ot_tree.get_children())
        for i, r in enumerate(rows):
            tag = "even" if i % 2 == 0 else "odd"
            if "假日" in (r.get("note") or ""):
                tag = "weekend"
            self.ot_tree.insert("", "end", iid=str(r["id"]), values=(
                r["date"], r["name"], r["time"], f"{r['hours']:.1f}",
                r.get("note", ""), r["reason"]
            ), tags=(tag,))

        self.ot_count_var.set(f"共 {len(rows)} 筆加班記錄")

    def _ot_add(self):
        self._open_ot_dialog(None)

    def _ot_edit(self):
        sel = self.ot_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "請先選取一筆加班記錄", parent=self)
            return
        rec_id = int(sel[0])
        rows = database.get_overtime_records()
        rec = next((r for r in rows if r["id"] == rec_id), None)
        if rec:
            self._open_ot_dialog(rec)

    def _ot_delete(self):
        sel = self.ot_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "請先選取要刪除的紀錄", parent=self)
            return
        if not messagebox.askyesno("確認刪除", f"確定刪除所選的 {len(sel)} 筆加班記錄？", parent=self):
            return
        for iid in sel:
            database.delete_overtime_record(int(iid))
        self.refresh_ot()
        self.set_status(f"已刪除 {len(sel)} 筆加班記錄")

    def _ot_export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 檔案", "*.csv"), ("所有檔案", "*.*")],
            initialfile="overtime_records.csv",
            parent=self
        )
        if not path:
            return
        rows = database.get_overtime_records(
            month=self.ot_month_var.get() if self.ot_month_var.get() != "（全部）" else None
        )
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["日期", "姓名", "時段", "小時", "平假日", "事由"])
            for r in rows:
                w.writerow([r["date"], r["name"], r["time"], r["hours"], r.get("note", ""), r["reason"]])
        messagebox.showinfo("匯出完成", f"已匯出至：\n{path}", parent=self)

    def _open_ot_dialog(self, rec):
        """新增/編輯加班記錄對話框"""
        win = tk.Toplevel(self)
        win.title("新增加班記錄" if rec is None else "編輯加班記錄")
        win.geometry("480x380")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        fields = {}
        row_defs = [
            ("日期 (YYYY/MM/DD)", "date", rec["date"] if rec else current_ym() + "/01"),
            ("姓名", "name", rec["name"] if rec else ""),
            ("時段 (HH:MM-HH:MM)", "time", rec["time"] if rec else ""),
            ("加班時數", "hours", str(rec["hours"]) if rec else ""),
            ("平假日", "note", rec.get("note", "") if rec else ""),
            ("事由", "reason", rec["reason"] if rec else ""),
        ]

        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both", expand=True)

        for i, (label, key, default) in enumerate(row_defs):
            ttk.Label(frame, text=label + "：", font=FONT_BOLD).grid(
                row=i, column=0, sticky="e", pady=6, padx=(0, 8))
            if key == "note":
                var = tk.StringVar(value=default)
                cb = ttk.Combobox(frame, textvariable=var, width=28,
                                  values=["平日加班", "假日加班"], state="readonly")
                cb.grid(row=i, column=1, sticky="ew")
                fields[key] = var
            else:
                var = tk.StringVar(value=default)
                ttk.Entry(frame, textvariable=var, width=30).grid(row=i, column=1, sticky="ew")
                fields[key] = var

        frame.columnconfigure(1, weight=1)

        # 自動計算時數
        def auto_calc_hours(*_):
            t = fields["time"].get().strip()
            _, h = att_parser.parse_time_range(t)
            if h > 0:
                fields["hours"].set(str(h))
                note = att_parser.get_weekday_note(fields["date"].get().strip())
                fields["note"].set(note)

        fields["time"].trace_add("write", auto_calc_hours)
        fields["date"].trace_add("write", lambda *_: fields["note"].set(
            att_parser.get_weekday_note(fields["date"].get().strip())))

        def save():
            try:
                date = fields["date"].get().strip()
                name = fields["name"].get().strip()
                time_str = fields["time"].get().strip()
                hours = float(fields["hours"].get().strip())
                note = fields["note"].get().strip()
                reason = fields["reason"].get().strip()
                if not date or not name:
                    raise ValueError("日期和姓名不能為空")
                if rec is None:
                    database.add_overtime_record(date, name, time_str, hours, reason, note, hours)
                else:
                    database.update_overtime_record(rec["id"], date, name, time_str, hours, reason, note, hours)
                win.destroy()
                self.refresh_ot()
                self.set_status(f"{'新增' if rec is None else '更新'}加班記錄：{name} {date}")
            except ValueError as e:
                messagebox.showerror("輸入錯誤", str(e), parent=win)

        btn_row = ttk.Frame(win)
        btn_row.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(btn_row, text="儲存", style="Accent.TButton", command=save).pack(side="right", padx=4)
        ttk.Button(btn_row, text="取消", command=win.destroy).pack(side="right")

    # ═══════════════════════════════════════════════
    # Tab 3：請假紀錄
    # ═══════════════════════════════════════════════

    def _tab_leave(self, nb):
        f = ttk.Frame(nb)

        # ── 篩選列 ──
        flt = ttk.LabelFrame(f, text=" 篩選條件 ", padding=(8, 4))
        flt.pack(fill="x", padx=12, pady=(8, 4))

        ttk.Label(flt, text="月份：").grid(row=0, column=0, sticky="w")
        self.lv_month_var = tk.StringVar(value="")
        months = ["（全部）"] + make_months_list()
        lv_cb = ttk.Combobox(flt, textvariable=self.lv_month_var, values=months, width=11, state="readonly")
        lv_cb.grid(row=0, column=1, padx=(0, 12))
        lv_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_lv())

        ttk.Label(flt, text="姓名：").grid(row=0, column=2, sticky="w")
        self.lv_name_var = tk.StringVar()
        ttk.Entry(flt, textvariable=self.lv_name_var, width=12).grid(row=0, column=3, padx=(0, 12))

        ttk.Label(flt, text="假別：").grid(row=0, column=4, sticky="w")
        self.lv_type_vars = {}
        type_frame = ttk.Frame(flt)
        type_frame.grid(row=0, column=5, padx=(0, 8))
        for lt in ["黑假", "WFH", "病假", "事假", "特休"]:
            v = tk.BooleanVar(value=False)
            self.lv_type_vars[lt] = v
            ttk.Checkbutton(type_frame, text=lt, variable=v).pack(side="left", padx=2)

        ttk.Button(flt, text="🔍 篩選", command=self.refresh_lv).grid(row=0, column=6, padx=4)
        ttk.Button(flt, text="⟳ 重設", command=self._reset_lv_filter).grid(row=0, column=7, padx=4)

        # ── 請假表 ──
        tree_frame = ttk.Frame(f)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=4)
        self.lv_tree = self._make_lv_treeview(tree_frame, readonly=False)

        # ── 底部操作列 ──
        bot = ttk.Frame(f)
        bot.pack(fill="x", padx=12, pady=(0, 8))
        self.lv_count_var = tk.StringVar(value="")
        ttk.Label(bot, textvariable=self.lv_count_var, foreground="#555").pack(side="left")
        ttk.Button(bot, text="➕ 新增", style="Accent.TButton",
                   command=self._lv_add).pack(side="right", padx=4)
        ttk.Button(bot, text="✏️ 編輯選取", command=self._lv_edit).pack(side="right", padx=4)
        ttk.Button(bot, text="🗑 刪除選取", command=self._lv_delete).pack(side="right", padx=4)
        ttk.Button(bot, text="📤 匯出 CSV", command=self._lv_export_csv).pack(side="right", padx=4)

        return f

    def _reset_lv_filter(self):
        self.lv_month_var.set("（全部）")
        self.lv_name_var.set("")
        for v in self.lv_type_vars.values():
            v.set(False)
        self.refresh_lv()

    def refresh_lv(self):
        month = self.lv_month_var.get()
        if month == "（全部）" or not month:
            month = None
        name = self.lv_name_var.get().strip() or None
        checked = [lt for lt, v in self.lv_type_vars.items() if v.get()]
        leave_types = checked if checked else None

        rows = database.get_leave_records(month=month, name=name, leave_types=leave_types)
        self.lv_tree.delete(*self.lv_tree.get_children())
        for i, r in enumerate(rows):
            tag = "even" if i % 2 == 0 else "odd"
            self.lv_tree.insert("", "end", iid=str(r["id"]), values=(
                r["date"], r["name"], r["leave_type"], r["duration"],
                f"{r['google_comp_days']:.1f}", r["reason"]
            ), tags=(tag,))

        self.lv_count_var.set(f"共 {len(rows)} 筆請假記錄")

    def _lv_add(self):
        self._open_lv_dialog(None)

    def _lv_edit(self):
        sel = self.lv_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "請先選取一筆請假記錄", parent=self)
            return
        rec_id = int(sel[0])
        rows = database.get_leave_records()
        rec = next((r for r in rows if r["id"] == rec_id), None)
        if rec:
            self._open_lv_dialog(rec)

    def _lv_delete(self):
        sel = self.lv_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "請先選取要刪除的紀錄", parent=self)
            return
        if not messagebox.askyesno("確認刪除", f"確定刪除所選的 {len(sel)} 筆請假記錄？", parent=self):
            return
        for iid in sel:
            database.delete_leave_record(int(iid))
        self.refresh_lv()
        self.set_status(f"已刪除 {len(sel)} 筆請假記錄")

    def _lv_export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 檔案", "*.csv"), ("所有檔案", "*.*")],
            initialfile="leave_records.csv",
            parent=self
        )
        if not path:
            return
        month = self.lv_month_var.get()
        if month == "（全部）":
            month = None
        rows = database.get_leave_records(month=month)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["日期", "姓名", "假別", "天數", "Google補休天", "事由"])
            for r in rows:
                w.writerow([r["date"], r["name"], r["leave_type"], r["duration"],
                             r["google_comp_days"], r["reason"]])
        messagebox.showinfo("匯出完成", f"已匯出至：\n{path}", parent=self)

    def _open_lv_dialog(self, rec):
        win = tk.Toplevel(self)
        win.title("新增請假記錄" if rec is None else "編輯請假記錄")
        win.geometry("480x360")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both", expand=True)

        fields = {}
        row_defs = [
            ("日期 (YYYY/MM/DD)", "date", rec["date"] if rec else current_ym() + "/01"),
            ("姓名", "name", rec["name"] if rec else ""),
            ("假別", "leave_type", rec["leave_type"] if rec else "黑假"),
            ("天數", "duration", rec["duration"] if rec else "1天"),
            ("Google補休天", "google_comp_days", str(rec["google_comp_days"]) if rec else "1.0"),
            ("事由（可空白）", "reason", rec["reason"] if rec else ""),
        ]

        for i, (label, key, default) in enumerate(row_defs):
            ttk.Label(frame, text=label + "：", font=FONT_BOLD).grid(
                row=i, column=0, sticky="e", pady=6, padx=(0, 8))
            if key == "leave_type":
                var = tk.StringVar(value=default)
                cb = ttk.Combobox(frame, textvariable=var, width=28, values=LEAVE_TYPES, state="readonly")
                cb.grid(row=i, column=1, sticky="ew")
                fields[key] = var
                # 自動填入 Google補休
                def on_type_change(*_):
                    t = fields["leave_type"].get()
                    meta = att_parser.LEAVE_META.get(t, {})
                    fields["google_comp_days"].set(str(meta.get("google_comp", 0.0)))
                var.trace_add("write", on_type_change)
            elif key == "duration":
                var = tk.StringVar(value=default)
                cb = ttk.Combobox(frame, textvariable=var, width=28,
                                  values=["1天", "0.5天", "半天"], state="readonly")
                cb.grid(row=i, column=1, sticky="ew")
                fields[key] = var
            else:
                var = tk.StringVar(value=default)
                ttk.Entry(frame, textvariable=var, width=30).grid(row=i, column=1, sticky="ew")
                fields[key] = var

        frame.columnconfigure(1, weight=1)

        def save():
            try:
                date = fields["date"].get().strip()
                name = fields["name"].get().strip()
                leave_type = fields["leave_type"].get().strip()
                duration = fields["duration"].get().strip()
                comp = float(fields["google_comp_days"].get().strip() or 0)
                reason = fields["reason"].get().strip()
                if not date or not name:
                    raise ValueError("日期和姓名不能為空")
                if rec is None:
                    database.add_leave_record(date, name, leave_type, duration, comp, reason)
                else:
                    database.update_leave_record(rec["id"], date, name, leave_type, duration, comp, reason)
                win.destroy()
                self.refresh_lv()
                self.set_status(f"{'新增' if rec is None else '更新'}請假記錄：{name} {date}")
            except ValueError as e:
                messagebox.showerror("輸入錯誤", str(e), parent=win)

        btn_row = ttk.Frame(win)
        btn_row.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(btn_row, text="儲存", style="Accent.TButton", command=save).pack(side="right", padx=4)
        ttk.Button(btn_row, text="取消", command=win.destroy).pack(side="right")

    # ═══════════════════════════════════════════════
    # Tab 4：月度統計
    # ═══════════════════════════════════════════════

    def _tab_stats(self, nb):
        f = ttk.Frame(nb)

        # ── 月份選擇 ──
        ctrl = ttk.Frame(f)
        ctrl.pack(fill="x", padx=12, pady=(10, 4))

        ttk.Label(ctrl, text="統計月份：", font=FONT_BOLD).pack(side="left")
        self.stats_month_var = tk.StringVar(value=current_ym())
        months = make_months_list()
        stats_cb = ttk.Combobox(ctrl, textvariable=self.stats_month_var, values=months, width=11, state="readonly")
        stats_cb.pack(side="left", padx=(0, 12))
        stats_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_stats())

        ttk.Button(ctrl, text="📊 更新統計", style="Accent.TButton",
                   command=self.refresh_stats).pack(side="left", padx=4)
        ttk.Button(ctrl, text="📤 匯出統計 CSV", command=self._stats_export_csv).pack(side="left", padx=4)

        # ── 上方：加班統計表 ──
        ot_lf = ttk.LabelFrame(f, text=" 加班統計（小時）", padding=6)
        ot_lf.pack(fill="x", padx=12, pady=(6, 4))

        ot_cols = ("姓名", "加班小時數")
        self.stats_ot_tree = ttk.Treeview(ot_lf, columns=ot_cols, show="headings", height=8)
        for col in ot_cols:
            self.stats_ot_tree.heading(col, text=col)
        self.stats_ot_tree.column("姓名", width=160)
        self.stats_ot_tree.column("加班小時數", width=100, anchor="center")
        self._set_tree_tags(self.stats_ot_tree)

        sb1 = ttk.Scrollbar(ot_lf, orient="vertical", command=self.stats_ot_tree.yview)
        self.stats_ot_tree.configure(yscrollcommand=sb1.set)
        self.stats_ot_tree.pack(side="left", fill="both", expand=True)
        sb1.pack(side="right", fill="y")

        # ── 下方：請假統計表 ──
        lv_lf = ttk.LabelFrame(f, text=" 請假與補休統計 ", padding=6)
        lv_lf.pack(fill="both", expand=True, padx=12, pady=(4, 10))

        lv_cols = ("姓名", "黑假(天)", "WFH(天)", "病假(天)", "事假(天)", "特休(天)", "因公外出(次)", "Google補休(天)")
        self.stats_lv_tree = ttk.Treeview(lv_lf, columns=lv_cols, show="headings")
        for col in lv_cols:
            self.stats_lv_tree.heading(col, text=col)
            self.stats_lv_tree.column(col, width=100, anchor="center")
        self.stats_lv_tree.column("姓名", width=140, anchor="w")
        self._set_tree_tags(self.stats_lv_tree)

        sb2 = ttk.Scrollbar(lv_lf, orient="vertical", command=self.stats_lv_tree.yview)
        self.stats_lv_tree.configure(yscrollcommand=sb2.set)
        self.stats_lv_tree.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")

        return f

    def refresh_stats(self):
        month = self.stats_month_var.get()
        data = database.get_monthly_stats(month=month)

        self.stats_ot_tree.delete(*self.stats_ot_tree.get_children())
        self.stats_lv_tree.delete(*self.stats_lv_tree.get_children())

        for i, s in enumerate(data["stats"]):
            tag = "even" if i % 2 == 0 else "odd"
            self.stats_ot_tree.insert("", "end", values=(
                s["name"], f"{s['overtime_hours']:.1f}"
            ), tags=(tag,))
            self.stats_lv_tree.insert("", "end", values=(
                s["name"],
                f"{s['black_days']:.1f}" if s["black_days"] else "-",
                f"{s['wfh_days']:.1f}" if s["wfh_days"] else "-",
                f"{s['sick_days']:.1f}" if s["sick_days"] else "-",
                f"{s['personal_days']:.1f}" if s["personal_days"] else "-",
                "-",
                str(s["business_count"]) if s["business_count"] else "-",
                f"{s['google_comp_total']:.1f}" if s["google_comp_total"] else "-",
            ), tags=(tag,))

        # 加班合計列
        self.stats_ot_tree.insert("", "end", values=(
            "【團隊合計】", f"{data['team_total_hours']:.1f}"
        ), tags=("total",))
        self.stats_ot_tree.tag_configure("total", background="#e8e3ff", font=FONT_BOLD)

        self.set_status(f"統計月份：{month}，共 {len(data['stats'])} 人")

    def _stats_export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 檔案", "*.csv")],
            initialfile=f"stats_{self.stats_month_var.get().replace('/', '')}.csv",
            parent=self
        )
        if not path:
            return
        month = self.stats_month_var.get()
        data = database.get_monthly_stats(month=month)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["月份", month])
            w.writerow([])
            w.writerow(["姓名", "加班小時"])
            for s in data["stats"]:
                w.writerow([s["name"], s["overtime_hours"]])
            w.writerow(["團隊合計", data["team_total_hours"]])
            w.writerow([])
            w.writerow(["姓名", "黑假", "WFH", "病假", "事假", "因公外出", "Google補休"])
            for s in data["stats"]:
                w.writerow([s["name"], s["black_days"], s["wfh_days"],
                             s["sick_days"], s["personal_days"],
                             s["business_count"], s["google_comp_total"]])
        messagebox.showinfo("匯出完成", f"已匯出至：\n{path}", parent=self)

    # ═══════════════════════════════════════════════
    # 共用：Treeview 建立工具
    # ═══════════════════════════════════════════════

    def _make_ot_treeview(self, parent, readonly=True):
        """建立加班記錄 Treeview"""
        cols = ("日期", "姓名", "時段", "小時", "平/假日", "事由")
        widths = (90, 70, 110, 50, 75, 350)

        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)

        tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="extended")
        for col, w in zip(cols, widths):
            tree.heading(col, text=col)
            tree.column(col, width=w, minwidth=40,
                        anchor="center" if col in ("小時", "平/假日", "時段") else "w")

        self._set_tree_tags(tree)

        sb_y = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        sb_x = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        if not readonly:
            tree.bind("<Double-1>", lambda e: self._ot_edit())

        return tree

    def _make_lv_treeview(self, parent, readonly=True):
        """建立請假記錄 Treeview"""
        cols = ("日期", "姓名", "假別", "天數", "Google補休", "事由")
        widths = (90, 70, 80, 60, 80, 350)

        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)

        tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="extended")
        for col, w in zip(cols, widths):
            tree.heading(col, text=col)
            tree.column(col, width=w, minwidth=40,
                        anchor="center" if col in ("天數", "Google補休", "假別") else "w")

        self._set_tree_tags(tree)

        sb_y = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        sb_x = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        if not readonly:
            tree.bind("<Double-1>", lambda e: self._lv_edit())

        return tree

    @staticmethod
    def _set_tree_tags(tree):
        tree.tag_configure("odd",     background=COLORS["row_odd"])
        tree.tag_configure("even",    background=COLORS["row_even"])
        tree.tag_configure("weekend", background=COLORS["weekend"])

    # ═══════════════════════════════════════════════
    # 全部重新載入
    # ═══════════════════════════════════════════════

    def refresh_all(self):
        self.refresh_ot()
        self.refresh_lv()
        self.refresh_stats()
        self.set_status("資料已更新")


# ─────────────────────────── 入口 ────────────────────────────

def main():
    app = OverworkApp()
    app.mainloop()


if __name__ == "__main__":
    main()
