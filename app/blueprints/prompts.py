from flask import Blueprint, request, jsonify, session
import sqlite3
import os
import json

from app.core.db_utils import get_user_db_connection
from app.core.helpers import load_prompt_template

prompts_bp = Blueprint('prompts', __name__, url_prefix='/api')

def get_prompt(prompt_type: str, user_id: str = None) -> str:
    # The user_id is now passed to load_prompt_template
    return load_prompt_template(prompt_type, user_id=user_id)

@prompts_bp.route('/prompts', methods=['GET'])
@prompts_bp.route('/get_prompts', methods=['GET'])
def get_prompts():
    user_id = session.get('username')
    if not user_id:
        return jsonify({'status': 'error', 'message': '用戶未登入'}), 401

    try:
        with get_user_db_connection(user_id) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT id, prompt_name, prompt_content, prompt_type, prompt_description, is_global, created_at FROM training_prompts ORDER BY id;"
            
            cursor.execute(query)
            prompts_list = [dict(row) for row in cursor.fetchall()]

            return jsonify({'status': 'success', 'prompts': prompts_list})
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500

@prompts_bp.route('/save_prompt', methods=['POST'])
def save_prompt():
    user_id_session = session.get('username')
    if not user_id_session:
        return jsonify({'status': 'error', 'message': '用戶未登入'}), 401
        
    data = request.get_json()
    
    prompt_id = data.get('id')
    prompt_name = data.get('prompt_name')
    prompt_content = data.get('prompt_content')
    prompt_description = data.get('prompt_description')
    
    if not prompt_name:
        return jsonify({'status': 'error', 'message': '缺少提示詞名稱。'}), 400
    
    try:
        with get_user_db_connection(user_id_session) as conn:
            cursor = conn.cursor()
            
            # Only allow updating name, content, and description.
            # prompt_type and is_global are considered fixed.
            cursor.execute(
                "UPDATE training_prompts SET prompt_name = ?, prompt_content = ?, prompt_description = ?, is_global = ? WHERE id = ?",
                (prompt_name, prompt_content, prompt_description, data.get('is_global', False), prompt_id)
            )
            
            if cursor.rowcount == 0:
                return jsonify({'status': 'error', 'message': '找不到對應的提示詞進行更新。'}), 404

            conn.commit()
            return jsonify({'status': 'success', 'message': '提示詞已更新。'})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': '操作失敗：提示詞名稱必須是唯一的。'}), 409
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500

@prompts_bp.route('/delete_prompt/<int:prompt_id>', methods=['DELETE'])
def delete_prompt(prompt_id):
    user_id = session.get('username')
    if not user_id:
        return jsonify({'status': 'error', 'message': '用戶未登入'}), 401

    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM training_prompts WHERE id = ? AND is_global = 0", (prompt_id,))
            
            if cursor.rowcount == 0:
                return jsonify({'status': 'error', 'message': '找不到可刪除的提示詞，或該提示詞為全域提示詞。'}), 404

            conn.commit()
            return jsonify({'status': 'success', 'message': '提示詞已刪除。'})
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500

def get_default_prompt_content(prompt_key: str) -> str:
    prompts_file_path = os.path.join(os.getcwd(), 'prompts', 'default_prompts.json')
    if not os.path.exists(prompts_file_path):
        return None
    with open(prompts_file_path, 'r', encoding='utf-8') as f:
        all_prompts = json.load(f)
    return all_prompts.get(prompt_key)

@prompts_bp.route('/reset_prompt_to_default/<string:prompt_name>', methods=['POST'])
def reset_prompt_to_default(prompt_name):
    user_id = session.get('username')
    if not user_id:
        return jsonify({'status': 'error', 'message': '用戶未登入'}), 401

    try:
        prompt_key = prompt_name.replace('_prompt', '') if prompt_name.endswith('_prompt') else prompt_name
        prompt_content = get_default_prompt_content(prompt_key)

        if prompt_content is None:
             return jsonify({'status': 'error', 'message': f"在預設檔案中找不到 '{prompt_key}' 的提示詞內容。"}), 404

        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE training_prompts SET prompt_content = ? WHERE prompt_name = ?",
                (prompt_content, prompt_name)
            )
            if cursor.rowcount == 0:
                return jsonify({'status': 'error', 'message': '在資料庫中找不到要重置的提示詞。'}), 404
            
            conn.commit()
            return jsonify({'status': 'success', 'message': '提示詞已重置為默認值。'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"重置過程中發生錯誤: {e}"}), 500
