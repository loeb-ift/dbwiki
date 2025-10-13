from flask import Blueprint, request, jsonify, session, Response, stream_with_context
import json
import sqlite3
from sqlalchemy import inspect, text
import logging
import re

from app.core.db_utils import get_user_db_connection
from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request
from app.core.helpers import load_prompt_template, get_dataset_tables, extract_serial_number_candidates, sample_column_data

# 配置日志记录器
logger = logging.getLogger(__name__)
training_bp = Blueprint('training', __name__, url_prefix='/api')

@training_bp.route('/training_data', methods=['GET'])
def get_training_data():
    user_id = session['username']
    logger.debug(f"get_training_data called with user_id: '{user_id}'")
    table_name = request.args.get('table_name')
    page = int(request.args.get('page', 1))
    page_size = 10
    offset = (page - 1) * page_size
    dataset_id = session.get('active_dataset')
    logger.debug(f"Request parameters - table_name: '{table_name}', dataset_id: '{dataset_id}', page: {page}")

    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400

    with get_user_db_connection(user_id) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT documentation_text FROM training_documentation WHERE table_name = ? AND dataset_id = ?", (table_name, dataset_id))
        doc_row = cursor.fetchone()
        documentation = doc_row['documentation_text'] if doc_row else ""
        
        cursor.execute("SELECT COUNT(*) FROM training_qa WHERE table_name = ? AND dataset_id = ?", (table_name, dataset_id))
        total_count = cursor.fetchone()[0]
        total_pages = (total_count + page_size - 1) // page_size

        cursor.execute("""
            SELECT id, question, sql_query as sql
            FROM training_qa
            WHERE table_name = ? AND dataset_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (table_name, dataset_id, page_size, offset))
        qa_pairs = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT documentation_text FROM training_documentation WHERE table_name = ? AND dataset_id = ?", ('__dataset_analysis__', dataset_id))
        analysis_row = cursor.fetchone()
        if analysis_row:
            dataset_analysis = analysis_row['documentation_text']
        else:
            dataset_analysis = """# 尚無資料庫結構分析

點擊下方的「資料庫自動分析」按鈕，讓 AI 為您生成一份關於此資料庫的結構、內容與查詢方式的綜合分析報告。

**這個功能會做什麼？**
1.  **整合上下文**：AI 會檢視您提供的所有 DDL、業務文件和 QA 問答範例。
2.  **生成分析報告**：基於這些資訊，AI 會生成一份「SQL 查詢思考過程分析表」，總結出資料庫的核心業務邏輯和查詢模式。
3.  **儲存與顯示**：報告生成後會顯示於此處，並儲存於資料庫中供日後參考。
"""

    response_data = {
        'documentation': documentation,
        'qa_pairs': qa_pairs,
        'dataset_analysis': dataset_analysis,
        'pagination': {
            'current_page': page,
            'total_pages': total_pages,
            'total_count': total_count
        }
    }
    return jsonify(response_data)

@training_bp.route('/save_documentation', methods=['POST'])
def save_documentation():
    user_id = session['username']
    logger.debug(f"save_documentation called with user_id: '{user_id}'")
    data = request.get_json()
    doc_content = data.get('documentation', '')
    table_name = data.get('table_name', 'global')
    dataset_id = session.get('active_dataset')
    logger.debug(f"Request data - table_name: '{table_name}', dataset_id: '{dataset_id}'")

    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400

    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            if doc_content.strip():
                cursor.execute(
                    "REPLACE INTO training_documentation (dataset_id, table_name, documentation_text) VALUES (?, ?, ?)",
                    (dataset_id, table_name, doc_content)
                )
                message = f"Documentation for table '{table_name}' saved."
            else:
                cursor.execute("DELETE FROM training_documentation WHERE dataset_id = ? AND table_name = ?", (dataset_id, table_name))
                message = f"Documentation for table '{table_name}' cleared."
            conn.commit()
        return jsonify({'status': 'success', 'message': message})
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@training_bp.route('/add_qa_question', methods=['POST'])
def add_qa_question():
    user_id = session['username']
    logger.debug(f"add_qa_question called with user_id: '{user_id}'")
    data = request.get_json()
    question = data.get('question')
    sql_query = data.get('sql')
    table_name = data.get('table_name', 'global')
    dataset_id = session.get('active_dataset')
    logger.debug(f"Request data - table_name: '{table_name}', dataset_id: '{dataset_id}', question: '{question[:30]}...'")

    if not all([question, sql_query, dataset_id]):
        return jsonify({'status': 'error', 'message': 'Question, SQL, and active dataset are required.'}), 400

    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO training_qa (question, sql_query, table_name, dataset_id) VALUES (?, ?, ?, ?)",
                (question, sql_query, table_name, dataset_id)
            )
            new_id = cursor.lastrowid
            conn.commit()
        return jsonify({'status': 'success', 'message': 'QA pair added successfully.', 'id': new_id})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'info', 'message': 'QA pair may already exist.'}), 200
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"Database error: {e}"}), 500

@training_bp.route('/train', methods=['POST'])
def train_model():
    user_id = session['username']
    logger.debug(f"train_model called with user_id: '{user_id}'")
    dataset_id = session.get('active_dataset')
    logger.debug(f"Request parameters - dataset_id: '{dataset_id}'")
    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400
    vn = get_vanna_instance(user_id)
    vn = configure_vanna_for_request(vn, user_id, dataset_id)

    def generate_progress():
        try:
            yield f"data: {json.dumps({'percentage': 0, 'message': '開始訓練...', 'log': 'Training process initiated.'})}\n\n"

            # 1. 从数据库加载所有训练数据
            ddl_list, doc_list, qa_list = [], [], []
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                # 获取 DDL
                cursor.execute("SELECT ddl FROM ddl_statements WHERE dataset_id = ?", (dataset_id,))
                ddl_list = [row[0] for row in cursor.fetchall()]
                # 获取文档
                cursor.execute("SELECT documentation_text FROM training_documentation WHERE dataset_id = ?", (dataset_id,))
                doc_list = [row[0] for row in cursor.fetchall() if row[0]]
                # 获取 QA 对
                cursor.execute("SELECT question, sql_query FROM training_qa WHERE dataset_id = ?", (dataset_id,))
                qa_list = [{'question': row[0], 'sql': row[1]} for row in cursor.fetchall()]
            
            yield f"data: {json.dumps({'percentage': 5, 'message': f'已加載 {len(ddl_list)} 條DDL, {len(doc_list)} 份文件, {len(qa_list)} 組問答。', 'log': 'Loaded training data from DB.'})}\n\n"

            total_steps = (1 if ddl_list else 0) + (1 if doc_list else 0) + (1 if qa_list else 0)
            if total_steps == 0:
                yield f"data: {json.dumps({'percentage': 100, 'message': '沒有找到可訓練的資料。', 'log': 'No training data found.'})}\n\n"
                return

            completed_steps = 0
            
            # 2. 训练DDL
            if ddl_list:
                full_ddl = "\n\n".join(ddl_list)
                vn.train(ddl=full_ddl)
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*90 + 5, 'message': 'DDL 訓練完成。', 'log': 'DDL training completed.'})}\n\n"
            
            # 3. 训练文档
            if doc_list:
                full_doc = "\n\n".join(doc_list)
                vn.train(documentation=full_doc)
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*90 + 5, 'message': '文件訓練完成。', 'log': 'Documentation training completed.'})}\n\n"

            # 4. 训练QA对
            if qa_list:
                total_pairs = len(qa_list)
                for i, pair in enumerate(qa_list):
                    if pair.get('question') and pair.get('sql'):
                        vn.train(question=pair['question'], sql=pair['sql'])
                    
                    # 仅在特定点更新进度，避免过于频繁
                    if i % 10 == 0 or i == total_pairs - 1:
                        base_progress = (completed_steps / total_steps) * 90 + 5
                        qa_progress = ((i + 1) / total_pairs) * (90 / total_steps)
                        current_percentage = base_progress + qa_progress
                        yield f"data: {json.dumps({'percentage': current_percentage, 'message': f'正在訓練問答配對... ({i+1}/{total_pairs})', 'log': f'Training QA pair {i+1}/{total_pairs}'})}\n\n"
                
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*90 + 5, 'message': f'問答配對 ({len(qa_list)} 組) 訓練完成。', 'log': f'QA pair training for {len(qa_list)} pairs completed.'})}\n\n"

            yield f"data: {json.dumps({'percentage': 100, 'message': '所有訓練步驟已完成。', 'log': 'All training steps completed.'})}\n\n"

        except Exception as e:
            logger.error(f"訓練過程中發生錯誤: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(stream_with_context(generate_progress()), mimetype='text/event-stream')

@training_bp.route('/generate_qa_from_sql', methods=['POST'])
def generate_qa_from_sql():
    user_id = session['username']
    logger.debug(f"generate_qa_from_sql called with user_id: '{user_id}'")
    if 'sql_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No sql_file part in the request'}), 400

    file = request.files['sql_file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No selected file'}), 400

    if not file or not file.filename.lower().endswith('.sql'):
        return jsonify({'status': 'error', 'message': 'Invalid file type. Please upload a .sql file.'}), 400

    sql_content = file.read().decode('utf-8')

    def stream_qa_generation(sql_content):
        dataset_id = session.get('active_dataset')
        if not dataset_id:
            yield f"data: {json.dumps({'status': 'error', 'message': '未选择活跃的数据集，请先选择一个数据集。'})}\n\n"
            return

        try:
            vn = get_vanna_instance(user_id)
            vn = configure_vanna_for_request(vn, user_id, dataset_id)
            queries = [q.strip() for q in sql_content.split(';') if q.strip()]
            total_queries = len(queries)
            yield f"data: {json.dumps({'status': 'starting', 'total': total_queries, 'message': '開始生成問答配對...'})}\n\n"
            from .prompts import get_prompt
            qa_system_prompt = get_prompt('qa_generation_system', user_id=session.get('username'))
            
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                for i, sql_query in enumerate(queries):
                    try:
                        question = vn.submit_prompt([
                            {'role': 'system', 'content': qa_system_prompt},
                            {'role': 'user', 'content': sql_query}
                        ])
                        
                        cursor.execute(
                            "INSERT INTO training_qa (question, sql_query, table_name, dataset_id) VALUES (?, ?, ?, ?)",
                            (question, sql_query, 'global', dataset_id)
                        )
                        new_id = cursor.lastrowid
                        conn.commit()
                        
                        percentage = int(((i + 1) / total_queries) * 100)
                        yield f"data: {json.dumps({'status': 'progress', 'percentage': percentage, 'message': f'已生成 {i + 1}/{total_queries} 個問答配對', 'qa_pair': {'id': new_id, 'question': question, 'sql': sql_query}})}\n\n"
                    except Exception as e:
                        yield f"data: {json.dumps({'status': 'warning', 'message': f'生成問題時發生錯誤: {str(e)} (SQL: {sql_query[:50]}...)'})}\n\n"
                
            yield f"data: {json.dumps({'status': 'completed', 'percentage': 100, 'message': '問答配對已全部生成並儲存！'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return Response(stream_with_context(stream_qa_generation(sql_content)), mimetype='text/event-stream')

@training_bp.route('/analyze_schema', methods=['POST'])
def analyze_schema():
    user_id = session.get('username')
    dataset_id = session.get('active_dataset')
    
    if not user_id or not dataset_id:
        # This error won't be nicely formatted for SSE, but it's a safeguard.
        return jsonify({'status': 'error', 'message': 'User not logged in or no active dataset selected.'}), 400

    def generate_analysis_stream():
        try:
            # 0. Clean up previous logs
            from app.core.helpers import _delete_all_ask_logs
            _delete_all_ask_logs(user_id)
            yield f"data: {json.dumps({'type': 'info', 'message': '開始新的分析任務...'})}\n\n"

            # 1. Setup
            vn = get_vanna_instance(user_id)
            vn = configure_vanna_for_request(vn, user_id, dataset_id)
            yield f"data: {json.dumps({'type': 'info', 'message': '分析環境初始化完成。'})}\n\n"

            # 2. Gather Context
            ds_ctx, ds_err = get_dataset_tables(user_id, dataset_id)
            ddl_list = ds_ctx.get('ddl_statements', []) if ds_ctx else []
            docs_list = []
            qa_examples = []
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT documentation_text FROM training_documentation WHERE dataset_id = ? AND table_name != '__dataset_analysis__'", (dataset_id,))
                docs_list = [row[0] for row in cursor.fetchall() if row and row[0]]
                cursor.execute("SELECT question, sql_query, table_name FROM training_qa WHERE dataset_id = ? ORDER BY created_at DESC LIMIT 100", (dataset_id,))
                qa_examples = cursor.fetchall()
            
            yield f"data: {json.dumps({'type': 'info', 'message': '已收集 DDL、文件和 QA 上下文。'})}\n\n"

            # 3. Main Structure Analysis
            documentation_prompt = load_prompt_template('documentation')
            safe_prompt = (documentation_prompt or "").replace('＠', '@')
            if ddl_list: safe_prompt += "\n\n===Tables (DDL)===\n" + "\n\n".join(ddl_list[:50])
            if docs_list: safe_prompt += "\n\n===Additional Context===\n" + "\n\n".join(docs_list[:20])
            if qa_examples:
                safe_prompt += "\n\n===Question-SQL Examples===\n"
                for q, s, _ in qa_examples[:30]: safe_prompt += f"\nQ: {q}\nSQL: {s}\n"
            
            question = "請根據上述上下文（DDL、文件、問答範例），生成一份全面的技術文件，詳細描述其架構、業務邏輯與查詢模式。請勿輸出 SQL 程式碼，只要文字分析。"
            message_log = [vn.system_message(safe_prompt), vn.user_message(question)]
            
            yield f"data: {json.dumps({'type': 'info', 'message': '正在呼叫 LLM 進行主要結構分析...'})}\n\n"
            response_text = vn.submit_prompt(message_log)
            final_analysis = str(response_text) if response_text is not None else ""
            yield f"data: {json.dumps({'type': 'analysis_result', 'content': final_analysis})}\n\n"

            # 4. Serial Number Analysis
            serial_number_analysis_result = ""
            yield f"data: {json.dumps({'type': 'info', 'message': '開始流水號/料號規則分析...'})}\n\n"
            try:
                candidate_columns = extract_serial_number_candidates(qa_examples)
                yield f"data: {json.dumps({'type': 'context', 'subtype': 'candidate_fields', 'content': list(candidate_columns.keys())})}\n\n"
                
                if candidate_columns:
                    db_path_row = None
                    with get_user_db_connection(user_id) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
                        db_path_row = cursor.fetchone()
                    
                    if db_path_row:
                        db_path = db_path_row[0]
                        serial_analysis_prompt_template = load_prompt_template('serial_number_analysis')
                        
                        # Analyze first candidate for simplicity
                        first_candidate_col = list(candidate_columns.keys())[0]
                        
                        # Find table name for the candidate column
                        table_name = 'global'
                        for q, s, tn in qa_examples:
                            if first_candidate_col in s:
                                table_name = tn if tn else 'global'
                                break
                        
                        yield f"data: {json.dumps({'type': 'info', 'message': f'正在為欄位 {first_candidate_col} 從資料表 {table_name} 中取樣...'})}\n\n"
                        sampled_data = sample_column_data(db_path, table_name, first_candidate_col)

                        if sampled_data:
                            yield f"data: {json.dumps({'type': 'context', 'subtype': 'sampled_data', 'content': sampled_data})}\n\n"
                            full_serial_prompt = f"{serial_analysis_prompt_template}\n\n【輸入範例】\n- DDL: {ddl_list[0] if ddl_list else 'N/A'}\n- 候選欄位: {first_candidate_col}\n- 欄位資料樣本:\n" + "\n".join(sampled_data)
                            
                            yield f"data: {json.dumps({'type': 'info', 'message': '正在呼叫 LLM 進行流水號規則分析...'})}\n\n"
                            serial_message_log = [vn.user_message(full_serial_prompt)]
                            serial_number_analysis_result = vn.submit_prompt(serial_message_log)
                        else:
                            serial_number_analysis_result = "取樣資料為空，無法進行分析。"
                else:
                    serial_number_analysis_result = "未在 QA 範例中找到潛在的流水號欄位。"

            except Exception as sn_e:
                logger.error(f"Error during serial number analysis: {sn_e}")
                serial_number_analysis_result = f"流水號分析時發生錯誤: {sn_e}"
            
            yield f"data: {json.dumps({'type': 'serial_number_analysis_result', 'content': serial_number_analysis_result})}\n\n"

            # 5. Save results to DB
            if final_analysis.strip() or serial_number_analysis_result.strip():
                with get_user_db_connection(user_id) as conn:
                    cursor = conn.cursor()
                    if final_analysis.strip():
                        cursor.execute("REPLACE INTO training_documentation (dataset_id, table_name, documentation_text) VALUES (?, ?, ?)", (dataset_id, '__dataset_analysis__', final_analysis))
                    if serial_number_analysis_result.strip():
                         cursor.execute("REPLACE INTO training_documentation (dataset_id, table_name, documentation_text) VALUES (?, ?, ?)", (dataset_id, '__serial_number_analysis__', serial_number_analysis_result))
                    conn.commit()
                yield f"data: {json.dumps({'type': 'info', 'message': '分析結果已儲存。'})}\n\n"

        except Exception as e:
            logger.exception("Error during schema analysis stream")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'end_of_stream'})}\n\n"

    return Response(stream_with_context(generate_analysis_stream()), mimetype='text/event-stream')

@training_bp.route('/generate_documentation_from_analysis', methods=['POST'])
def generate_documentation_from_analysis():
    user_id = session['username']
    logger.debug(f"generate_documentation_from_analysis called with user_id: '{user_id}'")
    dataset_id = session.get('active_dataset')
    logger.debug(f"Request parameters - dataset_id: '{dataset_id}'")

    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400

    try:
        with get_user_db_connection(user_id) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT documentation_text FROM training_documentation WHERE dataset_id = ? AND table_name = '__dataset_analysis__'", (dataset_id,))
            analysis_row = cursor.fetchone()
            analysis_documentation = analysis_row['documentation_text'] if analysis_row else ""

        if not analysis_documentation:
            return jsonify({'status': 'error', 'message': 'No analysis documentation found for the active dataset.'}), 400

        return jsonify({
            'status': 'success',
            'documentation': analysis_documentation
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@training_bp.route('/delete_all_qa', methods=['POST'])
def delete_all_qa():
    user_id = session['username']
    logger.debug(f"delete_all_qa called with user_id: '{user_id}'")
    dataset_id = session.get('active_dataset')
    logger.debug(f"Request parameters - dataset_id: '{dataset_id}'")

    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400

    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM training_qa WHERE dataset_id = ?", (dataset_id,))
            conn.commit()
        return jsonify({'status': 'success', 'message': '所有問答配對已刪除。'})
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500