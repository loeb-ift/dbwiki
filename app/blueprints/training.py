from flask import Blueprint, request, jsonify, session, Response, stream_with_context
import json
import sqlite3
from sqlalchemy import inspect, text
import logging
import re

from app.core.db_utils import get_user_db_connection
from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request
from app.core.helpers import load_prompt_template, get_dataset_tables, extract_column_features

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
        
        # Fetch both analysis and serial number results
        cursor.execute("SELECT documentation_text FROM training_documentation WHERE table_name = ? AND dataset_id = ?", ('__dataset_analysis__', dataset_id))
        analysis_row = cursor.fetchone()
        dataset_analysis = analysis_row['documentation_text'] if analysis_row else ""

        cursor.execute("SELECT documentation_text FROM training_documentation WHERE table_name = ? AND dataset_id = ?", ('__serial_number_analysis__', dataset_id))
        serial_number_row = cursor.fetchone()
        serial_number_analysis = serial_number_row['documentation_text'] if serial_number_row else ""

        if not dataset_analysis and not serial_number_analysis:
            initial_message = """# 尚無資料庫結構分析
點擊下方的「資料庫自動分析」按鈕，讓 AI 為您生成一份關於此資料庫的結構、內容與查詢方式的綜合分析報告。
"""
        else:
            initial_message = ""

    response_data = {
        'documentation': documentation,
        'qa_pairs': qa_pairs,
        'dataset_analysis': dataset_analysis or initial_message,
        'serial_number_analysis': serial_number_analysis,
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
                cursor.execute("SELECT ddl_statement FROM training_ddl WHERE dataset_id = ?", (dataset_id,))
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
                percentage = (completed_steps / total_steps) * 100
                yield f"data: {json.dumps({'percentage': percentage, 'message': 'DDL 訓練完成。', 'log': 'DDL training completed.'})}\n\n"
            
            # 3. 训练文档
            if doc_list:
                full_doc = "\n\n".join(doc_list)
                vn.train(documentation=full_doc)
                completed_steps += 1
                percentage = (completed_steps / total_steps) * 100
                yield f"data: {json.dumps({'percentage': percentage, 'message': '文件訓練完成。', 'log': 'Documentation training completed.'})}\n\n"

            # 4. 训练QA对
            if qa_list:
                total_pairs = len(qa_list)
                # The progress portion allocated to this step
                qa_step_progress_share = 1 / total_steps
                
                for i, pair in enumerate(qa_list):
                    if pair.get('question') and pair.get('sql'):
                        vn.train(question=pair['question'], sql=pair['sql'])
                    
                    # Update progress at intervals
                    if i % 10 == 0 or i == total_pairs - 1:
                        # Progress of the steps before this one
                        base_progress = (completed_steps / total_steps) * 100
                        # Progress within the current QA step
                        qa_progress_inner = ((i + 1) / total_pairs) * qa_step_progress_share * 100
                        current_percentage = base_progress + qa_progress_inner
                        yield f"data: {json.dumps({'percentage': current_percentage, 'message': f'正在訓練問答配對... ({i+1}/{total_pairs})', 'log': f'Training QA pair {i+1}/{total_pairs}'})}\n\n"
                
                completed_steps += 1
                percentage = (completed_steps / total_steps) * 100
                yield f"data: {json.dumps({'percentage': percentage, 'message': f'問答配對 ({len(qa_list)} 組) 訓練完成。', 'log': f'QA pair training for {len(qa_list)} pairs completed.'})}\n\n"

            # Final completion message
            if completed_steps == total_steps and total_steps > 0:
                # Ensure the final message is always 100% if all steps are done
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
        return jsonify({'status': 'error', 'message': 'User not logged in or no active dataset selected.'}), 400

    def generate_analysis_stream(vn, ddl_list, doc_list, qa_list):
        try:
            # The stream now starts after basic setup is complete
            yield f"data: {json.dumps({'type': 'info', 'message': '開始資料庫結構分析...'})}\n\n"
            
            # 1. Generate Schema Documentation
            documentation_prompt = load_prompt_template('documentation')
            safe_prompt = (documentation_prompt or "").replace('＠', '@')
            if ddl_list: safe_prompt += "\n\n===Tables (DDL)===\n" + "\n\n".join(ddl_list)
            
            question = "請根據上述 DDL，生成一份全面的技術文件，詳細描述其架構與設計。"
            message_log = [vn.system_message(safe_prompt), vn.user_message(question)]
            
            yield f"data: {json.dumps({'type': 'info', 'message': '正在呼叫 LLM 進行結構分析...'})}\n\n"
            documentation_analysis = vn.submit_prompt(message_log)
            
            yield f"data: {json.dumps({'type': 'analysis_result', 'content': documentation_analysis})}\n\n"
            
            # 2. Serial Number Analysis
            serial_number_analysis_result = ""
            yield f"data: {json.dumps({'type': 'info', 'message': '開始流水號/料號規則分析...'})}\n\n"
            try:
                # Phase 1: Field Discovery
                yield f"data: {json.dumps({'type': 'info', 'message': '階段一：正在請求 LLM 識別潛在的流水號欄位...'})}\n\n"
                
                # Use the data passed into the function, do not fetch again
                discovery_context = "=== DDL 結構 ===\n" + "\n\n".join(ddl_list) + "\n\n"
                if doc_list: discovery_context += "=== 業務文件 ===\n" + "\n\n".join(doc_list) + "\n\n"
                if qa_list: discovery_context += "=== SQL 問答範例 ===\n" + "\n".join([f"Q: {qa['question']}\nSQL: {qa['sql']}" for qa in qa_list]) + "\n\n"

                discovery_prompt = load_prompt_template('serial_number_candidate_generation')
                full_discovery_prompt = discovery_prompt + "\n\n" + discovery_context
                
                llm_response_str = vn.submit_prompt([vn.user_message(full_discovery_prompt)])
                
                candidate_columns_from_llm = []
                try:
                    if llm_response_str and llm_response_str.strip():
                        # Extract JSON from markdown code block if present
                        if "```json" in llm_response_str:
                            json_str = llm_response_str.split("```json")[1].split("```")[0].strip()
                        else:
                            json_str = llm_response_str.strip()
                        
                        if json_str:
                            candidate_columns_from_llm = json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to decode JSON from LLM response for candidate generation. Response: '{llm_response_str}'. Error: {e}")
                    yield f"data: {json.dumps({'type': 'warning', 'message': f'階段一 LLM 回應非預期格式，無法解析候選欄位。'})}\n\n"
                except Exception as e:
                    logger.error(f"An unexpected error occurred during candidate JSON parsing: {e}", exc_info=True)

                yield f"data: {json.dumps({'type': 'info', 'message': f'階段一完成：識別出 {len(candidate_columns_from_llm)} 個候選欄位。'})}\n\n"
                
                # Phase 2: Feature Extraction
                yield f"data: {json.dumps({'type': 'info', 'message': '階段二：正在對每個候選欄位進行資料特徵提取...'})}\n\n"
                
                enriched_candidates = []
                for i, candidate in enumerate(candidate_columns_from_llm):
                    table = candidate.get('table_name')
                    column = candidate.get('column_name')
                    if not table or not column: continue

                    yield f"data: {json.dumps({'type': 'info', 'message': f'正在提取 {table}.{column} 的特徵...'})}\n\n"
                    
                    values_from_qa = [match for qa in qa_list if qa['sql'] for match in re.findall(rf"WHERE\s+`?{re.escape(column)}`?\s*(?:=|LIKE)\s*'([^']+)'", qa['sql'], re.IGNORECASE)]
                    
                    features = extract_column_features(values=values_from_qa)
                    
                    ddl = next((d for d in ddl_list if f"CREATE TABLE {table}" in d or f'CREATE TABLE "{table}"' in d), "")
                    
                    enriched_candidates.append({
                        "rank": i + 1,
                        "confidence_score": candidate.get('confidence_score', 0.8),
                        "table_name": table,
                        "column_name": column,
                        "data_type": next((line.split()[1] for line in ddl.split('\n') if column in line), "UNKNOWN"),
                        "佐證資料": {"來自LLM的判斷依據": candidate.get('判斷依據', '')},
                        "statistics": features,
                        "sample_values": list(set(values_from_qa))[:10]
                    })

                yield f"data: {json.dumps({'type': 'info', 'message': '階段二完成：所有候選欄位的特徵提取完畢。'})}\n\n"

                # Phase 3 & 4: Pattern Recognition and Template Generation
                yield f"data: {json.dumps({'type': 'info', 'message': '階段三/四：正在請求 LLM 進行模式識別與模板生成...'})}\n\n"

                final_prompt_template = load_prompt_template('pattern_and_template_generation')
                final_context = json.dumps({"candidate_columns": enriched_candidates}, ensure_ascii=False, indent=2)
                full_final_prompt = final_prompt_template + "\n\n" + final_context

                serial_number_analysis_result = vn.submit_prompt([vn.user_message(full_final_prompt)])
                
                yield f"data: {json.dumps({'type': 'info', 'message': '所有分析階段完成。'})}\n\n"

            except Exception as sn_e:
                logger.error(f"Error during serial number analysis: {sn_e}", exc_info=True)
                serial_number_analysis_result = f"流水號分析時發生錯誤: {sn_e}"
            
            yield f"data: {json.dumps({'type': 'serial_number_analysis_result', 'content': serial_number_analysis_result})}\n\n"

            # 5. Save results
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                if documentation_analysis.strip():
                    cursor.execute("REPLACE INTO training_documentation (dataset_id, table_name, documentation_text) VALUES (?, ?, ?)", (dataset_id, '__dataset_analysis__', documentation_analysis))
                if serial_number_analysis_result.strip():
                    cursor.execute("REPLACE INTO training_documentation (dataset_id, table_name, documentation_text) VALUES (?, ?, ?)", (dataset_id, '__serial_number_analysis__', serial_number_analysis_result))
                conn.commit()
            yield f"data: {json.dumps({'type': 'info', 'message': '分析結果已儲存。'})}\n\n"

        except Exception as e:
            logger.exception("Error during schema analysis stream")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'end_of_stream'})}\n\n"

    # Outer function setup
    try:
        vn = get_vanna_instance(user_id)
        vn = configure_vanna_for_request(vn, user_id, dataset_id)
        
        # Explicitly fetch all required training data within the route
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ddl_statement FROM training_ddl WHERE dataset_id = ?", (dataset_id,))
            ddl_list = [row[0] for row in cursor.fetchall()]
            
            cursor.execute("SELECT documentation_text FROM training_documentation WHERE dataset_id = ?", (dataset_id,))
            doc_list = [row[0] for row in cursor.fetchall() if row[0]]
            
            cursor.execute("SELECT question, sql_query FROM training_qa WHERE dataset_id = ?", (dataset_id,))
            qa_list = [{'question': row[0], 'sql': row[1]} for row in cursor.fetchall()]

        # Add logging to inspect the fetched data
        logger.info(f"Fetched {len(ddl_list)} DDL statements for analysis.")
        logger.info(f"Fetched {len(doc_list)} documents for analysis.")
        logger.info(f"Fetched {len(qa_list)} QA pairs for analysis.")

        # Pass the prepared data to the generator
        return Response(stream_with_context(generate_analysis_stream(vn, ddl_list, doc_list, qa_list)), mimetype='text/event-stream')
    except Exception as e:
        logger.exception("Error setting up analysis stream")
        # Return a single error event in case of setup failure
        def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'end_of_stream'})}\n\n"
        return Response(stream_with_context(error_stream()), mimetype='text/event-stream', status=500)


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