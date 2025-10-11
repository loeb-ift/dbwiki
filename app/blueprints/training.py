from flask import Blueprint, request, jsonify, session, Response, stream_with_context
import json
import sqlite3
from flask import Blueprint, request, jsonify, session, Response, stream_with_context
from sqlalchemy import inspect, text

from app.core.db_utils import get_user_db_connection
from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request
from app.core.helpers import load_prompt_template

training_bp = Blueprint('training', __name__, url_prefix='/api')

@training_bp.route('/training_data', methods=['GET'])
def get_training_data():
    user_id = session['username']
    table_name = request.args.get('table_name', 'global')
    page = int(request.args.get('page', 1))
    page_size = 10
    offset = (page - 1) * page_size
    dataset_id = session.get('active_dataset')

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
        dataset_analysis = analysis_row['documentation_text'] if analysis_row else ""

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
    data = request.get_json()
    doc_content = data.get('documentation', '')
    table_name = data.get('table_name', 'global')
    dataset_id = session.get('active_dataset')

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
    data = request.get_json()
    question = data.get('question')
    sql_query = data.get('sql')
    table_name = data.get('table_name', 'global')
    dataset_id = session.get('active_dataset')

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
    dataset_id = session.get('active_dataset')
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
                    # 发送每个问答对的进度更新
                    if i % 5 == 0 or i == total_pairs - 1:  # 每处理5个问答对或最后一个时更新
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
    user_id = session['username']
    dataset_id = session.get('active_dataset')

    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400

    try:
        vn = get_vanna_instance(user_id)
        vn = configure_vanna_for_request(vn, user_id, dataset_id)

        inspector = inspect(vn.engine)
        table_names = inspector.get_table_names()
        ddl_statements = []
        with vn.engine.connect() as connection:
            for name in table_names:
                ddl = connection.execute(text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{name}';")).scalar()
                if ddl: ddl_statements.append(ddl + ";")
        full_ddl = "\n".join(ddl_statements)

        with get_user_db_connection(user_id) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT documentation_text FROM training_documentation WHERE dataset_id = ? AND table_name != '__dataset_analysis__'", (dataset_id,))
            documentation_rows = cursor.fetchall()
            knowledge_docs = "\n".join([row['documentation_text'] for row in documentation_rows])

            cursor.execute("SELECT question, sql_query FROM training_qa WHERE dataset_id = ?", (dataset_id,))
            qa_pairs_rows = cursor.fetchall()
            qa_pairs_str = "\n".join([f"問: {row['question']}\n答: {row['sql_query']}" for row in qa_pairs_rows])

        documentation_prompt_content = load_prompt_template('documentation')
        
        prompt_content = f"""
DDL 語句:
{full_ddl}

業務術語:
{knowledge_docs if knowledge_docs else "無"}

SQL 查詢集合:
{qa_pairs_str if qa_pairs_str else "無"}

請務必以繁體中文生成所有分析結果和建議。
"""
        prompt = documentation_prompt_content + prompt_content

        analysis_documentation = vn.submit_prompt([{'role': 'user', 'content': prompt}])

        if analysis_documentation:
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                analysis_table_name = '__dataset_analysis__'
                cursor.execute(
                    "REPLACE INTO training_documentation (dataset_id, table_name, documentation_text) VALUES (?, ?, ?)",
                    (dataset_id, analysis_table_name, analysis_documentation)
                )
                conn.commit()

        return jsonify({
            'status': 'success',
            'analysis': analysis_documentation or "無法生成資料庫分析文件。"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@training_bp.route('/generate_documentation_from_analysis', methods=['POST'])
def generate_documentation_from_analysis():
    user_id = session['username']
    dataset_id = session.get('active_dataset')

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
    dataset_id = session.get('active_dataset')

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