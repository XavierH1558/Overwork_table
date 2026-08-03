import sqlite3
import os
import re
from datetime import datetime
import parser

DB_DIR = os.environ.get('DATA_DIR', '').strip()
if DB_DIR:
    try:
        os.makedirs(DB_DIR, exist_ok=True)
        test_file = os.path.join(DB_DIR, '.perm_test')
        with open(test_file, 'w') as f:
            f.write('1')
        os.remove(test_file)
    except Exception:
        DB_DIR = os.path.dirname(__file__)
else:
    DB_DIR = os.path.dirname(__file__)

DB_PATH = os.path.join(DB_DIR, 'attendance.db')

TURSO_DATABASE_URL = os.environ.get('TURSO_DATABASE_URL', '').strip()
TURSO_AUTH_TOKEN = os.environ.get('TURSO_AUTH_TOKEN', '').strip()

class LibsqlRowWrapper:
    def __init__(self, libsql_row):
        self._dict = libsql_row.asdict()
        self._tuple = libsql_row.astuple()

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._tuple[item]
        return self._dict[item]

    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()

    def items(self):
        return self._dict.items()

    def __iter__(self):
        return iter(self._dict)

class LibsqlCursorWrapper:
    def __init__(self, client):
        self.client = client
        self.last_result = None

    def execute(self, sql, params=()):
        if params is None:
            params = ()
        res = self.client.execute(sql, list(params))
        self.last_result = res
        return self

    def fetchall(self):
        if not self.last_result or not self.last_result.rows:
            return []
        return [LibsqlRowWrapper(r) for r in self.last_result.rows]

    def fetchone(self):
        if not self.last_result or not self.last_result.rows:
            return None
        return LibsqlRowWrapper(self.last_result.rows[0])

class LibsqlConnWrapper:
    def __init__(self, url, token):
        import libsql_client
        http_url = url.replace("libsql://", "https://")
        if not http_url.startswith("http://") and not http_url.startswith("https://"):
            http_url = "https://" + http_url
        self.client = libsql_client.create_client_sync(http_url, auth_token=token)

    def cursor(self):
        return LibsqlCursorWrapper(self.client)

    def commit(self):
        pass

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

def get_connection():
    if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
        try:
            return LibsqlConnWrapper(TURSO_DATABASE_URL, TURSO_AUTH_TOKEN)
        except Exception as e1:
            try:
                import libsql_experimental as libsql
                conn = libsql.connect(TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)
                conn.row_factory = sqlite3.Row
                return conn
            except Exception as e2:
                print(f"[Database] Failed to connect to Turso: {e1} / {e2}, falling back to local SQLite.")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Overtime records table matching image 1
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS overtime_records (
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Leave records table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leave_records (
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
            )
        ''')

        # Team members table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                location TEXT DEFAULT '台灣辦公室',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Check if location column exists for existing table
        cursor.execute("PRAGMA table_info(team_members)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'location' not in cols:
            cursor.execute("ALTER TABLE team_members ADD COLUMN location TEXT DEFAULT '台灣辦公室'")

        # Check if is_special / special_reason columns exist in overtime_records
        cursor.execute("PRAGMA table_info(overtime_records)")
        ot_cols = [r[1] for r in cursor.fetchall()]
        if 'is_special' not in ot_cols:
            cursor.execute("ALTER TABLE overtime_records ADD COLUMN is_special INTEGER DEFAULT 0")
        if 'special_reason' not in ot_cols:
            cursor.execute("ALTER TABLE overtime_records ADD COLUMN special_reason TEXT DEFAULT ''")

        # Member location history table (date-range based location)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS member_location_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT,
                location TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Populate initial default members if table is empty
        cursor.execute('SELECT COUNT(*) FROM team_members')
        if cursor.fetchone()[0] == 0:
            default_members = ["Benny", "Daniel", "Eden", "YiWen", "Xavier", "Winnie", "Kevin", "Cora", "Benson", "Jim", "Rell"]
            for m in default_members:
                cursor.execute('INSERT OR IGNORE INTO team_members (name, location) VALUES (?, ?)', (m, '台灣辦公室'))

        conn.commit()


def get_all_members():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, COALESCE(location, "台灣辦公室") as location FROM team_members ORDER BY name ASC')
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_member_location_map():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, COALESCE(location, "台灣辦公室") as location FROM team_members')
        rows = cursor.fetchall()
        return {r['name']: r['location'] for r in rows}


def normalize_date_fmt(d_str):
    if not d_str or not str(d_str).strip():
        return ""
    st = str(d_str).strip().replace('-', '/')
    if len(st) == 8 and st.isdigit():
        return f"{st[:4]}/{st[4:6]}/{st[6:]}"
    parts = st.split('/')
    if len(parts) == 3:
        try:
            return f"{int(parts[0]):04d}/{int(parts[1]):02d}/{int(parts[2]):02d}"
        except Exception:
            return st
    return st


def get_all_member_location_histories(name=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        if name and name.strip():
            cursor.execute('SELECT * FROM member_location_history WHERE LOWER(name)=LOWER(?) ORDER BY start_date ASC, id ASC', (name.strip(),))
        else:
            cursor.execute('SELECT * FROM member_location_history ORDER BY name ASC, start_date ASC, id ASC')
        return [dict(r) for r in cursor.fetchall()]


def add_member_location_history(name, start_date, end_date, location):
    name = name.strip()
    start_date = normalize_date_fmt(start_date)
    end_date = normalize_date_fmt(end_date) if end_date and end_date.strip() else None
    location = location.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO member_location_history (name, start_date, end_date, location)
            VALUES (?, ?, ?, ?)
        ''', (name, start_date, end_date, location))
        conn.commit()
        return cursor.lastrowid


