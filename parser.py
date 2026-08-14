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
    "忘了刷卡": {"type": "出勤確認", "google_comp": 0.0},
    "忘刷卡": {"type": "出勤確認", "google_comp": 0.0},
    "沒刷卡": {"type": "出勤確認", "google_comp": 0.0},
    "待補出勤確認": {"type": "出勤確認", "google_comp": 0.0},
    "補出勤確認": {"type": "出勤確認", "google_comp": 0.0},
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


def parse_all_dates(text, default_year=2026):
    dates = []
    # 1. Date ranges: e.g. 8/13-8/15 or 8/13~8/15 or 8/13至8/15
    m_range = re.search(r'(\d{1,2})[/-](\d{1,2})\s*[-~—至]\s*(\d{1,2})[/-](\d{1,2})', text)
    if m_range:
        m1, d1, m2, d2 = int(m_range.group(1)), int(m_range.group(2)), int(m_range.group(3)), int(m_range.group(4))
        if m1 == m2 and d2 >= d1:
            for d in range(d1, d2 + 1):
                dates.append(f"{default_year}/{m1:02d}/{d:02d}")
            return dates

    # 2. Date list with M/D: e.g. 8/13, 8/14, 8/17
    found_mds = re.findall(r'(\d{1,2})[/-](\d{1,2})', text)
    if found_mds:
        for m_str, d_str in found_mds:
            d_val = f"{default_year}/{int(m_str):02d}/{int(d_str):02d}"
            if d_val not in dates:
                dates.append(d_val)
                
    if len(found_mds) == 1:
        sub_text = text[text.find(f"{found_mds[0][0]}/{found_mds[0][1]}"):]
        extra_days = re.findall(r'[,，、\s]+(\d{1,2})\b', sub_text)
        for ed in extra_days:
            ed_val = int(ed)
            if 1 <= ed_val <= 31:
                d_val = f"{default_year}/{int(found_mds[0][0]):02d}/{ed_val:02d}"
                if d_val not in dates:
                    dates.append(d_val)

    if not dates:
        found_4d = re.findall(r'\b(0[1-9]|1[0-2])([0-2][0-9]|3[01])\b', text)
        for m_str, d_str in found_4d:
            d_val = f"{default_year}/{int(m_str):02d}/{int(d_str):02d}"
            if d_val not in dates:
                dates.append(d_val)

    return dates


