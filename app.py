from flask import Flask, render_template, request, jsonify, Response
from datetime import datetime
import sqlite3
import os
import csv
import io
import database
import parser

app = Flask(__name__)

# Ensure DB is initialized on app startup
database.init_db()

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '1234')

def is_date_in_past_month(date_str):
    if not date_str:
        return False
    try:
        parts = date_str.strip().replace('-', '/').split('/')
        if len(parts) >= 2 and len(parts[0]) == 4:
            y, m = int(parts[0]), int(parts[1])
            now = datetime.now()
            if y < now.year:
                return True
            if y == now.year and m < now.month:
                return True
    except Exception:
        pass
    return False

def is_admin_authorized():
    req_pw = request.headers.get('X-Admin-Password') or (request.json or {}).get('admin_password', '')
    return req_pw == ADMIN_PASSWORD

@app.route('/api/verify_admin', methods=['POST'])
def verify_admin():
    data = request.json or {}
    password = data.get('password', '')
    if password == ADMIN_PASSWORD:
        return jsonify({"status": "success", "unlocked": True})
    return jsonify({"status": "error", "message": "管理員密碼錯誤！"}), 401

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/members', methods=['GET'])
def get_members():
    members = database.get_all_members()
    return jsonify(members)

@app.route('/api/members', methods=['POST'])
def add_member():
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403
    data = request.json or {}
    name = data.get('name', '')
    location = data.get('location', '台灣辦公室')
    google_comp_quota = float(data.get('google_comp_quota', 0.0))
    if not name.strip():
        return jsonify({"status": "error", "message": "姓名不能為空"}), 400
    rec_id = database.add_member(name, location, google_comp_quota)
    return jsonify({"status": "success", "id": rec_id})

@app.route('/api/members/<int:member_id>/location', methods=['PUT'])
def update_member_location(member_id):
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403
    data = request.json or {}
    location = data.get('location', '台灣辦公室')
    database.update_member_location(member_id, location)
    return jsonify({"status": "success"})

@app.route('/api/members/<int:member_id>/quota', methods=['PUT'])
def update_member_quota(member_id):
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403
    data = request.json or {}
    google_comp_quota = float(data.get('google_comp_quota', 0.0))
    database.update_member_quota(member_id, google_comp_quota)
    return jsonify({"status": "success"})

@app.route('/api/members/<int:member_id>', methods=['DELETE'])
def delete_member(member_id):
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403
    database.delete_member(member_id)
    return jsonify({"status": "success"})

@app.route('/api/parse', methods=['POST'])
def parse_logs():
    data = request.json or {}
    text_block = data.get('text', '')
    default_year = int(data.get('year', 2026))
    member_locs = database.get_member_location_map()
    loc_histories = database.get_all_member_location_histories()
    
    ot_records, lv_records, warn_records = parser.parse_raw_text(text_block, default_year, member_locations=member_locs, location_histories=loc_histories)
    return jsonify({
        "status": "success",
        "overtime_records": ot_records,
        "leave_records": lv_records,
        "warning_records": warn_records
    })

@app.route('/api/parse_csv', methods=['POST'])
def parse_csv():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "請上傳 CSV 檔案"}), 400
        
    file = request.files['file']
    default_year = int(request.form.get('year', 2026))
    member_locs = database.get_member_location_map()
    loc_histories = database.get_all_member_location_histories()
    
    try:
        content = file.read().decode('utf-8-sig', errors='ignore')
    except Exception as e:
        return jsonify({"status": "error", "message": f"檔案讀取失敗: {str(e)}"}), 400
        
    ot_records, lv_records, warn_records = parser.parse_raw_text(content, default_year, member_locations=member_locs, location_histories=loc_histories)
    return jsonify({
        "status": "success",
        "overtime_records": ot_records,
        "leave_records": lv_records,
        "warning_records": warn_records
    })

