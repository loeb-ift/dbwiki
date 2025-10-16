from flask import Blueprint, request, jsonify, session, Response, stream_with_context, send_file
import json
import re
import os
import pandas as pd
import io
import csv
import traceback
import threading
import time
import logging
from sqlalchemy.exc import OperationalError
import plotly.express as px
import plotly.graph_objects as go

from plotly.utils import PlotlyJSONEncoder
from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request, MyVanna
from app.core.helpers import load_prompt_template, _delete_all_ask_logs, write_ask_log
import textwrap

logger = logging.getLogger(__name__)

ask_bp = Blueprint('ask', __name__, url_prefix='/api/ask')

_last_result_cache = {}

def create_chart_function(code_string: str):
    """
    Dynamically creates a Python function from a string of code.
    The generated function is expected to have the signature: create_chart(df, px, go)
    """
    if not code_string:
        return None, "No code provided"

    # Wrap the user's code in a function definition
    function_code = textwrap.dedent(f"""
    def create_chart(df, px, go):
    {textwrap.indent(code_string, '    ')}
        return fig
    """)
    
    try:
        # Execute the function definition in a temporary namespace
        namespace = {}
        exec(function_code, namespace)
        return namespace['create_chart'], None
    except SyntaxError as e:
        return None, f"Syntax error in generated code: {e}"
    except Exception as e:
        return None, f"An unexpected error occurred during function creation: {e}"

def run_vanna_in_thread(vn_instance: MyVanna, question: str, session_data: dict, server_paginate: bool, page: int, page_size: int):
    """This function runs the Vanna logic in a separate thread."""
    user_id = session_data['user_id']
    dataset_id = session_data['dataset_id']
    
    from app import app as flask_app
    with flask_app.app_context():
        try:
            write_ask_log(user_id, "request_start", f"Starting question processing: {question}")
            
            vn = configure_vanna_for_request(vn_instance, user_id, dataset_id)

            similar_qa = vn.get_similar_question_sql(question=question)
            if similar_qa:
                vn_instance.log_queue.put({'type': 'retrieved_context', 'subtype': 'qa', 'content': similar_qa})

            related_ddl = vn.get_related_ddl(question=question)
            if related_ddl:
                vn_instance.log_queue.put({'type': 'retrieved_context', 'subtype': 'ddl', 'content': related_ddl})

            related_docs = vn.get_related_documentation(question=question)
            if related_docs:
                vn_instance.log_queue.put({'type': 'retrieved_context', 'subtype': 'documentation', 'content': related_docs})

            sql = None
            if similar_qa and similar_qa[0].get('similarity', 0) > 0.95:
                sql = similar_qa[0]['sql']
                vn_instance.log_queue.put({'type': 'info', 'content': f"找到高度相似的已存問題，直接使用其 SQL。"})
            else:
                vn_instance.log_queue.put({'type': 'info', 'content': "正在請求 LLM 生成新的 SQL..."})
                gen_or_resp = vn.generate_sql(
                    question=question,
                    ddl_list=related_ddl,
                    doc_list=related_docs,
                    question_sql_list=similar_qa
                )

                full_llm_response = None
                collected_text = ""

                if hasattr(gen_or_resp, '__iter__') and not isinstance(gen_or_resp, (str, bytes)):
                    for part in gen_or_resp:
                        chunk = str(part.get('content', '')) if isinstance(part, dict) else str(part)
                        if chunk:
                            vn_instance.log_queue.put({'type': 'sql_chunk', 'content': chunk})
                            collected_text += chunk
                    full_llm_response = collected_text
                else:
                    full_llm_response = gen_or_resp

                if full_llm_response:
                    vn_instance.log_queue.put({'type': 'thought', 'content': full_llm_response})

                sql = vn.extract_sql(full_llm_response)
                if not sql:
                    raise ValueError("未能從模型回應中提取到有效的 SQL 語句。")
            
            vn_instance.log_queue.put({'type': 'sql', 'content': sql})
            write_ask_log(user_id, "generated_sql", sql)

            df = pd.DataFrame()
            try:
                # Dialect-specific SQL corrections
                if vn.engine.dialect.name == 'sqlite':
                    vn_instance.log_queue.put({'type': 'info', 'content': 'SQLite dialect detected. Applying date function corrections.'})
                    sql = sql.replace("DATE_SUB(CURDATE(), INTERVAL 30 DAY)", "date('now', '-30 days')")
                    sql = sql.replace("CURRENT_DATE - INTERVAL '30 days'", "date('now', '-30 days')")

                df = vn.run_sql(sql=sql)
                
                # More careful data cleaning: convert non-numeric types to strings, leave numbers alone
                for col in df.columns:
                    if df[col].dtype not in ['int64', 'float64']:
                        df[col] = df[col].fillna('').astype(str)

                if not df.empty:
                    _last_result_cache[user_id] = {'columns': list(df.columns), 'data': df.values.tolist()}
                    
                    if server_paginate and page_size > 0:
                        start = max(0, (page - 1) * page_size)
                        end = min(len(df), start + page_size)
                        paged_df = df.iloc[start:end]
                        payload = {
                            'columns': list(paged_df.columns),
                            'data': paged_df.values.tolist(),
                            'pagination': {'page': page, 'page_size': page_size, 'total_rows': len(df)}
                        }
                    else:
                         payload = {'columns': list(df.columns), 'data': df.values.tolist()}
                    vn_instance.log_queue.put({'type': 'df', 'content': payload})
                    vn_instance.log_queue.put({'type': 'download', 'content': {'url': '/api/ask/download_csv'}})
                else:
                    vn_instance.log_queue.put({'type': 'message', 'content': 'SQL查詢返回空結果。'})

            except Exception as e:
                error_message = f"SQL 執行失敗: {e}"
                vn_instance.log_queue.put({'type': 'sql_error', 'sql': sql, 'error': error_message})
                write_ask_log(user_id, "sql_execution_error", error_message)
            
            vn_instance.log_queue.put({'type': 'info', 'content': f"SQL 執行完畢，DataFrame 行數: {len(df)}"})
            
            if _last_result_cache.get(user_id):
                vn_instance.log_queue.put({'type': 'info', 'content': '可點擊下載 CSV 檔案以取得完整結果。'})
            
            if not df.empty:
                try:
                    vn_instance.log_queue.put({'type': 'info', 'content': 'Attempting to generate Plotly code...'})
                    chart_code = vn_instance.generate_plotly_code(question=question, sql=sql, df=df)

                    if chart_code:
                        # Final defensive fix: remove potential erroneous quotes around column names
                        chart_code = chart_code.replace("['\"product_name\"']", "['product_name']").replace("['\"monthly_total\"']", "['monthly_total']")

                        vn_instance.log_queue.put({'type': 'info', 'content': f"Vanna generated chart code (after defensive fix):\n{chart_code}"})
                        
                        # Create the chart function dynamically
                        create_chart, error = create_chart_function(chart_code)
                        
                        if error:
                            vn_instance.log_queue.put({'type': 'error', 'content': f"Failed to create chart function: {error}"})
                        else:
                            vn_instance.log_queue.put({'type': 'info', 'content': 'Successfully created chart function. Executing...'})
                            
                            # Intercept and log DataFrame info
                            buffer = io.StringIO()
                            df.info(buf=buffer)
                            df_info = buffer.getvalue()
                            vn_instance.log_queue.put({'type': 'debug', 'content': f"DataFrame Info before chart generation:\n{df_info}\n{df.head().to_string()}"})

                            # Execute the dynamically created function
                            try:
                                fig = create_chart(df, px, go)
                                if fig:
                                    vn_instance.log_queue.put({'type': 'info', 'content': 'Chart object created successfully. Serializing...'})
                                    chart_json = json.dumps(fig, cls=PlotlyJSONEncoder)
                                    vn_instance.log_queue.put({"type": "plotly_chart", "content": chart_json})
                                    vn_instance.log_queue.put({'type': 'info', 'content': 'Chart serialization complete.'})
                                else:
                                    vn_instance.log_queue.put({'type': 'warning', 'content': 'Execution of chart function did NOT return a "fig" object.'})
                            except Exception as e:
                                vn_instance.log_queue.put({
                                    'type': 'error',
                                    'content': f'An exception occurred during chart function execution: {str(e)}\nTraceback: {traceback.format_exc()}'
                                })
                    else:
                        vn_instance.log_queue.put({'type': 'info', 'content': 'Vanna did not generate any chart code.'})

                except Exception as e:
                    vn_instance.log_queue.put({
                        'type': 'error',
                        'content': f'An exception occurred during the chart generation process: {str(e)}\nTraceback: {traceback.format_exc()}'
                    })
            
            followup_questions = vn.generate_followup_questions(question=question, sql=sql, df=df, user_id=user_id)
            if followup_questions:
                vn_instance.log_queue.put({'type': 'followup_questions', 'content': followup_questions})
            
            vn_instance.log_queue.put({'type': 'complete'})
            write_ask_log(user_id, "request_end", "Question processing completed successfully.")

        except Exception as e:
            full_traceback = traceback.format_exc()
            logger.error(f"Exception in run_vanna_in_thread: {full_traceback}")
            vn_instance.log_queue.put({'type': 'error', 'message': str(e), 'traceback': full_traceback})
            
        finally:
            vn_instance.log_queue.put(None)