def process_leave_task(task_text, seg_names, fallback_date, default_year=2026):
    date_list_pattern = r'(\d)\s*[,，]\s*(\d)'
    protected_text = re.sub(date_list_pattern, r'\1__COMMA__\2', task_text)
    protected_text = re.sub(date_list_pattern, r'\1__COMMA__\2', protected_text)

    # Protect parenthetical content e.g. (看醫生) -> __PAREN_0__
    parens = []
    def _mask_paren(m):
        parens.append(m.group(0))
        return f" __PAREN_{len(parens)-1}__ "

    protected_text = re.sub(r'[\(\（][^\)\）]+[\)\）]', _mask_paren, protected_text)

    raw_clauses = re.split(r'[,，;；]', protected_text)
    raw_clauses = [c.replace('__COMMA__', ', ').strip() for c in raw_clauses if c.strip()]

    # Unmask parens in raw clauses
    unmasked_clauses = []
    for c in raw_clauses:
        for p_idx, p_val in enumerate(parens):
            c = c.replace(f"__PAREN_{p_idx}__", p_val)
        unmasked_clauses.append(c)

    # Merge continuation clauses (clauses with no leave keyword, no date, and no person name) into previous clause
    merged_clauses = []
    for c in unmasked_clauses:
        has_kw = any(kw in c or kw.lower() in c.lower() for kw in LEAVE_META.keys())
        has_dt = len(parse_all_dates(c, default_year)) > 0
        has_person = any(re.search(r'(?<![a-zA-Z0-9_])' + re.escape(n) + r'(?![a-zA-Z0-9_])', c, re.IGNORECASE) for n in KNOWN_NAMES)
        
        if not has_kw and not has_dt and not has_person and merged_clauses:
            merged_clauses[-1] = merged_clauses[-1] + ' ' + c
        else:
            merged_clauses.append(c)

    leave_records = []
    seen_keys = set()
    line_fallback_dates = parse_all_dates(task_text, default_year)

    for clause in merged_clauses:
        # Find all matching keywords with their start positions in the clause
        matches = []
        clause_lower = clause.lower()
        for kw, meta in LEAVE_META.items():
            kw_lower = kw.lower()
            pos = clause_lower.find(kw_lower)
            if pos != -1:
                matches.append((pos, -len(kw), kw, meta))
                
        matched_kw = None
        matched_type = None
        matched_meta = None
        if matches:
            matches.sort()  # Sort by position ascending (earliest first), then length descending
            _, _, matched_kw, matched_meta = matches[0]
            matched_type = matched_meta["type"]
            if matched_type == "WFH":
                matched_type = "黑假"
                
        if matched_type:
            c_dates = parse_all_dates(clause, default_year)
            if not c_dates:
                c_dates = line_fallback_dates if line_fallback_dates else [fallback_date]
                
            is_wfh = 'WFH' in clause.upper() or 'ＷＦＨ' in clause or (matched_kw in ['WFH', 'ＷＦＨ'])
            half_day_keywords = ['半天', '0.5', '上午', '下午', '早上', '上半天', '下半天', '上半日', '下半日', '早退']
            is_half_kw = any(k in clause for k in half_day_keywords) or bool(re.search(r'\b(AM|PM)\b', clause, re.IGNORECASE))
            is_half = is_half_kw or is_wfh
            
            if matched_type == "出勤確認":
                duration = "1天"
                comp = 0.0
            elif is_half:
                duration = "0.5天"
                comp = 0.5 if (matched_type == "黑假" or is_wfh) else matched_meta["google_comp"]
            else:
                duration = "1天"
                comp = matched_meta["google_comp"]

            clean_reason = clause
            # Case-insensitive removal of names
            for person in (KNOWN_NAMES + seg_names):
                clean_reason = re.sub(r'(?<![a-zA-Z0-9_])' + re.escape(person) + r'(?![a-zA-Z0-9_])', '', clean_reason, flags=re.IGNORECASE)
            if matched_kw:
                clean_reason = clean_reason.replace(matched_kw, '')
            clean_reason = clean_reason.replace("補卡", '')
            clean_reason = re.sub(r'((?<!補)申請|(?<![補申])(要請|請假|請)|上半天|下半天|一天|半天|0\.5天|\d+天|\d{1,2}/\d{1,2}|\b(?:0[1-9]|1[0-2])(?:[0-2][0-9]|3[01])\b)', '', clean_reason)
            clean_reason = re.sub(r'[,，\s]+', ' ', clean_reason).strip()
            clean_reason = re.sub(r'^[,\s，:\-–—~]+|[,\s，:\-–—~]+$', '', clean_reason).strip()
            if clean_reason in ['上', '下']:
                clean_reason = ''
            
            if matched_type == "出勤確認":
                full_ctx = f"{task_text} {clause}"
                if "下班" in full_ctx or "晚上" in full_ctx or "下午" in full_ctx or "退勤" in full_ctx:
                    if "忘了刷卡" in full_ctx or "忘刷卡" in full_ctx or "沒刷卡" in full_ctx:
                        final_reason = "下班忘了刷卡"
                    elif "未刷卡" in full_ctx:
                        final_reason = "下班未刷卡，補出勤確認"
                    elif clean_reason and re.search(r'[\u4e00-\u9fa5a-zA-Z]', clean_reason):
                        final_reason = clean_reason if ("下班" in clean_reason or "晚上" in clean_reason) else f"下班{clean_reason}"
                    else:
                        final_reason = "下班未刷卡，補出勤確認"
                elif "上班" in full_ctx or "早上" in full_ctx or "上午" in full_ctx:
                    if "忘了刷卡" in full_ctx or "忘刷卡" in full_ctx or "沒刷卡" in full_ctx:
                        final_reason = "上班忘了刷卡"
                    elif "未刷卡" in full_ctx:
                        final_reason = "早上未刷卡，補出勤確認"
                    elif clean_reason and re.search(r'[\u4e00-\u9fa5a-zA-Z]', clean_reason):
                        final_reason = clean_reason if ("上班" in clean_reason or "早上" in clean_reason) else f"早上{clean_reason}"
                    else:
                        final_reason = "早上未刷卡，補出勤確認"
                elif "忘了帶卡" in full_ctx or "忘帶卡" in full_ctx:
                    final_reason = "忘了帶卡，待補出勤確認"
                elif clean_reason and re.search(r'[\u4e00-\u9fa5a-zA-Z]', clean_reason):
                    final_reason = clean_reason
                else:
                    final_reason = "補出勤確認"
            elif is_wfh and (not clean_reason or clean_reason == "-"):
                final_reason = "WFH"
            elif not re.search(r'[\u4e00-\u9fa5a-zA-Z]', clean_reason):
                final_reason = "WFH" if is_wfh else "-"
            else:
                final_reason = f"WFH {clean_reason}" if is_wfh and "WFH" not in clean_reason else clean_reason

            for person in seg_names:
                for d in c_dates:
                    rec_key = (d, person.lower(), matched_type)
                    if rec_key not in seen_keys:
                        seen_keys.add(rec_key)
                        leave_records.append({
                            "date": d,
                            "name": person,
                            "leave_type": matched_type,
                            "duration": duration,
                            "google_comp_days": comp,
                            "reason": final_reason
                        })
    return leave_records



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


