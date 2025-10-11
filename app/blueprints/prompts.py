from flask import Blueprint, request, jsonify, session
import sqlite3

from app.core.db_utils import get_user_db_connection
from app.core.helpers import load_prompt_template

prompts_bp = Blueprint('prompts', __name__, url_prefix='/api')

@prompts_bp.route('/prompts', methods=['GET'])
@prompts_bp.route('/get_prompts', methods=['GET'])
def get_prompts():
    user_id = session['username']
    try:
        with get_user_db_connection(user_id) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, prompt_name, prompt_content, prompt_type, is_global, created_at FROM training_prompts ORDER BY created_at DESC")
            prompts = [dict(row) for row in cursor.fetchall()]
            return jsonify({'status': 'success', 'prompts': prompts})
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500

@prompts_bp.route('/save_prompt', methods=['POST'])
def save_prompt():
    user_id = session['username']
    data = request.get_json()
    
    prompt_name = data.get('prompt_name')
    prompt_content = data.get('prompt_content')
    prompt_type = data.get('prompt_type')
    is_global = 1 if data.get('is_global', False) else 0
    prompt_id = data.get('id')
    
    if not prompt_name or not prompt_content:
        return jsonify({'status': 'error', 'message': '提示詞名稱和內容是必需的。'}), 400
    
    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            if prompt_id:
                cursor.execute(
                    "UPDATE training_prompts SET prompt_name = ?, prompt_content = ?, prompt_type = ?, is_global = ? WHERE id = ?",
                    (prompt_name, prompt_content, prompt_type, is_global, prompt_id)
                )
                message = '提示詞已更新。'
            else:
                cursor.execute(
                    "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, is_global) VALUES (?, ?, ?, ?)",
                    (prompt_name, prompt_content, prompt_type, is_global)
                )
                message = '提示詞已添加。'
            
            conn.commit()
            return jsonify({'status': 'success', 'message': message})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': '提示詞名稱已存在，請使用不同的名稱。'}), 400
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500

@prompts_bp.route('/delete_prompt/<int:prompt_id>', methods=['DELETE'])
def delete_prompt(prompt_id):
    user_id = session['username']
    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT is_global FROM training_prompts WHERE id = ?", (prompt_id,))
            result = cursor.fetchone()
            
            if not result:
                return jsonify({'status': 'error', 'message': '提示詞不存在。'}), 404
            
            if result[0] == 1:
                return jsonify({'status': 'error', 'message': '無法刪除全局提示詞。'}), 403
            
            cursor.execute("DELETE FROM training_prompts WHERE id = ?", (prompt_id,))
            conn.commit()
            
            return jsonify({'status': 'success', 'message': '提示詞已刪除。'})
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500

@prompts_bp.route('/reset_prompt_to_default/<string:prompt_name>', methods=['POST'])
def reset_prompt_to_default(prompt_name):
    user_id = session['username']
    try:
        prompt_content = load_prompt_template(f"{prompt_name}.txt")
        
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM training_prompts WHERE prompt_name = ?", (prompt_name,))
            result = cursor.fetchone()
            
            if result:
                cursor.execute(
                    "UPDATE training_prompts SET prompt_content = ?, is_global = 1 WHERE id = ?",
                    (prompt_content, result[0])
                )
            else:
                prompt_type_map = {
                    'ask_analysis_prompt': '用於分析用戶問題和生成SQL的提示詞',
                    'qa_generation_system_prompt': '用於從SQL生成問答配對的提示詞',
                    'documentation_prompt': '用於生成數據庫文檔的提示詞'
                }
                prompt_type = prompt_type_map.get(prompt_name, '默認提示詞')
                cursor.execute(
                    "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, is_global) VALUES (?, ?, ?, ?)",
                    (prompt_name, prompt_content, prompt_type, 1)
                )
            
            conn.commit()
            return jsonify({'status': 'success', 'message': '提示詞已重置為默認值。'})
    except FileNotFoundError:
        return jsonify({'status': 'error', 'message': '找不到默認提示詞文件。'}), 404
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500