from flask import Blueprint, request, jsonify, session, Response, stream_with_context
import json
import sqlite3
from sqlalchemy import inspect, text
import logging
import re

from app.core.db_utils import get_user_db_connection
from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request
from app.core.helpers import load_prompt_template, get_dataset_tables

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
            ddl = request.form.get('ddl')
            documentation = request.form.get('doc', '')
            qa_pairs_json = request.form.get('qa_pairs')
            qa_pairs = json.loads(qa_pairs_json) if qa_pairs_json else []

            yield f"data: {json.dumps({'percentage': 0, 'message': '開始訓練...', 'log': 'Training process initiated.'})}\n\n"
            
            total_steps = (1 if ddl else 0) + (1 if documentation else 0) + (1 if qa_pairs else 0)
            completed_steps = 0

            if ddl:
                vn.train(ddl=ddl)
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*100, 'message': 'DDL 訓練完成。', 'log': 'DDL training completed.'})}\n\n"
            
            if documentation:
                vn.train(documentation=documentation)
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*100, 'message': '文件訓練完成。', 'log': 'Documentation training completed.'})}\n\n"

            if qa_pairs:
                total_pairs = len(qa_pairs)
                for i, pair in enumerate(qa_pairs):
                    if pair.get('question') and pair.get('sql'):
                        vn.train(question=pair['question'], sql=pair['sql'])
                    if i % 5 == 0 or i == total_pairs - 1:
                        current_step = (completed_steps + (i + 1)/total_pairs) / total_steps
                        yield f"data: {json.dumps({'percentage': current_step*100, 'message': f'正在訓練問答配對... ({i+1}/{total_pairs})', 'log': f'Training QA pair {i+1}/{total_pairs}'})}\n\n"
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*100, 'message': f'問答配對 ({len(qa_pairs)} 組) 訓練完成。', 'log': f'QA pair training for {len(qa_pairs)} pairs completed.'})}\n\n"

            yield f"data: {json.dumps({'percentage': 100, 'message': '所有訓練步驟已完成。', 'log': 'All training steps completed.'})}\n\n"

        except Exception as e:
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
    logger.debug(f"analyze_schema called with user_id: '{user_id}', dataset_id: '{dataset_id}'")

    if not user_id or not dataset_id:
        return jsonify({'status': 'error', 'message': 'User not logged in or no active dataset selected.'}), 400

    # If client requests non-streaming JSON response
    payload = request.get_json(silent=True) or {}
    if payload.get('streaming') is False:
        try:
            vn = get_vanna_instance(user_id)
            vn = configure_vanna_for_request(vn, user_id, dataset_id)

            # 收集資料集上下文：DDL、文件、QA
            ds_ctx, ds_err = get_dataset_tables(user_id, dataset_id)
            ddl_list = ds_ctx.get('ddl_statements', []) if ds_ctx else []
            # 收集除 __dataset_analysis__ 的所有 documentation
            docs_list = []
            qa_examples = []
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT documentation_text FROM training_documentation WHERE dataset_id = ? AND table_name != '__dataset_analysis__'", (dataset_id,))
                docs_list = [row[0] for row in cursor.fetchall() if row and row[0]]
                cursor.execute("SELECT question, sql_query FROM training_qa WHERE dataset_id = ? ORDER BY created_at DESC LIMIT 50", (dataset_id,))
                qa_examples = cursor.fetchall()
            # 準備系統提示詞：將 DDL/文件/QA 注入
            documentation_prompt = load_prompt_template('documentation')
            safe_prompt = (documentation_prompt or "").replace('＠', '@')
            # 附加 DDL
            if ddl_list:
                safe_prompt += "\n\n===Tables (DDL)===\n" + "\n\n".join(ddl_list[:50])
            # 附加 documentation
            if docs_list:
                safe_prompt += "\n\n===Additional Context===\n" + "\n\n".join(docs_list[:20])
            # 附加 QA 範例（只放部分避免過長）
            if qa_examples:
                safe_prompt += "\n\n===Question-SQL Examples===\n"
                for q, s in qa_examples[:30]:
                    safe_prompt += f"\nQ: {q}\nSQL: {s}\n"
            question = "請根據上述上下文（DDL、文件、問答範例），生成一份全面的技術文件，詳細描述其架構、業務邏輯與查詢模式。請勿輸出 SQL 程式碼，只要文字分析。"
            message_log = [
                vn.system_message(safe_prompt),
                vn.user_message(question)
            ]
            try:
                response_text = vn.submit_prompt(message_log)
            except Exception as e:
                err_msg = str(e)
                logger.error(f"analyze_schema JSON path submit_prompt failed: {err_msg}")
                if "The string did not match the expected pattern" in err_msg:
                    fallback_system = "你是一位資料庫技術文件生成助手。請用繁體中文，依照使用者需求，產出結構化技術文件，包含：架構總覽、主要資料表、關聯關係、業務流程、典型查詢模式、索引與效能建議、安全與權限、維運建議。不要產生SQL，只要文字分析。"
                    message_log = [
                        vn.system_message(fallback_system),
                        vn.user_message(question)
                    ]
                    response_text = vn.submit_prompt(message_log)
                else:
                    raise

            final_analysis = str(response_text) if response_text is not None else ""
            if final_analysis.strip():
                with get_user_db_connection(user_id) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "REPLACE INTO training_documentation (dataset_id, table_name, documentation_text) VALUES (?, ?, ?)",
                        (dataset_id, '__dataset_analysis__', final_analysis)
                    )
                    conn.commit()
                return jsonify({'status': 'success', 'analysis_result': final_analysis})
            else:
                return jsonify({'status': 'error', 'message': 'AI 模型未返回有效內容。'}), 500
        except Exception as e:
            logger.exception("analyze_schema JSON path failed")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def generate_analysis_stream():
        try:
            # 開始進度
            yield "data: " + json.dumps({'type': 'progress', 'percentage': 5, 'message': '開始資料庫結構分析'}) + "\n\n"
            yield "data: " + json.dumps({'chunk': '# 正在開始資料庫結構分析...\n\n'}) + "\n\n"
            
            vn = get_vanna_instance(user_id)
            vn = configure_vanna_for_request(vn, user_id, dataset_id)
            yield "data: " + json.dumps({'type': 'progress', 'percentage': 10, 'message': '初始化分析環境完成'}) + "\n\n"
            # The question for meta-analysis
            question = "請根據您所知道的所有關於此資料庫的上下文（DDL, 文件, 問答範例），生成一份全面的技術文件，詳細描述其架構、業務邏輯和查詢模式。"
            
            # We use generate_sql because it internally calls get_sql_prompt which handles context stuffing and token limits.
            # The 'SQL' it generates in this case will actually be our documentation.
            # We also override the initial prompt to use our 'documentation' template.
            documentation_prompt = load_prompt_template('documentation')
            
            yield "data: " + json.dumps({'type': 'progress', 'percentage': 25, 'message': '正在構建提示（包含 DDL/文件/QA 上下文）'}) + "\n\n"
            yield "data: " + json.dumps({'chunk': '## 步驟 1/2: 使用 Vanna 安全地建構提示...\n\n'}) + "\n\n"
            
            # Use submit_prompt directly with streaming to avoid SQL-specific extraction and regex issues
            # Sanitize known problematic full-width symbols in the prompt template
            safe_prompt = (documentation_prompt or "").replace('＠', '@')
            message_log = [
                vn.system_message(safe_prompt),
                vn.user_message(question)
            ]
            yield "data: " + json.dumps({'type': 'progress', 'percentage': 40, 'message': '提示構建完成，發送至 LLM 模型'}) + "\n\n"
            # Non-streaming request to simplify processing with fallback handling
            try:
                response_text = vn.submit_prompt(message_log)
            except Exception as e:
                err_msg = str(e)
                logger.error(f"analyze_schema submit_prompt failed: {err_msg}")
                # 特殊處理: 正則匹配錯誤或未知格式問題時，使用簡化版提示詞重試一次
                if "The string did not match the expected pattern" in err_msg:
                    yield "data: " + json.dumps({'chunk': '⚠️ 偵測到模型回應格式問題，正在使用簡化提示詞重試...\n\n'}) + "\n\n"
                    fallback_system = "你是一位資料庫技術文件生成助手。請用繁體中文，依照使用者需求，產出結構化技術文件，包含：架構總覽、主要資料表、關聯關係、業務流程、典型查詢模式、索引與效能建議、安全與權限、維運建議。不要產生SQL，只要文字分析。"
                    message_log = [
                        vn.system_message(fallback_system),
                        vn.user_message(question)
                    ]
                    try:
                        response_text = vn.submit_prompt(message_log)
                    except Exception as e2:
                        logger.error(f"analyze_schema fallback submit_prompt failed: {e2}")
                        raise
                else:
                    raise
            
            yield "data: " + json.dumps({'chunk': '## 步驟 2/2: 發送給 AI 模型並接收分析結果...\n\n---\n\n'}) + "\n\n"

            final_analysis = str(response_text) if response_text is not None else ""
            if final_analysis:
                # Stream the single response as multiple SSE chunks for better UI responsiveness
                def _chunk_text(text, max_len=1500):
                    paragraphs = re.split(r'\n{2,}', text)
                    buf = ""
                    for para in paragraphs:
                        if not para:
                            continue
                        # If adding this paragraph would exceed max_len, yield the buffer first
                        if buf and len(buf) + len(para) + 2 > max_len:
                            yield buf
                            buf = ""
                        # Append the paragraph with a blank line separator
                        if buf:
                            buf += "\n\n" + para
                        else:
                            buf = para
                    if buf:
                        yield buf
                chunk_count = 0
                total_chars = 0
                for part in _chunk_text(final_analysis):
                    chunk_count += 1
                    total_chars += len(part)
                    yield "data: " + json.dumps({'chunk': part}) + "\n\n"
                avg_size = (total_chars / chunk_count) if chunk_count else 0
                logger.info(f"Schema analysis chunking: parts={chunk_count}, total_chars={total_chars}, avg_size={avg_size:.1f}")
            
            if final_analysis and final_analysis.strip():
                with get_user_db_connection(user_id) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "REPLACE INTO training_documentation (dataset_id, table_name, documentation_text) VALUES (?, ?, ?)",
                        (dataset_id, '__dataset_analysis__', final_analysis)
                    )
                    conn.commit()
                yield "event: message\ndata: \n\n分析報告已成功儲存。\n\n"
            else:
                yield "event: message\ndata: \n\n分析失敗：AI 模型未返回有效內容。\n\n"

            yield "event: end_of_stream\ndata: {}\n\n"

        except Exception as e:
            from flask import current_app
            current_app.logger.error(f"Error during schema analysis stream for user '{user_id}', dataset '{dataset_id}': {e}", exc_info=True)
            error_data = {'error': f"An internal error occurred: {e}"}
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"

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