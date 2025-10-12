from flask import Blueprint, request, jsonify, session, Response, stream_with_context
import json
import re
import os
import pandas as pd
import traceback
import threading
from flask import Blueprint, request, session, jsonify, Response, stream_with_context
from sqlalchemy.exc import OperationalError

from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request, MyVanna
from app.core.helpers import load_prompt_template, _get_all_ask_logs, _delete_all_ask_logs, write_ask_log

ask_bp = Blueprint('ask', __name__, url_prefix='/api/ask')

@ask_bp.route('', methods=['POST'])
def ask_question():
    # Check if user is logged in
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'User not authenticated. Please login.'}), 401
        
    user_id = session['username']
    data = request.json
    question = data.get('question')
    if not question:
        return jsonify({'status': 'error', 'message': 'Question is required.'}), 400

    vn_instance = get_vanna_instance(user_id)
    dataset_id = session.get('active_dataset')

    def run_vanna_in_thread(vn_instance: MyVanna, question: str, dataset_id: str, user_id: str):
        try:
            # 记录请求开始
            write_ask_log(user_id, "request_start", f"Starting question processing: {question}")
            
            vn = configure_vanna_for_request(vn_instance, user_id, dataset_id)
        
            # The following block is removed as it incorrectly re-trains data from a temp file on every ask.
            # The correct approach is to rely on the already trained data in the vector database.
            # The training should happen separately in the training section of the application.
            similar_qa = vn.get_similar_question_sql(question=question)
            # -- DEBUG LOGGING START --
            log_message = f"Found {len(similar_qa)} similar QA pairs."
            if similar_qa:
                log_message += f" Top match: {similar_qa[0]['question']} with score {similar_qa[0].get('similarity', 'N/A')}"
            vn.log(log_message, "DEBUG")
            write_ask_log(user_id, "debug_similar_qa", log_message)
            # -- DEBUG LOGGING END --
            related_ddl = vn.get_related_ddl(question=question)
            related_docs = vn.get_related_documentation(question=question)

            # -- FIX: Prioritize exact matches from training data --
            sql = None
            if similar_qa and similar_qa[0].get('similarity', 0) > 0.95:
                sql = similar_qa[0]['sql']
                vn.log(f"Found a high-confidence match in training data. Using pre-existing SQL.", "Info")
                write_ask_log(user_id, "using_trained_sql", f"Using trained SQL for question: {similar_qa[0]['question']}")
            
            if sql is None:
                vn.log(f"No high-confidence match found. Generating new SQL with LLM.", "Info")
                sql = vn.generate_sql(question=question)

            write_ask_log(user_id, "generated_sql", sql)  # 记录生成的SQL

            if re.match(r'^\s*WITH\s+.*?\)\s*$', sql, re.DOTALL | re.IGNORECASE):
                cte_match = re.match(r'^\s*WITH\s+(\w+)\s+AS\s+\(', sql, re.DOTALL | re.IGNORECASE)
                if cte_match:
                    cte_name = cte_match.group(1)
                    sql = f"{sql}\nSELECT * FROM {cte_name};"
                    vn.log(f"檢測到不完整的 WITH 語句，已嘗試修正為: {sql}", "警告")

            try:
                df = vn.run_sql(sql=sql)
            except OperationalError as e:
                if "no such table" in str(e):
                    vn.log(f"SQL 執行被跳過，因為找不到資料表。", "警告")
                else:
                    vn.log(f"SQL 執行失敗: {e}", "錯誤")
                df = pd.DataFrame()
                write_ask_log(user_id, "sql_execution_error", str(e))
        
            if df.empty:
                # 增强日志记录，确保SQL查询返回空结果的信息被正确记录
                log_message = f"SQL 查询 '{sql}' 返回空结果，尝试修正SQL..."
                vn.log(log_message, "警告")
                vn.log_queue.put({'type': 'warning', 'message': log_message, 'sql': sql})
                write_ask_log(user_id, "empty_sql_result", f"SQL query returned empty result: {sql}")
            
            # 新增：生成 Plotly 圖表
            plotly_json = None
            try:
                fig = None
                if not df.empty:
                    vn.log("正在生成 Plotly 圖表程式碼...", "資訊")
                    plotly_code = vn.generate_plotly_code(question=question, sql=sql, df_metadata=f"Running df.dtypes gives:\n {df.dtypes}")
                    write_ask_log(user_id, "generated_plotly_code", plotly_code)

                    vn.log("正在執行 Plotly 程式碼以生成圖表...", "資訊")
                    fig = vn.get_plotly_figure(plotly_code=plotly_code, df=df)
                
                if fig:
                    plotly_json = fig.to_json()
                    vn.log("成功生成 Plotly 圖表 JSON。", "資訊")
                    write_ask_log(user_id, "generated_plotly_json_success", "Plotly JSON generated.")
                else:
                    # 如果沒有圖表（因為 df 為空或生成失敗），則創建一個空的圖表
                    vn.log("未能生成 Plotly 圖表物件或資料為空，將創建一個空的圖表。", "警告")
                    import plotly.graph_objects as go
                    fig = go.Figure()
                    fig.update_layout(
                        title_text="無資料可供顯示",
                        xaxis={"visible": False},
                        yaxis={"visible": False},
                        annotations=[
                            {
                                "text": "查詢結果為空，無法生成圖表。",
                                "xref": "paper",
                                "yref": "paper",
                                "showarrow": False,
                                "font": {
                                    "size": 16
                                }
                            }
                        ]
                    )
                    plotly_json = fig.to_json()
                    write_ask_log(user_id, "empty_plotly_chart_created", "An empty chart was created as a placeholder.")

            except Exception as e:
                vn.log(f"生成 Plotly 圖表時出錯: {e}", "錯誤")
                write_ask_log(user_id, "plotly_generation_error", str(e))

            analysis_result = None
            try:
                ask_analysis_prompt_template = load_prompt_template('analysis')

                def format_similar_qa_as_markdown(qa_list):
                    if not qa_list:
                        return "無"
                    header = "| 相似問題 | 相關 SQL 範例 |\n|---|---|\n"
                    rows = [f"| {item.get('question', '')} | ```sql\n{item.get('sql', '')}\n``` |" for item in qa_list]
                    return header + "\n".join(rows)

                def format_ddl_as_markdown(ddl_list):
                    if not ddl_list:
                        return "無"
                    return f"```sql\n{''.join(ddl_list)}\n```"
                
                def format_docs_as_markdown(doc_list):
                    if not doc_list:
                        return "無"
                    return "\n---\n".join(doc_list)

                formatted_similar_qa = format_similar_qa_as_markdown(similar_qa)
                formatted_ddl = format_ddl_as_markdown(related_ddl)
                formatted_docs = format_docs_as_markdown(related_docs)

                dynamic_prompt_content = ask_analysis_prompt_template.replace(
                    "[用戶提出的原始自然語言問題]", question
                ).replace(
                    "[列出檢索到的相似問題和 SQL 範例]", formatted_similar_qa
                ).replace(
                    "[列出檢索到的相關 DDL 語句]", formatted_ddl
                ).replace(
                    "[列出檢索到的相關業務文件內容]", formatted_docs
                )

                # 保存動態提示詞到歷史紀錄
                try:
                    import time
                    prompt_history_dir = os.path.join(os.getcwd(), 'prompt_history')
                    os.makedirs(prompt_history_dir, exist_ok=True)
                    timestamp = int(time.time())
                    prompt_filename = f"{user_id}_dynamic_prompt_{timestamp}.txt"
                    prompt_filepath = os.path.join(prompt_history_dir, prompt_filename)
                    with open(prompt_filepath, 'w', encoding='utf-8') as f:
                        f.write(dynamic_prompt_content)
                    try:
                        from app import app as flask_app
                        with flask_app.app_context():
                            flask_app.logger.info(f"Dynamic prompt saved to history: {prompt_filepath}")
                    except (ImportError, RuntimeError):
                        print(f"Dynamic prompt saved to history: {prompt_filepath}")
                    write_ask_log(user_id, "dynamic_prompt_saved", f"Prompt saved to: {prompt_filepath}")
                except Exception as e:
                    try:
                        from app import app as flask_app
                        with flask_app.app_context():
                            flask_app.logger.error(f"Error saving dynamic prompt to history: {e}")
                    except (ImportError, RuntimeError):
                        print(f"Error saving dynamic prompt to history: {e}")
                    write_ask_log(user_id, "save_prompt_error", str(e))

                vn.log("正在將思考過程發送給 Ollama 進行分析...", "資訊")
                analysis_result = vn.submit_prompt([{'role': 'user', 'content': dynamic_prompt_content}])
                vn.log("Ollama 分析完成。", "資訊")
                write_ask_log(user_id, "ollama_analysis_result", str(analysis_result))  # 记录Ollama的分析结果

                # 不删除日志，保留以便调试和分析
                # _delete_all_ask_logs(user_id)

            except Exception as e:
                vn.log(f"生成、發送給 Ollama 或保存動態提示詞時出錯: {e}", "錯誤")
                write_ask_log(user_id, "analysis_error", str(e))
        
            logs = []
            while not vn.log_queue.empty():
                logs.append(vn.log_queue.get())
        
            similar_qa_details = [log['details'] for log in logs if log['step'] == '相似問題檢索完成']
            ddl_details = [log['details'] for log in logs if log['step'] == 'DDL 檢索完成']
            doc_details = [log['details'] for log in logs if log['step'] == '文件檢索完成']
        
            vn_instance.log_queue.put({
                'type': 'result',
                'sql': sql,
                'df_json': df.to_json(orient='records'),
                'plotly_json': plotly_json,  # 新增 plotly_json
                'similar_qa_details': similar_qa_details,
                'ddl_details': ddl_details,
                'doc_details': doc_details,
                'analysis_result': analysis_result
            })
            write_ask_log(user_id, "request_complete", "Question processing completed")
        except Exception as e:
            error_msg = f"Processing error: {str(e)}"
            vn_instance.log_queue.put({'type': 'error', 'message': error_msg, 'traceback': traceback.format_exc()})
            write_ask_log(user_id, "request_error", error_msg)
        finally:
            vn_instance.log_queue.put(None)

    def stream_logs():
        vanna_thread = threading.Thread(target=run_vanna_in_thread, args=(vn_instance, question, dataset_id, user_id))
        vanna_thread.start()

        while True:
            item = vn_instance.log_queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"
        
        vanna_thread.join()

    return Response(stream_with_context(stream_logs()), mimetype='text/event-stream')