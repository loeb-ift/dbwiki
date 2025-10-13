from flask import Blueprint, request, jsonify, session, Response, stream_with_context
import json
import re
import os
import pandas as pd
import traceback
import threading
import logging
from sqlalchemy.exc import OperationalError

from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request, MyVanna
from app.core.helpers import load_prompt_template, _delete_all_ask_logs, write_ask_log

logger = logging.getLogger(__name__)

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

    # 在執行 Vanna 邏輯的線程中運行
    def run_vanna_in_thread(vn_instance: MyVanna, question: str, dataset_id: str, user_id: str):
        # 由於應用上下文對於線程是局部的，我們需要在線程內部導入應用以確保其存在
        from app import app as flask_app
        with flask_app.app_context():
            try:
                # 記錄請求開始
                write_ask_log(user_id, "request_start", f"Starting question processing: {question}")
                
                vn = configure_vanna_for_request(vn_instance, user_id, dataset_id)
        
                # 1. Retrieve context and stream it to the frontend
                similar_qa = vn.get_similar_question_sql(question=question)
                if similar_qa:
                    vn_instance.log_queue.put({'type': 'retrieved_context', 'subtype': 'qa', 'content': similar_qa})

                related_ddl = vn.get_related_ddl(question=question)
                if related_ddl:
                    vn_instance.log_queue.put({'type': 'retrieved_context', 'subtype': 'ddl', 'content': related_ddl})

                related_docs = vn.get_related_documentation(question=question)
                if related_docs:
                    vn_instance.log_queue.put({'type': 'retrieved_context', 'subtype': 'documentation', 'content': related_docs})

                # 2. Perform the analysis step
                vn_instance.log_queue.put({'type': 'info', 'content': "正在請求 LLM 進行綜合分析..."})
                
                # Format context for the analysis prompt
                similar_qa_str = "\n".join([f"Question: {qa['question']}\nSQL: {qa['sql']}" for qa in similar_qa]) if similar_qa else "無"
                related_ddl_str = "\n".join(related_ddl) if related_ddl else "無"
                related_docs_str = "\n".join(related_docs) if related_docs else "無"

                try:
                    analysis_prompt_template = vn.get_prompt('analysis')
                except Exception:
                    analysis_prompt_template = "請根據以下信息，為生成 SQL 提供一個詳細的思考過程分析表。\n"

                analysis_prompt_content = f"""
                原始問題: {question}
                檢索到的相似問題與 SQL 範例: {similar_qa_str}
                檢索到的相關資料庫結構 (DDL): ```sql\n{related_ddl_str}\n```
                檢索到的相關業務文件: {related_docs_str}
                """
                full_analysis_prompt = analysis_prompt_template + analysis_prompt_content
                
                analysis_result = vn.submit_prompt([{'role': 'user', 'content': full_analysis_prompt}])
                vn_instance.log_queue.put({'type': 'explanation', 'content': analysis_result})

                # 3. Generate SQL
                sql = None
                if similar_qa and similar_qa[0].get('similarity', 0) > 0.95:
                    sql = similar_qa[0]['sql']
                    vn_instance.log_queue.put({'type': 'info', 'content': f"找到高度相似的已存問題，直接使用其 SQL。"})
                else:
                    vn_instance.log_queue.put({'type': 'info', 'content': "正在請求 LLM 生成新的 SQL..."})
                    sql_generator = vn.generate_sql(question=question, allow_gpt_oss_to_see_logs=True)
                    sql = "".join(sql_generator)
                
                vn_instance.log_queue.put({'type': 'sql', 'content': sql})
                write_ask_log(user_id, "generated_sql", sql)

                if re.match(r'^[\s]*WITH[\s]+.*?[\)][\s]*$', sql, re.DOTALL | re.IGNORECASE):
                    cte_match = re.match(r'^[\s]*WITH[\s]+(\w+)[\s]+AS[\s]+\([\s]*', sql, re.DOTALL | re.IGNORECASE)
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

                if not df.empty:
                    vn_instance.log_queue.put({'type': 'df', 'content': df.to_json(orient='split', date_format='iso')})
                else:
                    vn_instance.log_queue.put({'type': 'message', 'content': 'SQL查詢返回空結果。'})
                
                chart_code = vn.generate_plotly_code(question=question, sql=sql, df=df)
                if chart_code:
                    vn_instance.log_queue.put({'type': 'chart', 'content': chart_code})
                
                # The new analysis step already provides an explanation.
                # The call to generate_explanatory_sql is redundant and has been removed.
                
                followup_questions = vn.generate_followup_questions(question=question, sql=sql, df=df, user_id=user_id)
                if followup_questions:
                    vn_instance.log_queue.put({'type': 'followup_questions', 'content': followup_questions})
                
                vn_instance.log_queue.put({'type': 'complete'})

                write_ask_log(user_id, "request_end", "Question processing completed successfully.")

            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                full_traceback = traceback.format_exc()
                logger.error(f"Exception in run_vanna_in_thread: {full_traceback}")
                
                # Ensure log_queue is accessible for error logging
                if hasattr(vn_instance, 'log_queue'):
                    vn_instance.log_queue.put({'type': 'error', 'message': error_msg, 'traceback': full_traceback})
                else:
                    logger.error(f"MyVanna instance has no log_queue attribute when trying to log error: {error_msg}")
                
            finally:
                if hasattr(vn_instance, 'log_queue'):
                    vn_instance.log_queue.put(None) # 發送終止信號
                else:
                    logger.error("MyVanna instance has no log_queue attribute when trying to send termination signal.")

    def stream_logs():
        vanna_thread = threading.Thread(target=run_vanna_in_thread, args=(vn_instance, question, dataset_id, user_id))
        vanna_thread.start()

        chunk_count = 0
        total_chars = 0
        while True:
            item = vn_instance.log_queue.get()
            if item is None:
                break
            payload = json.dumps(item)
            total_chars += len(payload)
            chunk_count += 1
            yield f"data: {payload}\n\n"
        logger.info(f"Ask SSE stream: parts={chunk_count}, total_chars={total_chars}, avg_size={(total_chars/chunk_count) if chunk_count else 0:.1f}")
        
        vanna_thread.join()

    return Response(stream_with_context(stream_logs()), mimetype='text/event-stream')