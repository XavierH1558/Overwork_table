import sqlite3
import os
from datetime import datetime
import parser

DB_PATH = os.path.join(os.path.dirname(__file__), 'attendance.db')

def get_connection():
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Populate initial default members if table is empty
        cursor.execute('SELECT COUNT(*) FROM team_members')
        if cursor.fetchone()[0] == 0:
            default_members = ["Benny", "Daniel", "Eden", "YiWen", "Xavier", "Winnie", "Kevin", "Cora", "Benson", "Jim", "Rell"]
            for m in default_members:
                cursor.execute('INSERT OR IGNORE INTO team_members (name) VALUES (?)', (m,))

        conn.commit()


def get_all_members():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name FROM team_members ORDER BY name ASC')
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def add_member(name):
    name = name.strip()
    if not name:
        return None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO team_members (name) VALUES (?)', (name,))
        conn.commit()
        return cursor.lastrowid


def delete_member(member_id):
    with get_connection() as conn:
        cursor = conn.cursor()
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
    if note is None or note == "":
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
    inserted_lv_count = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for ot in overtime_list:
            # Check if record with same date, name, and time already exists
            cursor.execute('''
                SELECT id FROM overtime_records 
                WHERE date=? AND LOWER(name)=LOWER(?) AND time=?
            ''', (ot['date'], ot['name'], ot['time']))
            if cursor.fetchone() is not None:
                continue

            y, m = parse_ym(ot['date'])
            note = ot.get('note') or parser.get_weekday_note(ot['date'])
            eval_h = ot.get('eval_hours', ot['hours'])
            cursor.execute('''
                INSERT INTO overtime_records (date, name, time, hours, reason, note, eval_hours, year, month)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ot['date'], ot['name'], ot['time'], ot['hours'], ot['reason'], note, eval_h, y, m))
            inserted_ot_count += 1
            
        for lv in leave_list:
            # Check if record with same date, name, and leave_type already exists
            cursor.execute('''
                SELECT id FROM leave_records 
                WHERE date=? AND LOWER(name)=LOWER(?) AND leave_type=?
            ''', (lv['date'], lv['name'], lv['leave_type']))
            if cursor.fetchone() is not None:
                continue

            y, m = parse_ym(lv['date'])
            cursor.execute('''
                INSERT INTO leave_records (date, name, leave_type, duration, google_comp_days, reason, year, month)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (lv['date'], lv['name'], lv['leave_type'], lv['duration'], lv['google_comp_days'], lv['reason'], y, m))
            inserted_lv_count += 1
            
        conn.commit()
    return inserted_ot_count, inserted_lv_count


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
            query += " AND (LOWER(name) LIKE ? OR LOWER(reason) LIKE ? OR LOWER(note) LIKE ? OR date LIKE ?)"
            s_val = f"%{search.strip().lower()}%"
            params.extend([s_val, s_val, s_val, s_val])
            
        query += " ORDER BY date ASC, name ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


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
            query += " AND (LOWER(name) LIKE ? OR LOWER(reason) LIKE ? OR LOWER(leave_type) LIKE ? OR date LIKE ?)"
            s_val = f"%{search.strip().lower()}%"
            params.extend([s_val, s_val, s_val, s_val])
            
        query += " ORDER BY date ASC, name ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def update_overtime_record(rec_id, date, name, time_str, hours, reason, note, eval_hours):
    y, m = parse_ym(date)
    if not note or note == "":
        note = parser.get_weekday_note(date)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE overtime_records
            SET date=?, name=?, time=?, hours=?, reason=?, note=?, eval_hours=?, year=?, month=?
            WHERE id=?
        ''', (date, name, time_str, hours, reason, note, eval_hours, y, m, rec_id))
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

        # 1. Get list of all distinct names across both tables
        query_names = f'''
            SELECT DISTINCT name FROM (
                SELECT name FROM overtime_records WHERE 1=1 {m_clause}
                UNION
                SELECT name FROM leave_records WHERE 1=1 {m_clause}
            ) ORDER BY name ASC
        '''
        cursor.execute(query_names, m_params + m_params)
        names = [r[0] for r in cursor.fetchall()]
        
        # Fallback names list if database is empty
        if not names:
            db_m = get_all_members()
            names = [m['name'] for m in db_m]

        stats_list = []
        team_total_hours = 0.0
        
        for name in names:
            # Overtime total
            ot_query = f"SELECT SUM(hours) FROM overtime_records WHERE LOWER(name) = LOWER(?){m_clause}"
            ot_params = [name] + m_params
            cursor.execute(ot_query, ot_params)
            res = cursor.fetchone()
            ot_hours = round(res[0] or 0.0, 2)
            team_total_hours += ot_hours

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
            
            for l in leaves:
                lt = l['leave_type']
                dur_str = str(l['duration'])
                dur_val = 0.5 if ('0.5' in dur_str or '半天' in dur_str) else 1.0
                comp = l['google_comp_days'] or 0.0
                
                google_comp_total += comp
                
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

            stats_list.append({
                "name": name,
                "overtime_hours": ot_hours,
                "sick_days": sick_days,
                "personal_days": personal_days,
                "black_days": black_days,
                "wfh_days": wfh_days,
                "business_count": business_count,
                "google_comp_total": round(google_comp_total, 2)
            })

        return {
            "stats": stats_list,
            "team_total_hours": round(team_total_hours, 2)
        }
