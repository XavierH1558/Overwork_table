import re
from datetime import datetime

# Known team members list to help parser recognize names accurately
KNOWN_NAMES = [
    "Benny", "Daniel", "Eden", "YiWen", "Xavier", 
    "Winnie", "Kevin", "Cora", "Benson", "Jim", "Rell"
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


def parse_raw_text(text_block, default_year=2025, known_names=None):
    """
    Parses unstructured multi-line text input into structured overtime, leave records, and warnings.
    Returns: overtime_records, leave_records, warning_records
    """
    if known_names is None:
        try:
            import database
            db_members = database.get_all_members()
            known_names = [m['name'] for m in db_members]
        except Exception:
            known_names = KNOWN_NAMES

    if not known_names:
        known_names = KNOWN_NAMES

    overtime_records = []
    leave_records = []
    warning_records = []
    
    lines = text_block.strip().split('\n')
    current_date = f"{default_year}/07/01"
    
    for line_idx, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
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

        # Extract all time ranges in this line along with their positions
        time_matches = list(re.finditer(r'(\d{1,2}:?\d{2}\s*[-~—]\s*\d{1,2}:?\d{2})', rest_of_line))
        
        # Find names positions that mark new record blocks
        name_matches = []
        for name in known_names:
            pattern = r'(?<![a-zA-Z0-9_])' + re.escape(name) + r'(?![a-zA-Z0-9_])'
            for match in re.finditer(pattern, rest_of_line, re.IGNORECASE):
                pos = match.start()
                before_text = rest_of_line[:pos].rstrip()
                if before_text and any(before_text.endswith(verb) for verb in ["幫忙", "協助", "找", "與", "with", "for", "to"]):
                    continue
                name_matches.append((match.start(), match.end(), match.group(0)))
                
        name_matches.sort(key=lambda x: x[0])
        
        if not name_matches:
            if rest_of_line:
                warning_records.append({
                    "line": line_idx,
                    "raw": raw_line,
                    "reason": "未找到認識的團隊成員姓名"
                })
            continue

        # Split rest_of_line into segments based on names
        segments = []
        for i in range(len(name_matches)):
            start_pos = name_matches[i][0]
            end_pos = name_matches[i+1][0] if i + 1 < len(name_matches) else len(rest_of_line)
            segment_text = rest_of_line[start_pos:end_pos].strip()
            segments.append(segment_text)

        # Pre-name time context (if time is before names, e.g. "0713 1900-2000 Kevin, Cora...")
        line_prefix_time = None
        if time_matches and time_matches[0].start() < name_matches[0][0]:
            line_prefix_time = time_matches[0].group(1)

        # Process each segment
        idx = 0
        while idx < len(segments):
            seg_names = []
            cur_idx = idx
            
            while cur_idx < len(segments):
                m_name = re.match(r'^(' + '|'.join(re.escape(n) for n in known_names) + r')(?![a-zA-Z0-9_])(.*)', segments[cur_idx], re.IGNORECASE)
                if m_name:
                    found_name = m_name.group(1).capitalize()
                    rem = m_name.group(2).strip()
                    seg_names.append(found_name)
                    
                    if rem and not any(re.match(r'^' + re.escape(n) + r'(?![a-zA-Z0-9_])', rem, re.IGNORECASE) for n in known_names):
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
            
            # Check for leave types
            detected_leaves = []
            for kw, meta in LEAVE_META.items():
                if kw in task_text:
                    type_name = meta["type"]
                    if type_name == "WFH":
                        type_name = "黑假"
                        duration = "0.5天"
                        comp = 0.5
                    else:
                        duration = "1天"
                        comp = meta["google_comp"]
                        if "半天" in task_text or "0.5" in task_text:
                            duration = "0.5天"
                            if type_name in ["黑假"]:
                                comp = 0.5

                    if not any(d["type"] == type_name for d in detected_leaves):
                        detected_leaves.append({
                            "type": type_name,
                            "duration": duration,
                            "comp": comp
                        })

            # Check for time range in task_text or inherit line_prefix_time
            time_match = re.search(r'(\d{1,2}:?\d{2}\s*[-~—]\s*\d{1,2}:?\d{2})', task_text)
            raw_time_str = time_match.group(1) if time_match else line_prefix_time
            
            if detected_leaves:
                for person in seg_names:
                    clean_reason = task_text
                    clean_reason = re.sub(r'(?<![a-zA-Z0-9_])' + re.escape(person) + r'(?![a-zA-Z0-9_])', '', clean_reason, flags=re.IGNORECASE).strip()
                    if raw_time_str:
                        clean_reason = clean_reason.replace(raw_time_str, '').strip()
                    
                    for kw in ["黑假", "病假", "事假", "特休", "生理假"]:
                        clean_reason = clean_reason.replace(kw, '')
                        
                    clean_reason = re.sub(r'(要請|申請|請假|一天|半天|0\.5天|\d+天)', '', clean_reason).strip()
                    clean_reason = re.sub(r'^[,\s，:]+|[,\s，:]+$', '', clean_reason).strip()

                    for item in detected_leaves:
                        if item["type"] == "出勤確認":
                            final_reason = "早上未刷卡，補出勤確認"
                        else:
                            final_reason = clean_reason if clean_reason else "-"

                        leave_records.append({
                            "date": current_date,
                            "name": person,
                            "leave_type": item["type"],
                            "duration": item["duration"],
                            "google_comp_days": item["comp"],
                            "reason": final_reason
                        })
            elif raw_time_str:
                norm_time, hours = parse_time_range(raw_time_str)
                
                reason = task_text
                for n in seg_names:
                    reason = re.sub(r'\b' + re.escape(n) + r'\b', '', reason, flags=re.IGNORECASE)
                if time_match:
                    reason = reason.replace(time_match.group(1), '').strip()
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

    return overtime_records, leave_records, warning_records