@app.route('/api/parse_image', methods=['POST'])
def parse_image():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "請上傳圖片檔案"}), 400
        
    file = request.files['file']
    default_year = int(request.form.get('year', 2026))
    member_locs = database.get_member_location_map()
    loc_histories = database.get_all_member_location_histories()
    
    # Save temporary file
    temp_path = os.path.join('/tmp', f'upload_{file.filename}')
    file.save(temp_path)
    
    extracted_text = ""
    # Try native macOS Vision OCR first if available
    if os.path.exists('./mac_ocr'):
        try:
            res = subprocess.run(['./mac_ocr', temp_path], capture_output=True, text=True, timeout=15)
            if res.returncode == 0 and res.stdout.strip():
                extracted_text = res.stdout.strip()
        except Exception:
            pass

    # Fallback to pytesseract if needed
    if not extracted_text:
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(temp_path)
            extracted_text = pytesseract.image_to_string(img, lang='chi_tra+eng')
        except Exception as e:
            if not extracted_text:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return jsonify({"status": "error", "message": "圖片辨識 (OCR) 引擎未就緒，建議使用文字或 CSV 貼上匯入"}), 500
                
    if os.path.exists(temp_path):
        os.remove(temp_path)
        
    ot_records, lv_records, warn_records = parser.parse_raw_text(extracted_text, default_year, member_locations=member_locs, location_histories=loc_histories)
    return jsonify({
        "status": "success",
        "extracted_text": extracted_text,
        "overtime_records": ot_records,
        "leave_records": lv_records,
        "warning_records": warn_records
    })

@app.route('/api/confirm_import', methods=['POST'])
def confirm_import():
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403
    data = request.json or {}
    ot_list = data.get('overtime_records', [])
    lv_list = data.get('leave_records', [])
    
    # Validate Taiwan weekend leave records
    for lv in lv_list:
        is_invalid, err_msg = database.check_taiwan_leave_weekend(lv.get('name'), lv.get('date'), lv.get('leave_type'))
        if is_invalid:
            return jsonify({
                "status": "error",
                "message": f"{err_msg} ({lv.get('name')} {lv.get('date')})"
            }), 400
    
    ins_ot, ins_lv = database.bulk_insert(ot_list, lv_list)
    skipped_ot = len(ot_list) - ins_ot
    skipped_lv = len(lv_list) - ins_lv
    
    msg_parts = [f"成功新增 {ins_ot} 筆加班與 {ins_lv} 筆請假"]
    if skipped_ot > 0 or skipped_lv > 0:
        msg_parts.append(f"(自動去重忽略 {skipped_ot + skipped_lv} 筆已存在的重複紀錄)")
        
    return jsonify({"status": "success", "message": " ".join(msg_parts)})

@app.route('/api/overtime', methods=['GET'])
def get_overtime():
    month = request.args.get('month')
    name = request.args.get('name')
    ot_type = request.args.get('ot_type')
    search = request.args.get('search')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    records = database.get_overtime_records(month=month, name=name, search=search, ot_type=ot_type, start_date=start_date, end_date=end_date)
    for r in records:
        r['location'] = database.get_member_location_at_date(r['name'], r['date'])
    return jsonify(records)

@app.route('/api/members/locations', methods=['GET'])
def get_member_locations_history():
    name = request.args.get('name')
    histories = database.get_all_member_location_histories(name=name)
    return jsonify(histories)

@app.route('/api/members/locations', methods=['POST'])
def add_member_location_history_endpoint():
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403
    data = request.json or {}
    name = data.get('name')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    location = data.get('location')
    if not name or not start_date or not location:
        return jsonify({"status": "error", "message": "請填寫姓名、開始日期與地點！"}), 400
    hid = database.add_member_location_history(name, start_date, end_date, location)
    return jsonify({"status": "success", "id": hid})

@app.route('/api/members/locations/<int:hid>', methods=['DELETE'])
def delete_member_location_history_endpoint(hid):
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403
    database.delete_member_location_history(hid)
    return jsonify({"status": "success"})

@app.route('/api/members/locations/<int:hid>', methods=['PUT'])
def update_member_location_history_endpoint(hid):
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403
    data = request.json or {}
    name = data.get('name')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    location = data.get('location')
    if not name or not start_date or not location:
        return jsonify({"status": "error", "message": "請填寫姓名、開始日期與地點！"}), 400
    database.update_member_location_history(hid, name, start_date, end_date, location)
    return jsonify({"status": "success"})

@app.route('/api/overtime', methods=['POST'])
def add_overtime():
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403
    data = request.json or {}
    date = data.get('date')
    name = data.get('name')
    time_str = data.get('time', '')
    hours = float(data.get('hours', 0.0))
    reason = data.get('reason', '')
    note = data.get('note', '')
    eval_hours = float(data.get('eval_hours', hours))
    
    rec_id = database.add_overtime_record(date, name, time_str, hours, reason, note, eval_hours)
    return jsonify({"status": "success", "id": rec_id})

@app.route('/api/overtime/<int:rec_id>', methods=['GET'])
def get_overtime_by_id(rec_id):
    with database.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM overtime_records WHERE id=?', (rec_id,))
        row = cursor.fetchone()
    if not row:
        return jsonify({"status": "error", "message": "找不到紀錄"}), 404
    return jsonify(dict(row))

