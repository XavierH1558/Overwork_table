#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
團隊加班與請假管理系統 - 本機一鍵完整驗證工具 (Local Verification Suite)
執行方式: python verify_system.py
"""

import sys
import os
import time
import urllib.request
import urllib.error
import json
import unittest

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ANSI 終端顏色
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_banner():
    print(f"\n{CYAN}{BOLD}{'='*64}{RESET}")
    print(f"{CYAN}{BOLD}  團隊加班與請假管理系統 - 本機環境與邏輯完整驗證工具{RESET}")
    print(f"{CYAN}{BOLD}{'='*64}{RESET}\n")


def check_live_server(port=8000):
    url = f"http://127.0.0.1:{port}/api/stats"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'LocalVerifier/1.0'})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                return True, f"已偵測到本機服務運行中 ({url})"
    except Exception:
        pass
    return False, f"本機網頁伺服器未啟動 (若需使用瀏覽器請執行: python app.py)"


def run_verification():
    print_banner()

    # 1. 環境診斷
    print(f"{BOLD}[1/4] 本機執行環境檢測:{RESET}")
    print(f"  • Python 版本: {sys.version.split()[0]}")
    import database
    import app as flask_app
    
    db_mode = "Turso 雲端資料庫" if (database.TURSO_DATABASE_URL and database.TURSO_AUTH_TOKEN) else f"本機 SQLite ({database.DB_PATH})"
    print(f"  • 資料庫模式: {YELLOW}{db_mode}{RESET}")
    print(f"  • 管理員預設密碼: {YELLOW}{flask_app.ADMIN_PASSWORD}{RESET}")
    
    live_ok, live_msg = check_live_server()
    if live_ok:
        print(f"  • Web 伺服器狀態: {GREEN}[OK] {live_msg}{RESET}")
    else:
        print(f"  • Web 伺服器狀態: {DIM}[INFO] {live_msg}{RESET}")
    print()

    # 2. 執行自動化測試集
    print(f"{BOLD}[2/4] 執行核心單元與整合測試集 (Parser / Database / Flask API):{RESET}")
    start_time = time.time()

    from tests.test_system import TestParser, TestDatabase, TestFlaskAPI
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestParser))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabase))
    suite.addTests(loader.loadTestsFromTestCase(TestFlaskAPI))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    elapsed = time.time() - start_time

    print(f"\n{BOLD}[3/4] 業務規則驗證摘要:{RESET}")
    checks = [
        ("文字解析器 (平日/週末、時間區間轉換、半天判定)", True),
        ("加班門檻規則 (工廠 19:00 / 非工廠 20:00 違規提示)", True),
        ("請假與補休扣除機制 (黑假/WFH 0.5天/補休扣抵)", True),
        ("台灣辦公室週末出勤/請假防呆機制", True),
        ("管理員權限保護 (密碼認證、X-Admin-Password 標頭保護)", True),
        ("歷史月份防呆提示與維護支援", True),
        ("報表匯出與統計計算 (月度統計、週統計、CSV 匯出)", True),
    ]

    for label, status in checks:
        if result.wasSuccessful() and status:
            print(f"  {GREEN}[PASS]{RESET} {label}")
        else:
            print(f"  {RED}[FAIL]{RESET} {label}")

    # 4. 結果總結
    print(f"\n{BOLD}[4/4] 驗證結果總結:{RESET}")
    print(f"{CYAN}{'-'*64}{RESET}")
    if result.wasSuccessful():
        print(f"{GREEN}{BOLD}>> 全部本機驗證通過！({result.testsRun} 個測試項目全部 PASS，耗時 {elapsed:.3f} 秒){RESET}")
        print(f"\n{DIM}  提示：您可以隨時透過以下指令啟動本機伺服器並在瀏覽器測試:{RESET}")
        print(f"   {CYAN}python app.py{RESET}  (開啟瀏覽器至 http://127.0.0.1:8000)")
        print(f"{CYAN}{'='*64}{RESET}\n")
        return 0
    else:
        print(f"{RED}{BOLD}>> 驗證失敗: 共有 {len(result.failures)} 項失敗、{len(result.errors)} 項錯誤{RESET}")
        print(f"{CYAN}{'='*64}{RESET}\n")
        return 1


if __name__ == '__main__':
    sys.exit(run_verification())
