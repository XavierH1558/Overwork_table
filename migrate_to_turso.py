"""
Turso 資料同步匯入腳本 (Migrate local attendance.db to Turso Cloud)
支援 libsql_client (純 Python HTTP) 與 libsql_experimental (Native)

使用說明：
1. 直接在終端機執行：python3 migrate_to_turso.py
2. 根據提示輸入 TURSO_DATABASE_URL 與 TURSO_AUTH_TOKEN 即可匯入。
"""

import sqlite3
import os
import sys
import database

DB_PATH = database.DB_PATH

def migrate():
    turso_url = os.environ.get('TURSO_DATABASE_URL', '').strip()
    turso_token = os.environ.get('TURSO_AUTH_TOKEN', '').strip()

    if not turso_url or not turso_token:
        print("❌ 未偵測到 TURSO_DATABASE_URL 或 TURSO_AUTH_TOKEN 環境變數！")
        print("\n請手動輸入連線資訊（直接按 Enter 鍵取消）：")
        turso_url = input("請輸入 TURSO_DATABASE_URL (例: libsql://your-db.turso.io): ").strip()
        turso_token = input("請輸入 TURSO_AUTH_TOKEN: ").strip()

    if not turso_url or not turso_token:
        print("❌ 未提供完整的 Turso 連線資訊，終止匯入。")
        sys.exit(1)

    if not os.path.exists(DB_PATH):
        print(f"❌ 找不到本地資料庫檔案: {DB_PATH}")
        sys.exit(1)

    # 確保網址格式為 https://
    http_url = turso_url.replace("libsql://", "https://")
    if not http_url.startswith("http://") and not http_url.startswith("https://"):
        http_url = "https://" + http_url

    print(f"📦 正在讀取本地 SQLite: {DB_PATH}")
    local_conn = sqlite3.connect(DB_PATH)
    local_conn.row_factory = sqlite3.Row
    local_cursor = local_conn.cursor()

    # 嘗試載入連線驅動套件 (優先 libsql_experimental，失敗則自動使用純 Python 的 libsql_client)
    client = None
    turso_conn = None
    use_experimental = False

    try:
        import libsql_experimental as libsql
        turso_conn = libsql.connect(turso_url, auth_token=turso_token)
        turso_cursor = turso_conn.cursor()
        use_experimental = True
        print(f"☁️ 正在連線至 Turso 雲端資料庫 (使用 Native 驅動)...")
    except Exception:
        try:
            import libsql_client
            client = libsql_client.create_client_sync(http_url, auth_token=turso_token)
            print(f"☁️ 正在連線至 Turso 雲端資料庫 (使用 HTTP 純 Python 驅動)...")
        except Exception as e:
            print(f"❌ 連線建立失敗！請確認 libsql-client 套件: {e}")
            sys.exit(1)

    # 讀取本地所有資料表名稱
    local_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in local_cursor.fetchall()]

    print(f"📋 找到資料表: {', '.join(tables)}")

    # 初始化建表語法
    create_sqls = [
        '''CREATE TABLE IF NOT EXISTS overtime_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            name TEXT NOT NULL,
            time TEXT NOT NULL,
            hours REAL NOT NULL,
            reason TEXT NOT NULL,
            note TEXT NOT NULL,
            eval_hours REAL NOT NULL,
            year INTEGER,
            month INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_special INTEGER DEFAULT 0,
            special_reason TEXT DEFAULT ''
        )''',
        '''CREATE TABLE IF NOT EXISTS leave_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            name TEXT NOT NULL,
            leave_type TEXT NOT NULL,
            duration TEXT NOT NULL,
            google_comp_days REAL NOT NULL,
            reason TEXT NOT NULL,
            year INTEGER,
            month INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            location TEXT DEFAULT '台灣辦公室',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS member_location_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            location TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''
    ]

    for sql in create_sqls:
        if use_experimental:
            turso_cursor.execute(sql)
        else:
            client.execute(sql)

    if use_experimental:
        turso_conn.commit()

    total_inserted = 0

    for table in tables:
        local_cursor.execute(f"PRAGMA table_info('{table}')")
        cols = [r[1] for r in local_cursor.fetchall()]
        if not cols:
            continue

        cols_str = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO \"{table}\" ({cols_str}) VALUES ({placeholders})"

        local_cursor.execute(f"SELECT {cols_str} FROM \"{table}\"")
        rows = local_cursor.fetchall()
        count = len(rows)

        if count > 0:
            row_tuples = [tuple(row) for row in rows]
            if use_experimental:
                turso_cursor.executemany(sql, row_tuples)
                turso_conn.commit()
            else:
                for row_t in row_tuples:
                    clean_tuple = [None if v is None else v for v in row_t]
                    client.execute(sql, clean_tuple)
            print(f"✅ 資料表 [{table}]: 成功寫入 {count} 筆資料")
            total_inserted += count
        else:
            print(f"ℹ️ 資料表 [{table}]: 無舊資料需寫入")

    local_conn.close()
    if use_experimental:
        turso_conn.close()
    else:
        client.close()

    print(f"\n🎉 匯入完成！總共傳送 {total_inserted} 筆紀錄至 Turso 雲端資料庫。")

if __name__ == '__main__':
    migrate()