def delete_member_location_history(history_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM member_location_history WHERE id=?', (history_id,))
        conn.commit()


def update_member_location_history(history_id, name, start_date, end_date, location):
    name = name.strip()
    start_date = normalize_date_fmt(start_date)
    end_date = normalize_date_fmt(end_date) if end_date and end_date.strip() else None
    location = location.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE member_location_history
            SET name=?, start_date=?, end_date=?, location=?
            WHERE id=?
        ''', (name, start_date, end_date, location, history_id))
        conn.commit()


def get_member_location_at_date(name, date_str):
    if not name or not date_str:
        return '台灣辦公室'
    d_clean = normalize_date_fmt(date_str)
    with get_connection() as conn:
        cursor = conn.cursor()
        # Check history table for matching date range
        cursor.execute('''
            SELECT location FROM member_location_history
            WHERE LOWER(name) = LOWER(?)
              AND start_date <= ?
              AND (end_date IS NULL OR end_date = '' OR end_date >= ?)
            ORDER BY start_date DESC, id DESC
            LIMIT 1
        ''', (name.strip(), d_clean, d_clean))
        row = cursor.fetchone()
        if row and row['location']:
            return row['location']
        
        # Fallback to default location in team_members
        cursor.execute('SELECT COALESCE(location, "台灣辦公室") as location FROM team_members WHERE LOWER(name)=LOWER(?)', (name.strip(),))
        row = cursor.fetchone()
        if row and row['location']:
            return row['location']
            
    return '台灣辦公室'



def add_member(name, location='台灣辦公室'):
    name = name.strip()
    if not name:
        return None
    if not location:
        location = '台灣辦公室'
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO team_members (name, location) VALUES (?, ?)', (name, location))
        conn.commit()
        return cursor.lastrowid


def update_member_location(member_id, location):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE team_members SET location=? WHERE id=?', (location, member_id))
        conn.commit()


def delete_member(member_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM team_members WHERE id=?', (member_id,))
        row = cursor.fetchone()
        if row:
            m_name = row['name']
            cursor.execute('DELETE FROM overtime_records WHERE LOWER(name)=LOWER(?)', (m_name,))
            cursor.execute('DELETE FROM leave_records WHERE LOWER(name)=LOWER(?)', (m_name,))
        cursor.execute('DELETE FROM team_members WHERE id=?', (member_id,))
        conn.commit()



def parse_ym(date_str):
    try:
        parts = date_str.replace("-", "/").split("/")
        if len(parts) >= 3:
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return datetime.now().year, datetime.now().month


def add_overtime_record(date, name, time_str, hours, reason, note=None, eval_hours=None):
    note = parser.get_weekday_note(date)
    if eval_hours is None:
        eval_hours = hours
    y, m = parse_ym(date)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO overtime_records (date, name, time, hours, reason, note, eval_hours, year, month)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date, name, time_str, hours, reason, note, eval_hours, y, m))
        conn.commit()
        return cursor.lastrowid


def add_leave_record(date, name, leave_type, duration, google_comp_days, reason):
    y, m = parse_ym(date)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO leave_records (date, name, leave_type, duration, google_comp_days, reason, year, month)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date, name, leave_type, duration, google_comp_days, reason, y, m))
        conn.commit()
        return cursor.lastrowid


def bulk_insert(overtime_list, leave_list):
    inserted_ot_count = 0
    updated_ot_count = 0
    inserted_lv_count = 0
    updated_lv_count = 0

    with get_connection() as conn:
        cursor = conn.cursor()
        for ot in overtime_list:
            y, m = parse_ym(ot['date'])
            eval_h = ot.get('eval_hours', ot['hours'])
            is_special = int(bool(ot.get('is_special', 0)))
            special_reason = ot.get('special_reason', '') or ''
            if is_special:
                note = '假日加班'
            else:
                note = ot.get('note') or parser.get_weekday_note(ot['date'])

            # Check if record for same date and name already exists
            cursor.execute('''
                SELECT id FROM overtime_records 
                WHERE date=? AND LOWER(name)=LOWER(?)
                ORDER BY id ASC
            ''', (ot['date'], ot['name']))
            existing_rows = cursor.fetchall()

            if existing_rows:
                # Update first existing record
                first_id = existing_rows[0]['id']
                cursor.execute('''
                    UPDATE overtime_records
                    SET date=?, name=?, time=?, hours=?, reason=?, note=?, eval_hours=?, year=?, month=?, is_special=?, special_reason=?
                    WHERE id=?
                ''', (ot['date'], ot['name'], ot['time'], ot['hours'], ot['reason'], note, eval_h, y, m, is_special, special_reason, first_id))
                updated_ot_count += 1

                # Clean up any extra duplicate records for the same date & person
                if len(existing_rows) > 1:
                    extra_ids = [r['id'] for r in existing_rows[1:]]
                    placeholders = ','.join(['?'] * len(extra_ids))
                    cursor.execute(f'DELETE FROM overtime_records WHERE id IN ({placeholders})', extra_ids)
            else:
                # Insert new record
                cursor.execute('''
                    INSERT INTO overtime_records (date, name, time, hours, reason, note, eval_hours, year, month, is_special, special_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (ot['date'], ot['name'], ot['time'], ot['hours'], ot['reason'], note, eval_h, y, m, is_special, special_reason))
                inserted_ot_count += 1

        for lv in leave_list:
            y, m = parse_ym(lv['date'])
            # Check if record for same date, name, and leave_type already exists
            cursor.execute('''
                SELECT id FROM leave_records 
                WHERE date=? AND LOWER(name)=LOWER(?) AND leave_type=?
                ORDER BY id ASC
            ''', (lv['date'], lv['name'], lv['leave_type']))
            existing_rows = cursor.fetchall()

            if existing_rows:
                first_id = existing_rows[0]['id']
                cursor.execute('''
                    UPDATE leave_records
                    SET date=?, name=?, leave_type=?, duration=?, google_comp_days=?, reason=?, year=?, month=?
                    WHERE id=?
                ''', (lv['date'], lv['name'], lv['leave_type'], lv['duration'], lv['google_comp_days'], lv['reason'], y, m, first_id))
                updated_lv_count += 1

                if len(existing_rows) > 1:
                    extra_ids = [r['id'] for r in existing_rows[1:]]
                    placeholders = ','.join(['?'] * len(extra_ids))
                    cursor.execute(f'DELETE FROM leave_records WHERE id IN ({placeholders})', extra_ids)
            else:
                cursor.execute('''
                    INSERT INTO leave_records (date, name, leave_type, duration, google_comp_days, reason, year, month)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (lv['date'], lv['name'], lv['leave_type'], lv['duration'], lv['google_comp_days'], lv['reason'], y, m))
                inserted_lv_count += 1

        conn.commit()

    total_ot = inserted_ot_count + updated_ot_count
    total_lv = inserted_lv_count + updated_lv_count
    return total_ot, total_lv


def get_date_search_patterns(search_str):
    patterns = set()
    s = search_str.strip()
    if not s:
        return patterns, ''

    patterns.add(s)
    digits_only = re.sub(r'\D', '', s)

    parts = re.split(r'[/.\- ]+', s)
    if len(parts) == 2:
        try:
            m_val, d_val = int(parts[0]), int(parts[1])
            if 1 <= m_val <= 12 and 1 <= d_val <= 31:
                patterns.add(f"{m_val:02d}/{d_val:02d}")
                patterns.add(f"{m_val}/{d_val}")
                patterns.add(f"{m_val:02d}/{d_val}")
                patterns.add(f"{m_val}/{d_val:02d}")
                patterns.add(f"{m_val:02d}-{d_val:02d}")
                patterns.add(f"{m_val}-{d_val}")
        except ValueError:
            pass
    elif len(parts) == 3:
        try:
            y_val, m_val, d_val = int(parts[0]), int(parts[1]), int(parts[2])
            if 1 <= m_val <= 12 and 1 <= d_val <= 31:
                patterns.add(f"{y_val}/{m_val:02d}/{d_val:02d}")
                patterns.add(f"{y_val}/{m_val}/{d_val}")
                patterns.add(f"{y_val}-{m_val:02d}-{d_val:02d}")
        except ValueError:
            pass

    if digits_only:
        if len(digits_only) == 4:
            m_val, d_val = int(digits_only[:2]), int(digits_only[2:])
            if 1 <= m_val <= 12 and 1 <= d_val <= 31:
                patterns.add(f"{m_val:02d}/{d_val:02d}")
                patterns.add(f"{m_val}/{d_val}")
                patterns.add(f"{m_val:02d}/{d_val}")
                patterns.add(f"{m_val}/{d_val:02d}")
                patterns.add(f"{m_val:02d}-{d_val:02d}")
                patterns.add(f"{m_val}-{d_val}")
        elif len(digits_only) == 3:
            m_val, d_val = int(digits_only[:1]), int(digits_only[1:])
            if 1 <= m_val <= 12 and 1 <= d_val <= 31:
                patterns.add(f"{m_val:02d}/{d_val:02d}")
                patterns.add(f"{m_val}/{d_val}")
                patterns.add(f"{m_val:02d}/{d_val}")
                patterns.add(f"{m_val}/{d_val:02d}")
                patterns.add(f"{m_val:02d}-{d_val:02d}")
                patterns.add(f"{m_val}-{d_val}")
        elif len(digits_only) == 8:
            y_val, m_val, d_val = int(digits_only[:4]), int(digits_only[4:6]), int(digits_only[6:])
            if 1 <= m_val <= 12 and 1 <= d_val <= 31:
                patterns.add(f"{y_val}/{m_val:02d}/{d_val:02d}")
                patterns.add(f"{y_val}/{m_val}/{d_val}")
                patterns.add(f"{y_val}-{m_val:02d}-{d_val:02d}")

    return patterns, digits_only


def get_overtime_records(month=None, name=None, search=None, ot_type=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM overtime_records WHERE 1=1"
        params = []
        
        if month:
            # month format 'YYYY/MM'
            m_clean = month.replace("-", "/")
            parts = m_clean.split('/')
            if len(parts) == 2:
                y_str = parts[0]
                m_int = int(parts[1])
                # Match both 2025/7/ and 2025/07/
                query += " AND (date LIKE ? OR date LIKE ?)"
                params.extend([f"{y_str}/{m_int:02d}/%", f"{y_str}/{m_int}/%"])
            else:
                query += " AND date LIKE ?"
                params.append(f"{m_clean}%")
            
        if name and name.strip():
            query += " AND LOWER(name) LIKE ?"
            params.append(f"%{name.strip().lower()}%")

        if ot_type and ot_type.strip():
            query += " AND note = ?"
            params.append(ot_type.strip())
            
        if search and search.strip():
            s_clean = search.strip().lower()
            s_val = f"%{s_clean}%"
            date_patterns, digits_only = get_date_search_patterns(search)
            
            conds = ["LOWER(name) LIKE ?", "LOWER(reason) LIKE ?", "LOWER(note) LIKE ?", "date LIKE ?"]
            s_params = [s_val, s_val, s_val, s_val]

            if digits_only:
                conds.append("REPLACE(REPLACE(date, '/', ''), '-', '') LIKE ?")
                s_params.append(f"%{digits_only}%")

            for dp in date_patterns:
                conds.append("date LIKE ?")
                s_params.append(f"%{dp}%")

            query += " AND (" + " OR ".join(conds) + ")"
            params.extend(s_params)

            
        query += " ORDER BY date ASC, name ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_asw_export_data(month=None):
    if not month:
        month = "2026/07"
    records = get_overtime_records(month=month)
    
    m_clean = month.replace('/', '-')
    parts = m_clean.split('-')
    if len(parts) == 2:
        m_clean = f"{parts[0]}-{int(parts[1]):02d}"
    title = f"ASW_加班補休時數管控申請表_{m_clean}"

    members_map = {}
    for r in records:
        name = r['name']
        if name not in members_map:
            members_map[name] = []
        members_map[name].append(r)

    sorted_names = sorted(members_map.keys())

    rows = []
    total_hours = 0.0

    for name in sorted_names:
        m_recs = sorted(members_map[name], key=lambda x: x['date'])
        
        for r in m_recs:
            d_parts = r['date'].replace('-', '/').split('/')
            if len(d_parts) == 3:
                d_fmt = f"{d_parts[0]}/{int(d_parts[1])}/{int(d_parts[2])}"
            else:
                d_fmt = r['date']

            is_sp = bool(r.get('is_special'))
            note_val = r.get('note') or ('假日加班' if is_sp else '平日加班')
            
            h = float(r['hours'] or 0.0)
            h_fmt = int(h) if h.is_integer() else h
            total_hours += h

            rows.append({
                "date": d_fmt,
                "name": r['name'],
                "time": r['time'],
                "hours": h_fmt,
                "reason": r['reason'],
                "note": note_val,
                "eval_hours": h_fmt,
                "is_empty": False
            })

        # Empty line separator between members
        rows.append({
            "date": "", "name": "", "time": "", "hours": "", "reason": "", "note": "", "eval_hours": "",
            "is_empty": True
        })

    return title, rows, round(total_hours, 2)


def get_leave_records(month=None, name=None, leave_types=None, search=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM leave_records WHERE 1=1"
        params = []
        
        if month:
            m_clean = month.replace("-", "/")
            parts = m_clean.split('/')
            if len(parts) == 2:
                y_str = parts[0]
                m_int = int(parts[1])
                query += " AND (date LIKE ? OR date LIKE ?)"
                params.extend([f"{y_str}/{m_int:02d}/%", f"{y_str}/{m_int}/%"])
            else:
                query += " AND date LIKE ?"
                params.append(f"{m_clean}%")
            
        if name and name.strip():
            query += " AND LOWER(name) LIKE ?"
            params.append(f"%{name.strip().lower()}%")
            
        if leave_types and len(leave_types) > 0:
            placeholders = ",".join(["?"] * len(leave_types))
            query += f" AND leave_type IN ({placeholders})"
            params.extend(leave_types)
            
        if search and search.strip():
            s_clean = search.strip().lower()
            s_val = f"%{s_clean}%"
            date_patterns, digits_only = get_date_search_patterns(search)
            
            conds = ["LOWER(name) LIKE ?", "LOWER(reason) LIKE ?", "LOWER(leave_type) LIKE ?", "date LIKE ?"]
            s_params = [s_val, s_val, s_val, s_val]

            if digits_only:
                conds.append("REPLACE(REPLACE(date, '/', ''), '-', '') LIKE ?")
                s_params.append(f"%{digits_only}%")

            for dp in date_patterns:
                conds.append("date LIKE ?")
                s_params.append(f"%{dp}%")

            query += " AND (" + " OR ".join(conds) + ")"
            params.extend(s_params)
            
        query += " ORDER BY date ASC, name ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def update_overtime_record(rec_id, date, name, time_str, hours, reason, note, eval_hours, is_special=0, special_reason=''):
    y, m = parse_ym(date)
    is_special_int = int(bool(is_special))
    if is_special_int:
        note = '假日加班'
    elif not note or note == "":
        note = parser.get_weekday_note(date)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE overtime_records
            SET date=?, name=?, time=?, hours=?, reason=?, note=?, eval_hours=?, year=?, month=?,
                is_special=?, special_reason=?
            WHERE id=?
        ''', (date, name, time_str, hours, reason, note, eval_hours, y, m,
              is_special_int, special_reason or '', rec_id))
        conn.commit()


def update_leave_record(rec_id, date, name, leave_type, duration, google_comp_days, reason):
    y, m = parse_ym(date)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE leave_records
            SET date=?, name=?, leave_type=?, duration=?, google_comp_days=?, reason=?, year=?, month=?
            WHERE id=?
        ''', (date, name, leave_type, duration, google_comp_days, reason, y, m, rec_id))
        conn.commit()


def delete_overtime_record(rec_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM overtime_records WHERE id=?", (rec_id,))
        conn.commit()


def delete_leave_record(rec_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leave_records WHERE id=?", (rec_id,))
        conn.commit()


def get_monthly_stats(month=None):
    """
    Returns monthly summary matching image 2 style:
    - Overtime hours per person & Team Total
    - Leave breakdown per person (病假, 事假, 黑假, WFH, 因公外出, Google補休天數)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Build month clause
        m_clause = ""
        m_params = []
        if month:
            m_clean = month.replace("-", "/")
            parts = m_clean.split('/')
            if len(parts) == 2:
                y_str = parts[0]
                m_int = int(parts[1])
                m_clause = " AND (date LIKE ? OR date LIKE ?)"
                m_params = [f"{y_str}/{m_int:02d}/%", f"{y_str}/{m_int}/%"]
            else:
                m_clause = " AND date LIKE ?"
                m_params = [f"{m_clean}%"]

        # 1. Get list of active team members
        db_members = get_all_members()
        names = [m['name'] for m in db_members]
        
        # Fallback: distinct names from records if team_members table is empty
        if not names:
            query_names = f'''
                SELECT DISTINCT name FROM (
                    SELECT name FROM overtime_records WHERE 1=1 {m_clause}
                    UNION
                    SELECT name FROM leave_records WHERE 1=1 {m_clause}
                ) ORDER BY name ASC
            '''
            cursor.execute(query_names, m_params + m_params)
            names = [r[0] for r in cursor.fetchall()]

        stats_list = []
        team_total_hours = 0.0
        team_weekday_hours = 0.0
        team_weekend_hours = 0.0
        
        for name in names:
            # Overtime breakdown: query all overtime records for this member
            ot_query = f"SELECT date, hours, note, is_special, special_reason, reason FROM overtime_records WHERE LOWER(name) = LOWER(?){m_clause}"
            ot_params = [name] + m_params
            cursor.execute(ot_query, ot_params)
            ot_rows = cursor.fetchall()
            
            ot_count = len(ot_rows)
            weekday_ot_hours = 0.0
            weekend_ot_hours = 0.0
            special_ot_count = 0
            special_reasons_list = []
            
            location_ot_summary = {}

            for r in ot_rows:
                h = float(r['hours'] or 0.0)
                is_sp = bool(r['is_special'])
                sp_reason = (r['special_reason'] or '').strip()
                gen_reason = (r['reason'] or '').strip()
                note = r['note'] or ''
                r_date = r['date']
                
                loc = get_member_location_at_date(name, r_date)
                if loc not in location_ot_summary:
                    location_ot_summary[loc] = {
                        "ot_count": 0,
                        "weekday_hours": 0.0,
                        "weekend_hours": 0.0,
                        "total_hours": 0.0
                    }
                location_ot_summary[loc]["ot_count"] += 1
                location_ot_summary[loc]["total_hours"] += h

                if is_sp or note == '假日加班':
                    weekend_ot_hours += h
                    location_ot_summary[loc]["weekend_hours"] += h
                    if is_sp:
                        special_ot_count += 1
                        special_reasons_list.append(sp_reason or gen_reason or '特殊狀況')
                else:
                    weekday_ot_hours += h
                    location_ot_summary[loc]["weekday_hours"] += h

            ot_hours = weekday_ot_hours + weekend_ot_hours
            team_total_hours += ot_hours
            team_weekday_hours += weekday_ot_hours
            team_weekend_hours += weekend_ot_hours

            # If no overtime records, query default location for member in that month
            if not location_ot_summary:
                curr_loc = get_member_location_at_date(name, f"{month or '2026/07'}/15")
                location_ot_summary[curr_loc] = {
                    "ot_count": 0,
                    "weekday_hours": 0.0,
                    "weekend_hours": 0.0,
                    "total_hours": 0.0
                }

            location_breakdown = []
            for loc_name, loc_data in location_ot_summary.items():
                location_breakdown.append({
                    "location": loc_name,
                    "ot_count": loc_data["ot_count"],
                    "weekday_hours": round(loc_data["weekday_hours"], 2),
                    "weekend_hours": round(loc_data["weekend_hours"], 2),
                    "total_hours": round(loc_data["total_hours"], 2)
                })

            # Leaves details
            lv_query = f"SELECT leave_type, duration, google_comp_days FROM leave_records WHERE LOWER(name) = LOWER(?){m_clause}"
            lv_params = [name] + m_params
            cursor.execute(lv_query, lv_params)
            leaves = cursor.fetchall()
            
            sick_days = 0.0
            personal_days = 0.0
            black_days = 0.0
            wfh_days = 0.0
            business_count = 0
            google_comp_total = 0.0
            
            leave_summary = {}
            for l in leaves:
                lt = l['leave_type']
                dur_str = str(l['duration'])
                dur_val = 0.5 if ('0.5' in dur_str or '半天' in dur_str) else 1.0
                comp = l['google_comp_days'] or 0.0
                
                google_comp_total += comp
                
                if lt not in leave_summary:
                    leave_summary[lt] = {'days': 0.0, 'count': 0}
                leave_summary[lt]['days'] += dur_val
                leave_summary[lt]['count'] += 1
                
                if lt == '病假':
                    sick_days += dur_val
                elif lt == '事假':
                    personal_days += dur_val
                elif lt == '黑假':
                    black_days += dur_val
                elif lt == 'WFH':
                    wfh_days += dur_val
                elif lt == '因公外出':
                    business_count += 1

            leave_breakdown = []
            for lt, ddata in leave_summary.items():
                if lt in ['因公外出', '出勤確認']:
                    label = f"{lt} {ddata['count']}次"
                else:
                    d_val = ddata['days']
                    d_str = f"{int(d_val)}天" if d_val.is_integer() else f"{d_val}天"
                    label = f"{lt} {d_str}"
                leave_breakdown.append({"type": lt, "label": label})

            stats_list.append({
                "name": name,
                "location": get_member_location_at_date(name, f"{month or '2026/07'}/15"),
                "location_breakdown": location_breakdown,
                "ot_count": ot_count,
                "leave_count": len(leaves),
                "weekday_ot_hours": round(weekday_ot_hours, 2),
                "weekend_ot_hours": round(weekend_ot_hours, 2),
                "overtime_hours": round(ot_hours, 2),
                "special_ot_count": special_ot_count,
                "special_reasons": list(dict.fromkeys(special_reasons_list)),
                "leave_breakdown": leave_breakdown,
                "sick_days": sick_days,
                "personal_days": personal_days,
                "black_days": black_days,
                "wfh_days": wfh_days,
                "business_count": business_count,
                "google_comp_total": round(google_comp_total, 2)
            })

        return {
            "stats": stats_list,
            "team_total_hours": round(team_total_hours, 2),
            "team_weekday_hours": round(team_weekday_hours, 2),
            "team_weekend_hours": round(team_weekend_hours, 2)
        }