@app.route('/api/overtime/<int:rec_id>', methods=['PUT'])
def update_overtime(rec_id):
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403

    data = request.json or {}
    date = data.get('date')
    name = data.get('name')
    time_str = data.get('time', '')
    hours = float(data.get('hours', 0.0))
    reason = data.get('reason', '')
    note = data.get('note', '')
    eval_hours = float(data.get('eval_hours', hours))
    is_special = int(bool(data.get('is_special', False)))
    special_reason = data.get('special_reason', '')
    
    database.update_overtime_record(rec_id, date, name, time_str, hours, reason, note, eval_hours,
                                    is_special=is_special, special_reason=special_reason)
    return jsonify({"status": "success"})

@app.route('/api/overtime/<int:rec_id>', methods=['DELETE'])
def delete_overtime(rec_id):
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403

    database.delete_overtime_record(rec_id)
    return jsonify({"status": "success"})

@app.route('/api/leaves', methods=['GET'])
def get_leaves():
    month = request.args.get('month')
    name = request.args.get('name')
    leave_types_str = request.args.get('leave_types')
    search = request.args.get('search')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    leave_types = leave_types_str.split(',') if leave_types_str else None
    records = database.get_leave_records(month=month, name=name, leave_types=leave_types, search=search, start_date=start_date, end_date=end_date)
    return jsonify(records)

@app.route('/api/leaves/<int:rec_id>', methods=['GET'])
def get_leave_by_id(rec_id):
    with database.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM leave_records WHERE id=?', (rec_id,))
        row = cursor.fetchone()
    if not row:
        return jsonify({"status": "error", "message": "找不到紀錄"}), 404
    return jsonify(dict(row))

@app.route('/api/leaves', methods=['POST'])
def add_leave():
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403
    data = request.json or {}
    date = data.get('date')
    name = data.get('name')
    leave_type = data.get('leave_type')
    duration = data.get('duration', '1天')
    google_comp_days = float(data.get('google_comp_days', 0.0))
    reason = data.get('reason', '')
    is_comp_deducted = int(data.get('is_comp_deducted', 1))
    
    is_invalid, err_msg = database.check_taiwan_leave_weekend(name, date, leave_type)
    if is_invalid:
        return jsonify({"status": "error", "message": err_msg}), 400
    
    rec_id = database.add_leave_record(date, name, leave_type, duration, google_comp_days, reason, is_comp_deducted)
    return jsonify({"status": "success", "id": rec_id})

@app.route('/api/leaves/<int:rec_id>', methods=['PUT'])
def update_leave(rec_id):
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403

    data = request.json or {}
    date = data.get('date')
    name = data.get('name')
    leave_type = data.get('leave_type')
    duration = data.get('duration', '1天')
    google_comp_days = float(data.get('google_comp_days', 0.0))
    reason = data.get('reason', '')
    is_comp_deducted = int(data.get('is_comp_deducted', 1))
    
    is_invalid, err_msg = database.check_taiwan_leave_weekend(name, date, leave_type)
    if is_invalid:
        return jsonify({"status": "error", "message": err_msg}), 400
    
    database.update_leave_record(rec_id, date, name, leave_type, duration, google_comp_days, reason, is_comp_deducted)
    return jsonify({"status": "success"})

@app.route('/api/leaves/<int:rec_id>/deducted_status', methods=['PUT'])
def update_leave_deducted_status(rec_id):
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403

    data = request.json or {}
    is_comp_deducted = int(data.get('is_comp_deducted', 1))
    database.update_leave_deducted_status(rec_id, is_comp_deducted)
    return jsonify({"status": "success"})

@app.route('/api/leaves/<int:rec_id>', methods=['DELETE'])
def delete_leave(rec_id):
    if not is_admin_authorized():
        return jsonify({"status": "error", "message": "需要管理員權限才能執行此操作！"}), 403

    database.delete_leave_record(rec_id)
    return jsonify({"status": "success"})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    month = request.args.get('month')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    stats = database.get_monthly_stats(month=month, start_date=start_date, end_date=end_date)
    return jsonify(stats)

