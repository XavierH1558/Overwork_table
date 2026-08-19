"""
自動化測試與本機驗證腳本
包含：
1. Parser 測試 (加班時間解析、假別判定、工廠/非工廠門檻、文字解析)
2. Database 測試 (成員管理、地點履歷、加班/請假 CRUD、補休額度扣除、統計計算、台灣週末限制)
3. API 整合測試 (管理員權限、REST API 路由、批次操作、報表匯出、跨月限制)
"""

import unittest
import os
import sys
import json
import tempfile
import sqlite3
from datetime import datetime

# 確保載入專案模組
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import database
import parser
import app as flask_app


class TestParser(unittest.TestCase):
    """測試文字與訊息解析模組"""

    def setUp(self):
        self.member_locations = {
            "小明": "台灣辦公室",
            "小華": "台灣工廠",
            "老王": "南崁工廠",
            "Alice": "美國辦公室",
            "Benny": "台灣工廠",
            "Eden": "台灣辦公室",
            "Xavier": "台灣辦公室"
        }
        self.location_histories = [
            {"name": "小明", "start_date": "2026/01/01", "end_date": "2026/01/31", "location": "台灣工廠"}
        ]
        self.known_names = list(self.member_locations.keys())

    def test_overtime_parsing_non_factory(self):
        """測試非工廠 (20:00起算) 加班解析"""
        text = "2026/03/10 小明 20:00-22:30 專案測試"
        ot_records, lv_records, warn_records = parser.parse_raw_text(
            text, default_year=2026, known_names=self.known_names, member_locations=self.member_locations
        )
        self.assertEqual(len(ot_records), 1)
        self.assertEqual(ot_records[0]['name'], "小明")
        self.assertEqual(ot_records[0]['hours'], 2.5)
        self.assertEqual(ot_records[0]['eval_hours'], 2.5)
        self.assertIsNone(ot_records[0]['rule_warning'])

    def test_overtime_parsing_factory(self):
        """測試工廠 (19:00起算) 加班解析"""
        text = "2026/03/10 小華 19:00-22:00 產線支援"
        ot_records, lv_records, warn_records = parser.parse_raw_text(
            text, default_year=2026, known_names=self.known_names, member_locations=self.member_locations
        )
        self.assertEqual(len(ot_records), 1)
        self.assertEqual(ot_records[0]['name'], "小華")
        self.assertEqual(ot_records[0]['hours'], 3.0)
        self.assertIsNone(ot_records[0]['rule_warning'])

    def test_overtime_early_rule_warning(self):
        """測試非工廠在 20:00 前提早加班觸發警示"""
        text = "2026/03/10 小明 19:00-22:00 專案測試"
        ot_records, lv_records, warn_records = parser.parse_raw_text(
            text, default_year=2026, known_names=self.known_names, member_locations=self.member_locations
        )
        self.assertEqual(len(ot_records), 1)
        self.assertIsNotNone(ot_records[0]['rule_warning'])
        self.assertIn("不得早於 20:00", ot_records[0]['rule_warning'])

    def test_leave_parsing_wfh(self):
        """測試 WFH 假別解析 (WFH 歸類於黑假並帶 0.5 天補休)"""
        text = "2026/03/12 小明 WFH 家中有事"
        ot_records, lv_records, warn_records = parser.parse_raw_text(
            text, default_year=2026, known_names=self.known_names, member_locations=self.member_locations
        )
        self.assertEqual(len(lv_records), 1)
        self.assertEqual(lv_records[0]['leave_type'], "黑假")
        self.assertEqual(lv_records[0]['google_comp_days'], 0.5)
        self.assertEqual(lv_records[0]['name'], "小明")

    def test_leave_parsing_half_day(self):
        """測試半天假別 (上午/下午) 解析"""
        text = "2026/03/13 小明 下午特休半天"
        ot_records, lv_records, warn_records = parser.parse_raw_text(
            text, default_year=2026, known_names=self.known_names, member_locations=self.member_locations
        )
        self.assertEqual(len(lv_records), 1)
        self.assertEqual(lv_records[0]['leave_type'], "特休")
        self.assertIn("0.5天", lv_records[0]['duration'])
        self.assertEqual(lv_records[0]['google_comp_days'], 0.0)