def stream_logs(vn_instance, question, session_data, server_paginate, page, page_size):
    """Generator function to stream logs from the Vanna thread."""
    vanna_thread = threading.Thread(target=run_vanna_in_thread, args=(vn_instance, question, session_data, server_paginate, page, page_size))
    vanna_thread.start()

    while True:
        item = vn_instance.log_queue.get()
        if item is None:
            break
        payload = json.dumps(item)
        yield f"data: {payload}\n\n"
    
    vanna_thread.join()

@ask_bp.route('', methods=['POST'])
def ask_question():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'User not authenticated. Please login.'}), 401
        
    user_id = session['username']
    _delete_all_ask_logs(user_id)
    
    data = request.json or {}
    question = data.get('question')
    if not question:
        return jsonify({'status': 'error', 'message': 'Question is required.'}), 400

    try:
        page = int(data.get('page', 0)) if data.get('page') is not None else 0
        page_size = int(data.get('page_size', 0)) if data.get('page_size') is not None else 0
        server_paginate = page > 0 and page_size > 0
    except (ValueError, TypeError):
        page = 0
        page_size = 0
        server_paginate = False

    vn_instance = get_vanna_instance(user_id)
    
    # Pass a copy of session data to the thread
    session_data = {
        'user_id': user_id,
        'dataset_id': session.get('active_dataset')
    }

    return Response(stream_with_context(stream_logs(vn_instance, question, session_data, server_paginate, page, page_size)), mimetype='text/event-stream')

@ask_bp.route('/download_csv', methods=['GET'])
def download_csv():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'User not authenticated.'}), 401
    
    user_id = session['username']
    result = _last_result_cache.get(user_id)
    
    if not result or not result.get('data'):
        return jsonify({'status': 'error', 'message': 'No data to download.'}), 404

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(result['columns'])
    writer.writerows(result['data'])
    csv_data = output.getvalue()
    
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=query_result.csv"}
    )