@app.route('/api/export', methods=['GET'])
def export_csv():
    month = request.args.get('month')
    ot_records = database.get_overtime_records(month=month)
    lv_records = database.get_leave_records(month=month)
    stats_data = database.get_monthly_stats(month=month)
    stats_list = stats_data.get('stats', [])
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    
    safe_month = (month or '全部月份').replace('/', '_')
    
    # 1. 團隊統計摘要
    writer.writerow([f'【團隊加班與請假統計摘要 - {month or "全部月份"}】'])
    writer.writerow(['姓名', '駐點地點', '加班總數(筆)', '平日加班(hr)', '假日加班(hr)', '加班時數小計(hr)', '預估可獲補休(天)', '請假總數(筆)', '請假假別組成明細', 'Google補休總額(天)', '已扣補休(天)', '剩餘補休(天)'])
    for s in stats_list:
        loc_str = s.get('location') or '-'
        ot_cnt = s.get('ot_count', 0)
        wd_ot = s.get('weekday_ot_hours', 0.0)
        we_ot = s.get('weekend_ot_hours', 0.0)
        tot_ot = s.get('overtime_hours', 0.0)
        est_days = s.get('est_comp_days', 0.0)
        lv_cnt = s.get('leave_count', 0)
        lb_list = [b['label'] for b in s.get('leave_breakdown', [])]
        lb_str = ' | '.join(lb_list) if lb_list else '-'
        quota = s.get('google_comp_quota', 0.0)
        used = s.get('google_comp_used_total', 0.0)
        rem = s.get('google_comp_remaining', 0.0)
        writer.writerow([s.get('name'), loc_str, ot_cnt, wd_ot, we_ot, tot_ot, est_days, lv_cnt, lb_str, quota, used, rem])
    
    writer.writerow([])
    
    # 2. 加班明細
    writer.writerow([f'【加班紀錄明細 - {month or "全部月份"}】 (共 {len(ot_records)} 筆)'])
    writer.writerow(['日期', '加班類型', '姓名', '加班地點', '時間區間', '加班時數(hr)', '事由', '備註', '評估時數(hr)'])
    for r in ot_records:
        loc = database.get_member_location_at_date(r['name'], r['date'])
        note = r.get('note') or ('假日加班' if r.get('note') == '假日加班' or r.get('is_special') else '平日加班')
        writer.writerow([r.get('date'), note, r.get('name'), loc, r.get('time'), r.get('hours'), r.get('reason'), r.get('special_reason') or r.get('note') or '', r.get('eval_hours')])
        
    writer.writerow([])
    
    # 3. 請假明細
    writer.writerow([f'【請假紀錄明細 - {month or "全部月份"}】 (共 {len(lv_records)} 筆)'])
    writer.writerow(['日期', '姓名', '假別', '時長', 'Google補休(天)', '事由', '補休扣除狀態'])
    check_counts = {}
    sorted_leaves = sorted(lv_records, key=lambda x: (x.get('date', ''), x.get('id', 0)))
    for r in sorted_leaves:
        lt = r.get('leave_type', '')
        if lt == '出勤確認':
            n = (r.get('name') or '').strip()
            check_counts[n] = check_counts.get(n, 0) + 1
            seq = check_counts[n]
            if seq > 4:
                lt_display = f"出勤確認 (第{seq}次-超額)"
            else:
                lt_display = f"出勤確認 ({seq}/4)"
        else:
            lt_display = lt
            
        is_ded = r.get('is_comp_deducted')
        if r.get('leave_type') in ['黑假', 'WFH']:
            ded_str = '已扣補休' if is_ded == 1 else '還沒扣'
        else:
            ded_str = '-'
            
        writer.writerow([r.get('date'), r.get('name'), lt_display, r.get('duration'), r.get('google_comp_days', 0.0), r.get('reason', ''), ded_str])
        
    response = Response(output.getvalue(), mimetype='text/csv; charset=utf-8')
    filename = f"Attendance_Report_{safe_month}.csv"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{filename}'
    return response

@app.route('/api/asw_export', methods=['GET'])
def get_asw_export():
    month = request.args.get('month')
    title, rows, total_hours = database.get_asw_export_data(month=month)
    return jsonify({
        "status": "success",
        "title": title,
        "rows": rows,
        "total_eval_hours": total_hours
    })

@app.route('/api/asw_export_csv', methods=['GET'])
def export_asw_csv():
    month = request.args.get('month')
    title, rows, total_hours = database.get_asw_export_data(month=month)
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter='\t')
    
    writer.writerow(['Date', 'Name', 'Time', 'Hours', 'Reason', '備註', '時數'])
    for r in rows:
        if r.get('is_empty'):
            writer.writerow([])
        else:
            writer.writerow([r['date'], r['name'], r['time'], r['hours'], r['reason'], r['note'], r['eval_hours']])
    
    response = Response(output.getvalue(), mimetype='text/tab-separated-values')
    filename = f"{title}.tsv"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print("Starting Overwork Table Server...")
    print(f"Please open browser at: http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