class TestDatabase(unittest.TestCase):
    """測試 SQLite 本機資料庫操作模組"""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        self.orig_db_path = database.DB_PATH
        self.orig_turso_url = database.TURSO_DATABASE_URL
        self.orig_turso_token = database.TURSO_AUTH_TOKEN
        database.DB_PATH = self.temp_db_path
        database.TURSO_DATABASE_URL = ""
        database.TURSO_AUTH_TOKEN = ""

        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.orig_db_path
        database.TURSO_DATABASE_URL = self.orig_turso_url
        database.TURSO_AUTH_TOKEN = self.orig_turso_token
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except Exception:
                pass

    def test_member_crud(self):
        """測試成員 新增/查詢/修改地點/修改額度/刪除"""
        # 新增
        mid = database.add_member("測試員", "台灣辦公室", 5.0)
        self.assertIsNotNone(mid)

        # 查詢
        members = database.get_all_members()
        m = next((item for item in members if item['name'] == "測試員"), None)
        self.assertIsNotNone(m)
        self.assertEqual(m['location'], "台灣辦公室")
        self.assertEqual(m['google_comp_quota'], 5.0)

        # 修改地點
        database.update_member_location(mid, "台灣工廠")
        members = database.get_all_members()
        m = next((item for item in members if item['name'] == "測試員"), None)
        self.assertEqual(m['location'], "台灣工廠")

        # 修改額度
        database.update_member_quota(mid, 8.5)
        members = database.get_all_members()
        m = next((item for item in members if item['name'] == "測試員"), None)
        self.assertEqual(m['google_comp_quota'], 8.5)

        # 刪除
        database.delete_member(mid)
        members = database.get_all_members()
        self.assertIsNone(next((item for item in members if item['name'] == "測試員"), None))

    def test_location_history(self):
        """測試駐點履歷 CRUD"""
        database.add_member("歷史員", "台灣辦公室", 0.0)
        hid = database.add_member_location_history("歷史員", "2026/01/01", "2026/01/31", "南崁工廠")
        self.assertIsNotNone(hid)

        histories = database.get_all_member_location_histories("歷史員")
        self.assertEqual(len(histories), 1)
        self.assertEqual(histories[0]['location'], "南崁工廠")

        # 日期判定
        loc_jan = database.get_member_location_at_date("歷史員", "2026/01/15")
        self.assertEqual(loc_jan, "南崁工廠")
        loc_feb = database.get_member_location_at_date("歷史員", "2026/02/15")
        self.assertEqual(loc_feb, "台灣辦公室")

        # 刪除履歷
        database.delete_member_location_history(hid)
        histories = database.get_all_member_location_histories("歷史員")
        self.assertEqual(len(histories), 0)

    def test_overtime_crud(self):
        """測試加班紀錄 新增/查詢/更新/刪除"""
        database.add_member("加班王", "台灣辦公室", 0.0)
        rec_id = database.add_overtime_record("2026/03/01", "加班王", "20:00-22:00", 2.0, "除錯", "備註", 2.0)
        self.assertIsNotNone(rec_id)

        records = database.get_overtime_records(month="2026/03", name="加班王")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['hours'], 2.0)

        # 更新
        database.update_overtime_record(rec_id, "2026/03/01", "加班王", "20:00-23:00", 3.0, "深度除錯", "備註2", 3.0)
        records = database.get_overtime_records(month="2026/03", name="加班王")
        self.assertEqual(records[0]['hours'], 3.0)

        # 刪除
        database.delete_overtime_record(rec_id)
        records = database.get_overtime_records(month="2026/03", name="加班王")
        self.assertEqual(len(records), 0)

    def test_leave_crud_and_quota_deduction(self):
        """測試請假紀錄與補休額度扣除狀態"""
        database.add_member("休假王", "台灣辦公室", 10.0)
        l_id = database.add_leave_record("2026/03/02", "休假王", "黑假", "1天", 1.0, "個人休假", is_comp_deducted=1)
        self.assertIsNotNone(l_id)

        records = database.get_leave_records(month="2026/03", name="休假王")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['google_comp_days'], 1.0)
        self.assertEqual(records[0]['is_comp_deducted'], 1)

        # 更改為不扣額度
        database.update_leave_deducted_status(l_id, 0)
        records = database.get_leave_records(month="2026/03", name="休假王")
        self.assertEqual(records[0]['is_comp_deducted'], 0)

        # 統計
        stats = database.get_monthly_stats(month="2026/03")
        stats_list = stats.get('stats', [])
        user_stat = next((s for s in stats_list if s['name'] == "休假王"), None)
        self.assertIsNotNone(user_stat)

    def test_taiwan_weekend_leave_restriction(self):
        """測試台灣辦公室週末請假檢核機制 (2026/03/14 為週六)"""
        database.add_member("台灣同仁", "台灣辦公室", 5.0)
        is_invalid, err_msg = database.check_taiwan_leave_weekend("台灣同仁", "2026/03/14", "特休")
        self.assertTrue(is_invalid)
        self.assertIn("禮拜六日無上班", err_msg)

        # 平日則不應阻擋 (2026/03/13 為週五)
        is_invalid_fri, _ = database.check_taiwan_leave_weekend("台灣同仁", "2026/03/13", "特休")
        self.assertFalse(is_invalid_fri)

    def test_attendance_check_quota_and_exceeded(self):
        """測試每人每月 4 次出勤確認容錯額度與超額判定"""
        database.add_member("刷卡員", "台灣辦公室", 0.0)
        for i in range(1, 6):
            database.add_leave_record(f"2026/03/0{i}", "刷卡員", "出勤確認", "出勤確認", 0.0, f"忘刷第{i}次")

        stats = database.get_monthly_stats(month="2026/03")
        stats_list = stats.get('stats', [])
        user_stat = next((s for s in stats_list if s['name'] == "刷卡員"), None)
        self.assertIsNotNone(user_stat)
        self.assertEqual(user_stat['attendance_check_count'], 5)
        self.assertTrue(user_stat['attendance_check_exceeded'])

        chk_breakdown = next((b for b in user_stat['leave_breakdown'] if b['type'] == '出勤確認'), None)
        self.assertIsNotNone(chk_breakdown)
        self.assertTrue(chk_breakdown['exceeded'])
        self.assertIn("超額1次", chk_breakdown['label'])


