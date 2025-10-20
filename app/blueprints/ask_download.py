from flask import Blueprint, session, jsonify, send_file
import io
import csv

# 下載 CSV 的 Blueprint
ask_download_bp = Blueprint('ask_download', __name__, url_prefix='/api/ask')

# 這個結果緩存將由 ask.py 寫入，本模組讀取
# 由於是在不同檔案，我們導入 ask.py 中的變數
try:
    from app.blueprints.ask import _last_result_cache
except Exception:
    _last_result_cache = {}

@ask_download_bp.route('/download_csv', methods=['GET'])
def download_csv():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'User not authenticated. Please login.'}), 401
    user_id = session['username']
    result = _last_result_cache.get(user_id)
    if not result or not result.get('columns'):
        return jsonify({'status': 'error', 'message': '尚無可下載的查詢結果，請先執行一次成功的查詢。'}), 400

    # 建立 CSV 內容
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(result['columns'])
    for row in result.get('data', []):
        writer.writerow(row)
    csv_bytes = io.BytesIO(output.getvalue().encode('utf-8-sig'))

    return send_file(
        csv_bytes,
        mimetype='text/csv',
        as_attachment=True,
        download_name='query_result.csv'
    )
