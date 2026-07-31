import re
from datetime import datetime

# Known team members list to help parser recognize names accurately
KNOWN_NAMES = [
    "Benny", "Daniel", "Eden", "YiWen", "Xavier", 
    "Winnie", "Kevin", "Cora", "Benson", "Jim", "Luc", "Rell", "Farglory"
]

LEAVE_META = {
    "黑假": {"type": "黑假", "google_comp": 1.0},
    "WFH": {"type": "WFH", "google_comp": 0.5},
    "ＷＦＨ": {"type": "WFH", "google_comp": 0.5},
    "病假": {"type": "病假", "google_comp": 0.0},
    "事假": {"type": "事假", "google_comp": 0.0},
    "因公外出": {"type": "因公外出", "google_comp": 0.0},
    "公出": {"type": "因公外出", "google_comp": 0.0},
    "出差": {"type": "因公外出", "google_comp": 0.0},
    "特休": {"type": "特休", "google_comp": 0.0},
    "生理假": {"type": "生理假", "google_comp": 0.0},
    "出勤確認": {"type": "出勤確認", "google_comp": 0.0},
    "未刷卡": {"type": "出勤確認", "google_comp": 0.0},
    "忘了帶卡": {"type": "出勤確認", "google_comp": 0.0},
    "待補出勤確認": {"type": "出勤確認", "google_comp": 0.0},
}


def parse_time_range(time_str):
    """
    Parses strings like '19:00-22:30', '1900 - 21:00', '21:00-0130', '1900-2000', '2330-0230'
    Returns normalized string (HH:MM-HH:MM) and calculated hours float.
    """
    clean_str = time_str.replace(" ", "")
    m = re.match(r'^(\d{1,2}:?\d{2})[-~—](\d{1,2}:?\d{2})$', clean_str)
    if not m:
        return None, 0.0
    
    start_raw, end_raw = m.group(1), m.group(2)
    
    def normalize_hm(raw):
        if ":" in raw:
            parts = raw.split(":")
            h, mins = int(parts[0]), int(parts[1])
        else:
            if len(raw) == 3:
                h, mins = int(raw[0]), int(raw[1:])
            else:
                h, mins = int(raw[:2]), int(raw[2:])
        return h, mins

    sh, sm = normalize_hm(start_raw)
    eh, em = normalize_hm(end_raw)
    
    start_total_mins = sh * 60 + sm
    end_total_mins = eh * 60 + em
    
    if end_total_mins <= start_total_mins:
        end_total_mins += 24 * 60
        
    duration_mins = end_total_mins - start_total_mins
    hours = round(duration_mins / 60.0, 2)
    
    norm_start = f"{sh:02d}:{sm:02d}"
    norm_end = f"{eh:02d}:{em:02d}"
    norm_time_str = f"{norm_start}-{norm_end}"
    
    return norm_time_str, hours


def get_weekday_note(date_str):
    """
    Given 'YYYY/M/D' or 'YYYY/MM/DD', calculates weekday.
    Returns '平日加班' for Mon-Fri, '假日加班' for Sat-Sun.
    """
    try:
        parts = date_str.replace("-", "/").split("/")
        if len(parts) == 3:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            dt = datetime(year, month, day)
            if dt.weekday() in (5, 6):
                return "假日加班"
            else:
                return "平日加班"
    except Exception:
        pass
    return "平日加班"


