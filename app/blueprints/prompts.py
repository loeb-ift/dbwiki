from flask import Blueprint, request, jsonify, session
import sqlite3

from app.core.db_utils import get_user_db_connection, get_db_connection
from app.core.helpers import load_prompt_template

prompts_bp = Blueprint('prompts', __name__, url_prefix='/api')

def get_prompt(prompt_type: str, user_id: str) -> str:
    """
    Wrapper function that calls the refactored load_prompt_template from helpers.
    This ensures all prompt loading logic is centralized.
    """
    # The user_id is handled by the session within the new load_prompt_template
    return load_prompt_template(prompt_type)


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
            
            # 聯合查詢：首先獲取用戶的私有提示詞，然後獲取所有全局提示詞
            # 使用 UNION 來避免重複（如果用戶修改了全局提示詞，可能會在自己的庫裡有一份）
            # 這裡我們假設 is_global=0 為用戶私有, is_global=1 為全局
            # 並且我們需要確保全局提示詞是從主數據庫或一個可靠的地方獲取
            # 為了簡化，我們假設用戶數據庫包含了用戶可見的所有提示詞
            # 包括他們自己創建的和系統全局的
            query = """
            SELECT id, prompt_name, prompt_content, prompt_type, is_global, created_at
            FROM training_prompts
            ORDER BY is_global DESC, created_at DESC;
            """
            
            cursor.execute(query)
            prompts_list = [dict(row) for row in cursor.fetchall()]

            prompt_descriptions = {
                'sql_generation': '用於生成 SQL 的核心提示詞，指導 LLM 如何根據 DDL、文件和範例來建構查詢。',
                'followup_question_generation': '用於在一次查詢成功後，生成相關的、可供使用者點擊的後續問題。',
                'summary_generation': '用於在查詢返回結果後，生成對數據的自然語言摘要。',
                'question_rewriting': '用於理解對話上下文，將連續的多個問題合併為一個可以被單一 SQL 回答的、更完整的問題。',
                'question_generation_from_sql': '一個通用的「反向」提示詞，用於從一個 SQL 查詢推斷出它可能在回答的業務問題。',
                'plotly_generation': '指導 LLM 如何根據查詢結果 DataFrame 生成 Python Plotly 程式碼以進行視覺化。',
                'ask_analysis_prompt': '一個複雜的提示詞，用於生成詳細的「SQL 查詢思考過程分析表」，幫助理解 LLM 的決策過程。',
                'qa_generation': '一個專家級的提示詞，包含大量 ERP 範例，專門用於從 SQL 批次生成高品質的、符合業務場景的訓練問答對。',
                'documentation_prompt': '指導 LLM 作為一名架構師，從資料庫結構反向工程，生成系統的技術文檔。'
            }

            for prompt in prompts_list:
                prompt_type = prompt.get('prompt_type')
                if prompt_type:
                    prompt['description'] = prompt_descriptions.get(prompt_type, '這是一個自定義或未分類的提示詞。')

            # Filter out unused prompts before sending to frontend
            unused_prompts = ['question_generation_from_sql']
            filtered_prompts = [p for p in prompts_list if p.get('prompt_type') not in unused_prompts]

            from flask import current_app
            current_app.logger.debug(f"Returning prompts to frontend: {filtered_prompts}")
            return jsonify({'status': 'success', 'prompts': filtered_prompts})
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500

@prompts_bp.route('/save_prompt', methods=['POST'])
def save_prompt():
    user_id_session = session['username']
    data = request.get_json()
    
    prompt_name = data.get('prompt_name')
    prompt_content = data.get('prompt_content')
    prompt_type = data.get('prompt_type')
    is_global = 1 if data.get('is_global', False) else 0
    prompt_id = data.get('id')
    
    # For non-global prompts, the user_id is the current user. For global, it's NULL.
    user_id_to_save = user_id_session if is_global == 0 else None

    if not prompt_name or not prompt_content:
        return jsonify({'status': 'error', 'message': '提示詞名稱和內容是必需的。'}), 400
    
    try:
        # All prompts are saved in the user's database space for simplicity
        with get_user_db_connection(user_id_session) as conn:
            cursor = conn.cursor()
            
            if prompt_id:
                # Update existing prompt
                cursor.execute(
                    "UPDATE training_prompts SET prompt_name = ?, prompt_content = ?, prompt_type = ?, is_global = ? WHERE id = ?",
                    (prompt_name, prompt_content, prompt_type, is_global, prompt_id)
                )
                message = '提示詞已更新。'
            else:
                # Insert new prompt
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
        # We need to find the prompt_type associated with the prompt_name
        # This is a bit tricky as the direct mapping is in db_utils.
        # For now, we assume a 1-to-1 mapping where prompt_name is like 'sql_generation_prompt'
        # and we need 'sql_generation'.
        # A better long-term solution might be to pass prompt_type here.
        prompt_type = prompt_name.replace('_prompt', '').replace('_system', '')
        prompt_content = load_prompt_template(prompt_type)
        
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
                    'documentation_prompt': '用於生成數據庫文檔的提示詞',
                    'plotly_generation_prompt': '用於生成 Plotly 圖表的提示詞',
                    'sql_generation': '用於生成 SQL 的提示詞',
                    'followup_question_generation': '用於生成後續問題的提示詞',
                    'summary_generation': '用於生成摘要的提示詞',
                    'question_rewriting': '用於重寫問題的提示詞',
                    'question_generation_from_sql': '用於從 SQL 生成問題的提示詞'
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