def validate_ot_rule(time_str, reason="", member_name=None, member_locations=None, date=None, location_histories=None):
    """
    Validates overtime start time rules:
    - Factory Overtime (Farglory, Lab, GDL, or member at factory location):
      Earliest allowed start = 19:00. Warn if starting before 19:00.
    - General Overtime (Non-factory):
      Earliest allowed start = 20:00. Warn if starting before 20:00
      (e.g. non-factory member accidentally writing 19:00).
    Returns: is_valid (bool), warning_msg (str)
    """
    if not time_str or '-' not in time_str:
        return True, ""

    start_part = time_str.split('-')[0].strip().replace(':', '')
    if len(start_part) == 4 and start_part.isdigit():
        start_h = int(start_part[:2])
        start_m = int(start_part[2:])
        start_fmt = f"{start_h:02d}:{start_m:02d}"
    elif ':' in time_str.split('-')[0]:
        parts = time_str.split('-')[0].strip().split(':')
        try:
            start_h = int(parts[0])
            start_m = int(parts[1])
            start_fmt = f"{start_h:02d}:{start_m:02d}"
        except Exception:
            return True, ""
    else:
        return True, ""

    start_total = start_h * 60 + start_m

    reason_upper = (reason or "").upper()
    factory_keywords = ['FARGLORY', 'LAB', 'GDL', '工廠', '實驗室']
    is_factory_reason = any(kw in reason_upper for kw in factory_keywords)

    factory_locations = ['台灣工廠', '台灣實驗室', '休士頓工廠', '美國LAB', '墨西哥GDL工廠']
    
    member_loc = ''
    if member_name and date and location_histories:
        from database import normalize_date_fmt
        d_clean = normalize_date_fmt(date)
        matching = []
        for h in location_histories:
            if h['name'].lower() == member_name.lower():
                h_start = normalize_date_fmt(h['start_date'])
                h_end = normalize_date_fmt(h.get('end_date'))
                if h_start <= d_clean and (not h_end or h_end >= d_clean):
                    matching.append(h)
        if matching:
            matching.sort(key=lambda x: (normalize_date_fmt(x['start_date']), x.get('id', 0)), reverse=True)
            member_loc = matching[0]['location']

    if not member_loc and member_name:
        member_loc = (member_locations or {}).get(member_name, '')

    is_factory_location = member_loc in factory_locations
    is_factory = is_factory_reason or is_factory_location

    if is_factory:
        # Factory: must NOT start before 19:00
        if start_total < 19 * 60:
            loc_label = f" ({member_loc})" if is_factory_location else ""
            return False, f"工廠加班{loc_label} 起始時間不得早於 19:00，此筆為 {start_fmt}"
    else:
        # Non-factory: must NOT start before 20:00
        if start_total < 20 * 60:
            return False, f"非工廠加班起始時間不得早於 20:00，此筆為 {start_fmt}（若屬特殊狀況請在編輯中勾選特殊狀況）"

    return True, ""