class TestFlaskAPI(unittest.TestCase):
    """測試 Flask Web 路由與管理員認證機制"""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        self.orig_db_path = database.DB_PATH
        self.orig_turso_url = database.TURSO_DATABASE_URL
        self.orig_turso_token = database.TURSO_AUTH_TOKEN
        database.DB_PATH = self.temp_db_path
        database.TURSO_DATABASE_URL = ""
        database.TURSO_AUTH_TOKEN = ""
        database.init_db()

        # 先在測試資料庫中建立成員
        database.add_member("測試員", "台灣辦公室", 5.0)

        flask_app.app.config['TESTING'] = True
        self.client = flask_app.app.test_client()
        self.admin_pw = flask_app.ADMIN_PASSWORD
        self.admin_headers = {'X-Admin-Password': self.admin_pw, 'Content-Type': 'application/json'}

    def tearDown(self):
        database.DB_PATH = self.orig_db_path
        database.TURSO_DATABASE_URL = self.orig_turso_url
        database.TURSO_AUTH_TOKEN = self.orig_turso_token
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except Exception:
                pass

    def test_verify_admin_endpoint(self):
        """測試管理員密碼驗證 API"""
        # 正確密碼
        res = self.client.post('/api/verify_admin', json={'password': self.admin_pw})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('unlocked'))

        # 錯誤密碼
        res_wrong = self.client.post('/api/verify_admin', json={'password': 'wrong_password_999'})
        self.assertEqual(res_wrong.status_code, 401)

    def test_member_api_auth_protection(self):
        """測試成員管理需管理員權限保護"""
        # 未帶管理員標頭 -> 應被拒絕 403
        res = self.client.post('/api/members', json={'name': '未授權用戶'})
        self.assertEqual(res.status_code, 403)

        # 帶正確管理員標頭 -> 成功 200
        res_auth = self.client.post('/api/members', json={'name': '授權用戶', 'location': '台灣辦公室', 'google_comp_quota': 2.0}, headers=self.admin_headers)
        self.assertEqual(res_auth.status_code, 200)

    def test_parse_api(self):
        """測試 /api/parse API"""
        payload = {
            "text": "2026/03/15 測試員 20:00-22:00 伺服器部署",
            "year": 2026
        }
        res = self.client.post('/api/parse', json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['overtime_records']), 1)

    def test_export_csv_api(self):
        """測試 /api/export 匯出 API"""
        res = self.client.get('/api/export?month=2026/03')
        self.assertEqual(res.status_code, 200)
        self.assertIn('text/csv', res.content_type)

    def test_stats_api(self):
        """測試 /api/stats 統計資料 API"""
        res = self.client.get('/api/stats?month=2026/03')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('stats', data)
        self.assertIn('weekly_summary', data)

    def test_historical_month_crud_authorized(self):
        """測試管理員授權下，歷史月份資料仍可正常進行 CRUD 維護"""
        # 歷史月份加班新增
        res_add = self.client.post('/api/overtime', json={
            'date': '2025/12/15',
            'name': '測試員',
            'time': '20:00-22:00',
            'hours': 2.0,
            'reason': '歷史加班'
        }, headers=self.admin_headers)
        self.assertEqual(res_add.status_code, 200)
        rec_id = res_add.get_json().get('id')

        # 歷史月份加班修改
        res_upd = self.client.put(f'/api/overtime/{rec_id}', json={
            'date': '2025/12/15',
            'name': '測試員',
            'time': '20:00-23:00',
            'hours': 3.0,
            'reason': '歷史加班修正'
        }, headers=self.admin_headers)
        self.assertEqual(res_upd.status_code, 200)

        # 歷史月份加班刪除
        res_del = self.client.delete(f'/api/overtime/{rec_id}', headers=self.admin_headers)
        self.assertEqual(res_del.status_code, 200)


if __name__ == '__main__':
    unittest.main()
