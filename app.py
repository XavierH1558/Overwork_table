from flask import Flask, render_template, request, jsonify, Response
import sqlite3
import os
import csv
import io
import database
import parser

app = Flask(__name__)

# Ensure DB is initialized on app startup
database.init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/parse', methods=['POST'])
def parse_logs():
    data = request.json or {}
    text_block = data.get('text', '')
    default_year = int(data.get('year', 2025))
    
    ot_records, lv_records = parser.parse_raw_text(text_block, default_year)
    return jsonify({
        "status": "success",
        "overtime_records": ot_records,
        "leave_records": lv_records
    })

@app.route('/api/confirm_import', methods=['POST'])
def confirm_import():
    data = request.json or {}
    ot_list = data.get('overtime_records', [])
    lv_list = data.get('leave_records', [])
    
    database.bulk_insert(ot_list, lv_list)
    return jsonify({"status": "success", "message": f"成功匯入 {len(ot_list)} 筆加班與 {len(lv_list)} 筆請假紀錄"})

@app.route('/api/overtime', methods=['GET'])
def get_overtime():
    month = request.args.get('month')
    name = request.args.get('name')
    search = request.args.get('search')
    records = database.get_overtime_records(month=month, name=name, search=search)
    return jsonify(records)

@app.route('/api/overtime', methods=['POST'])
def add_overtime():
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

@app.route('/api/overtime/<int:rec_id>', methods=['PUT'])
def update_overtime(rec_id):
    data = request.json or {}
    date = data.get('date')
    name = data.get('name')
    time_str = data.get('time', '')
    hours = float(data.get('hours', 0.0))
    reason = data.get('reason', '')
    note = data.get('note', '')
    eval_hours = float(data.get('eval_hours', hours))
    
    database.update_overtime_record(rec_id, date, name, time_str, hours, reason, note, eval_hours)
    return jsonify({"status": "success"})

@app.route('/api/overtime/<int:rec_id>', methods=['DELETE'])
def delete_overtime(rec_id):
    database.delete_overtime_record(rec_id)
    return jsonify({"status": "success"})

@app.route('/api/leaves', methods=['GET'])
def get_leaves():
    month = request.args.get('month')
    name = request.args.get('name')
    leave_types_str = request.args.get('leave_types')
    search = request.args.get('search')
    
    leave_types = leave_types_str.split(',') if leave_types_str else None
    records = database.get_leave_records(month=month, name=name, leave_types=leave_types, search=search)
    return jsonify(records)

@app.route('/api/leaves', methods=['POST'])
def add_leave():
    data = request.json or {}
    date = data.get('date')
    name = data.get('name')
    leave_type = data.get('leave_type')
    duration = data.get('duration', '1天')
    google_comp_days = float(data.get('google_comp_days', 0.0))
    reason = data.get('reason', '')
    
    rec_id = database.add_leave_record(date, name, leave_type, duration, google_comp_days, reason)
    return jsonify({"status": "success", "id": rec_id})

@app.route('/api/leaves/<int:rec_id>', methods=['PUT'])
def update_leave(rec_id):
    data = request.json or {}
    date = data.get('date')
    name = data.get('name')
    leave_type = data.get('leave_type')
    duration = data.get('duration', '1天')
    google_comp_days = float(data.get('google_comp_days', 0.0))
    reason = data.get('reason', '')
    
    database.update_leave_record(rec_id, date, name, leave_type, duration, google_comp_days, reason)
    return jsonify({"status": "success"})

@app.route('/api/leaves/<int:rec_id>', methods=['DELETE'])
def delete_leave(rec_id):
    database.delete_leave_record(rec_id)
    return jsonify({"status": "success"})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    month = request.args.get('month')
    stats = database.get_monthly_stats(month=month)
    return jsonify(stats)

@app.route('/api/export', methods=['GET'])
def export_csv():
    month = request.args.get('month')
    ot_records = database.get_overtime_records(month=month)
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    
    writer.writerow(['Date', 'Name', 'Time', 'Hours', 'Reason', '備註', '評估時數'])
    for r in ot_records:
        writer.writerow([r['date'], r['name'], r['time'], r['hours'], r['reason'], r['note'], r['eval_hours']])
        
    response = Response(output.getvalue(), mimetype='text/csv')
    filename = f"Overtime_Report_{month or 'All'}.csv"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response

if __name__ == '__main__':
    print("Starting Overwork Table Server...")
    print("Please open browser at: http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