def parse_raw_text(text_block, default_year=2026, known_names=None, member_locations=None, location_histories=None):
    """
    Parses unstructured multi-line text input into structured overtime, leave records, and warnings.
    Returns: overtime_records, leave_records, warning_records
    """
    if known_names is None or location_histories is None:
        try:
            import database
            if known_names is None:
                db_members = database.get_all_members()
                known_names = [m['name'] for m in db_members]
            if not member_locations:
                member_locations = database.get_member_location_map()
            if location_histories is None:
                location_histories = database.get_all_member_location_histories()
        except Exception:
            if known_names is None:
                known_names = KNOWN_NAMES

    if not known_names:
        known_names = KNOWN_NAMES

    if member_locations is None:
        try:
            import database
            member_locations = database.get_member_location_map()
        except Exception:
            member_locations = {}

    overtime_records = []
    leave_records = []
    warning_records = []
    
    lines = text_block.strip().split('\n')
    current_date = f"{default_year}/07/01"
    last_line_records = []
    
    for line_idx, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line:
            continue
            
        # Check if line contains a date pattern (at start or inline like Daniel - **7/13 (Mon)** or 0731)
        date_match = re.search(r'(?:^|[\*\s\-\(])((\d{4}[/-])?(\d{1,2})[/-](\d{1,2})|\b(0[1-9]|1[0-2])([0-2][0-9]|3[01])\b)(?:\b|\s|\*|\))', line)
        if date_match:
            raw_date = date_match.group(1)
            start_date_match = re.match(r'^((\d{4}[/-])?\d{1,2}[/-]\d{1,2}|\b(0[1-9]|1[0-2])([0-2][0-9]|3[01])\b|\b\d{4}\b)', line)
            if start_date_match:
                rest_of_line = line[len(start_date_match.group(1)):].strip()
            else:
                rest_of_line = line

            if '/' in raw_date or '-' in raw_date:
                parts = re.split(r'[/-]', raw_date)
                if len(parts) == 3:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                else:
                    y, m, d = default_year, int(parts[0]), int(parts[1])
            elif len(raw_date) == 4 and raw_date.isdigit():
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
                if not date_match and last_line_records:
                    for rec in last_line_records:
                        rec["reason"] = (rec["reason"] + " " + rest_of_line).strip()
                else:
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
        current_line_records = []
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
            has_leave_kw = any(kw in task_text for kw in LEAVE_META.keys())
            
            # Check for time range in task_text or inherit line_prefix_time
            time_match = re.search(r'(\d{1,2}:?\d{2}\s*[-~—]\s*\d{1,2}:?\d{2})', task_text)
            raw_time_str = time_match.group(1) if time_match else line_prefix_time
            
            if has_leave_kw:
                parsed_l_recs = process_leave_task(task_text, seg_names, current_date, default_year)
                leave_records.extend(parsed_l_recs)
                current_line_records.extend(parsed_l_recs)
            elif raw_time_str:
                norm_time, hours = parse_time_range(raw_time_str)
                
                reason = task_text
                for n in seg_names:
                    reason = re.sub(r'\b' + re.escape(n) + r'\b', '', reason, flags=re.IGNORECASE)
                if time_match:
                    reason = reason.replace(time_match.group(1), '').strip()
                
                reason = re.sub(r'[\*\s-]*\d{1,2}[/-]\d{1,2}(\s*\([A-Za-z]+\))?[\*\s-]*', ' ', reason)
                reason = re.sub(r'^\s*:?\s*\d+(\.\d+)?\s*(hrs?|hr|小時|h)?\s*[,，]?', '', reason)
                reason = re.sub(r'^[,\s，:\-–—\*]+|[,\s，:\-–—\*]+$', '', reason).strip()
                if not reason:
                    reason = "加班處理公務"
                    
                note = get_weekday_note(current_date)
                
                for person in seg_names:
                    is_rule_ok, rule_warn_msg = validate_ot_rule(
                        norm_time or raw_time_str,
                        reason,
                        member_name=person,
                        member_locations=member_locations,
                        date=current_date,
                        location_histories=location_histories
                    )
                    if not is_rule_ok:
                        warning_records.append({
                            "line": line_idx,
                            "raw": raw_line,
                            "reason": f"{person}: {rule_warn_msg}"
                        })
                    
                    new_ot_rec = {
                        "date": current_date,
                        "name": person,
                        "time": norm_time or raw_time_str,
                        "hours": hours,
                        "reason": reason,
                        "note": note,
                        "eval_hours": hours,
                        "rule_warning": rule_warn_msg if not is_rule_ok else None
                    }
                    overtime_records.append(new_ot_rec)
                    current_line_records.append(new_ot_rec)

        if current_line_records:
            last_line_records = current_line_records

    return overtime_records, leave_records, warning_records