def parse_raw_text(text_block, default_year=2025):
    """
    Parses unstructured multi-line text input into structured overtime and leave records.
    """
    overtime_records = []
    leave_records = []
    
    lines = text_block.strip().split('\n')
    current_date = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if line starts with a date pattern (e.g. "7/27", "0731", "2025/7/27")
        date_match = re.match(r'^((\d{4}[/-])?\d{1,2}[/-]\d{1,2}|\b\d{4}\b)', line)
        if date_match:
            raw_date = date_match.group(1)
            rest_of_line = line[len(raw_date):].strip()
            
            if '/' in raw_date or '-' in raw_date:
                parts = re.split(r'[/-]', raw_date)
                if len(parts) == 3:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                else:
                    y, m, d = default_year, int(parts[0]), int(parts[1])
            else:
                if len(raw_date) == 4:
                    y = default_year
                    m = int(raw_date[:2])
                    d = int(raw_date[2:])
                else:
                    y, m, d = default_year, 1, 1
                    
            current_date = f"{y}/{m:02d}/{d:02d}"
        else:
            rest_of_line = line

        if not current_date:
            current_date = f"{default_year}/07/01"

        # Find names positions
        name_matches = []
        for name in KNOWN_NAMES:
            for match in re.finditer(r'\b' + re.escape(name) + r'\b', rest_of_line, re.IGNORECASE):
                name_matches.append((match.start(), match.end(), match.group(0)))
                
        name_matches.sort(key=lambda x: x[0])
        
        if not name_matches:
            continue

        # Split rest_of_line into segments based on names
        segments = []
        for i in range(len(name_matches)):
            start_pos = name_matches[i][0]
            end_pos = name_matches[i+1][0] if i + 1 < len(name_matches) else len(rest_of_line)
            segment_text = rest_of_line[start_pos:end_pos].strip()
            segments.append(segment_text)

        # Process each segment grouping multi-person actions
        idx = 0
        while idx < len(segments):
            seg_names = []
            cur_idx = idx
            
            while cur_idx < len(segments):
                m_name = re.match(r'^(' + '|'.join(re.escape(n) for n in KNOWN_NAMES) + r')\b(.*)', segments[cur_idx], re.IGNORECASE)
                if m_name:
                    found_name = m_name.group(1).capitalize()
                    rem = m_name.group(2).strip()
                    seg_names.append(found_name)
                    
                    if rem and not any(re.match(r'^' + re.escape(n) + r'\b', rem, re.IGNORECASE) for n in KNOWN_NAMES):
                        break
                    elif not rem:
                        cur_idx += 1
                    else:
                        cur_idx += 1
                else:
                    break
                    
            if not seg_names:
                idx += 1
                continue

            task_text = " ".join(segments[idx:max(cur_idx+1, idx+1)])
            idx = max(cur_idx + 1, idx + 1)
            
            # Check for time range (overtime)
            time_match = re.search(r'(\d{1,2}:?\d{2}\s*[-~—]\s*\d{1,2}:?\d{2})', task_text)
            
            if time_match:
                raw_time_str = time_match.group(1)
                norm_time, hours = parse_time_range(raw_time_str)
                
                reason = task_text
                for n in seg_names:
                    reason = re.sub(r'\b' + re.escape(n) + r'\b', '', reason, flags=re.IGNORECASE)
                reason = reason.replace(raw_time_str, '').strip()
                reason = re.sub(r'^[,\s:]+', '', reason)
                if not reason:
                    reason = "加班處理公務"
                    
                note = get_weekday_note(current_date)
                
                for person in seg_names:
                    overtime_records.append({
                        "date": current_date,
                        "name": person,
                        "time": norm_time or raw_time_str,
                        "hours": hours,
                        "reason": reason,
                        "note": note,
                        "eval_hours": hours
                    })
            else:
                # Check for leave types (may contain multiple leave types in task_text)
                detected_leaves = []
                for kw, meta in LEAVE_META.items():
                    if kw in task_text:
                        # Avoid duplicating WFH / ＷＦＨ
                        type_name = meta["type"]
                        if not any(d["type"] == type_name for d in detected_leaves):
                            duration = "1天"
                            comp = meta["google_comp"]
                            if "半天" in task_text or "0.5" in task_text:
                                duration = "0.5天"
                                if type_name in ["黑假", "WFH"]:
                                    comp = 0.5
                            detected_leaves.append({
                                "type": type_name,
                                "duration": duration,
                                "comp": comp
                            })
                            
                if detected_leaves:
                    for person in seg_names:
                        reason = task_text
                        reason = re.sub(r'\b' + re.escape(person) + r'\b', '', reason, flags=re.IGNORECASE).strip()
                        
                        for item in detected_leaves:
                            leave_records.append({
                                "date": current_date,
                                "name": person,
                                "leave_type": item["type"],
                                "duration": item["duration"],
                                "google_comp_days": item["comp"],
                                "reason": reason if reason else task_text
                            })
                else:
                    for person in seg_names:
                        leave_records.append({
                            "date": current_date,
                            "name": person,
                            "leave_type": "備註說明",
                            "duration": "1天",
                            "google_comp_days": 0.0,
                            "reason": task_text
                        })

    return overtime_records, leave_records
