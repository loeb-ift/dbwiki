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

from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request, MyVanna
from app.core.helpers import load_prompt_template, _delete_all_ask_logs, write_ask_log

logger = logging.getLogger(__name__)

ask_bp = Blueprint('ask', __name__, url_prefix='/api/ask')

# 用於在每次查詢後保存最近一次的結果，供 CSV 下載
# 結構：{ 'columns': [...], 'data': [[...], ...] }
_last_result_cache = {}

@ask_bp.route('', methods=['POST'])
def ask_question():
    # Check if user is logged in
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'User not authenticated. Please login.'}), 401
        
    user_id = session['username']
    
    # Clean up previous logs before starting a new request
    _delete_all_ask_logs(user_id)
    
    data = request.json or {}
    question = data.get('question')
    if not question:
        return jsonify({'status': 'error', 'message': 'Question is required.'}), 400

    # 後端分頁參數（可選）
    try:
        page = int(data.get('page', 0)) if data.get('page') is not None else 0
        page_size = int(data.get('page_size', 0)) if data.get('page_size') is not None else 0
        server_paginate = page > 0 and page_size > 0
    except Exception:
        page = 0
        page_size = 0
        server_paginate = False

    vn_instance = get_vanna_instance(user_id)
    dataset_id = session.get('active_dataset')

    # 在執行 Vanna 邏輯的線程中運行
    def run_vanna_in_thread(vn_instance: MyVanna, question: str, dataset_id: str, user_id: str, server_paginate: bool, page: int, page_size: int):
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

                # 3. Generate SQL
                sql = None
                if similar_qa and similar_qa[0].get('similarity', 0) > 0.95:
                    sql = similar_qa[0]['sql']
                    vn_instance.log_queue.put({'type': 'info', 'content': f"找到高度相似的已存問題，直接使用其 SQL。"})
                else:
                    vn_instance.log_queue.put({'type': 'info', 'content': "正在請求 LLM 生成新的 SQL..."})
                    # vn.generate_sql may be a generator (streaming) or return a full response.
                    gen_or_resp = vn.generate_sql(
                        question=question,
                        ddl_list=related_ddl,
                        doc_list=related_docs,
                        question_sql_list=similar_qa
                    )

                    full_llm_response = None
                    collected_text = ""

                    try:
                        # Treat as iterator if not a plain string/bytes
                        if hasattr(gen_or_resp, '__iter__') and not isinstance(gen_or_resp, (str, bytes)):
                            for part in gen_or_resp:
                                # Stream possible SQL chunks to the frontend
                                try:
                                    if isinstance(part, dict):
                                        # Common shapes: {type: 'text', content: '...'} or {'sql': '...'}
                                        if 'sql' in part and isinstance(part['sql'], str):
                                            chunk = part['sql']
                                        elif part.get('type') == 'text' and isinstance(part.get('content'), str):
                                            chunk = part.get('content')
                                        else:
                                            chunk = str(part)
                                    else:
                                        chunk = str(part)
                                    if chunk:
                                        vn_instance.log_queue.put({'type': 'sql_chunk', 'content': chunk})
                                        collected_text += chunk
                                except Exception:
                                    # Be resilient to any unexpected chunk format
                                    pass
                            full_llm_response = collected_text
                        else:
                            # It's a full response string
                            full_llm_response = gen_or_resp
                    except Exception:
                        # Fallback: ensure we have some response text
                        if isinstance(gen_or_resp, str):
                            full_llm_response = gen_or_resp
                        else:
                            full_llm_response = collected_text or ""

                    # Log the full response to be displayed as the thought process
                    if full_llm_response:
                        vn_instance.log_queue.put({'type': 'thought', 'content': full_llm_response})

                    # Extract the SQL from the full response
                    sql = vn.extract_sql(full_llm_response)
                    if not sql:
                        # Fallback: try using collected text directly
                        sql = collected_text.strip() if collected_text.strip() else None
                    if not sql:
                        raise ValueError("未能從模型回應中提取到有效的 SQL 語句。")
                
                # Log the extracted SQL separately (final SQL)
                vn_instance.log_queue.put({'type': 'sql', 'content': sql})
                write_ask_log(user_id, "generated_sql", sql)

                if re.match(r'^[\s]*WITH[\s]+.*?[\)][\s]*$', sql, re.DOTALL | re.IGNORECASE):
                    cte_match = re.match(r'^[\s]*WITH[\s]+(\w+)[\s]+AS[\s]+\([\s]*', sql, re.DOTALL | re.IGNORECASE)
                    if cte_match:
                        cte_name = cte_match.group(1)
                        sql = f"{sql}\nSELECT * FROM {cte_name};"
                        vn.log(f"檢測到不完整的 WITH 語句，已嘗試修正為: {sql}", "警告")

                try:
                    # 執行 SQL
                    df = vn.run_sql(sql=sql)

                    # DataFrame 容錯處理：空值、非標準類型轉字串
                    try:
                        df = df.fillna('').astype(object).map(lambda x: x if isinstance(x, (int, float, str, bool)) or x is None else str(x))
                    except Exception:
                        pass


                    # 後端分頁：若指定 page/page_size，僅回傳該頁資料至前端，但 CSV 快取仍保存完整結果
                    if not df.empty:
                        # 快取完整結果供 CSV 下載
                        try:
                            _last_result_cache[user_id] = {
                                'columns': list(df.columns),
                                'data': df.values.tolist()
                            }
                        except Exception:
                            _last_result_cache[user_id] = {}

                        # 準備回傳給前端的資料（可能是分頁）：
                        if server_paginate and page_size > 0:
                            start = max(0, (page - 1) * page_size)
                            end = min(len(df), start + page_size)
                            paged_df = df.iloc[start:end]
                            payload = {
                                'columns': list(paged_df.columns),
                                'data': paged_df.values.tolist(),
                                'pagination': {
                                    'page': page,
                                    'page_size': page_size,
                                    'total_rows': len(df)
                                }
                            }
                            vn_instance.log_queue.put({'type': 'df', 'content': payload})
                        else:
                            # 不分頁，回傳完整
                            vn_instance.log_queue.put({'type': 'df', 'content': df.to_json(orient='split', date_format='iso')})

                        # 提供可下載 CSV URL
                        vn_instance.log_queue.put({'type': 'download', 'content': {'url': '/api/ask/download_csv'}})
                    else:
                        vn_instance.log_queue.put({'type': 'message', 'content': 'SQL查詢返回空結果。'})

                except Exception as e:
                    error_message = f"SQL 執行失敗: {e}"
                    vn_instance.log_queue.put({
                        'type': 'sql_error',
                        'sql': sql,
                        'error': error_message
                    })
                    write_ask_log(user_id, "sql_execution_error", error_message)
                    df = pd.DataFrame() # 确保df在后续步骤中是空的

                
                vn_instance.log_queue.put({'type': 'info', 'content': f"SQL 執行完畢，DataFrame 行數: {len(df)}"})
                # 如果有可下載結果，附帶提示
                if hasattr(vn_instance, 'log_queue') and _last_result_cache.get(user_id):
                    vn_instance.log_queue.put({'type': 'info', 'content': '可點擊下載 CSV 檔案以取得完整結果。'})
                
                chart_code = vn.generate_plotly_code(question=question, sql=sql, df=df)
                # 後端統一輸出為標準 Plotly JSON
                plotly_spec = None
                try:
                    if isinstance(chart_code, dict) and 'data' in chart_code:
                        plotly_spec = chart_code
                    elif isinstance(chart_code, str):
                        # 尝试执行 Python 代码以获取 Plotly 图表对象
                        local_vars = {'df': df, 'px': px, 'go': go} # 提供必要的上下文
                        exec_code = chart_code.strip()
                        # 移除 import 语句，因为它们应该在文件顶部
                        exec_code = re.sub(r'^(import .*|from .* import .*)\n', '', exec_code, flags=re.MULTILINE)
                        
                        # 尝试执行代码，并期望它定义一个 'fig' 变量
                        try:
                            exec(exec_code, {'__builtins__': {}}, local_vars) # 限制内置函数
                            fig = local_vars.get('fig')
                            if fig and hasattr(fig, 'to_json'):
                                plotly_spec = json.loads(fig.to_json())
                            elif fig and hasattr(fig, 'to_dict'):
                                plotly_spec = fig.to_dict()
                        except Exception as exec_e:
                            logger.warning(f"執行 Plotly 圖表代碼失敗: {exec_e}")
                            # 如果执行失败，尝试作为纯 JSON 字符串解析
                            try:
                                s = re.sub(r'^```[a-zA-Z]*\n([\s\S]*?)\n```$', r'\1', chart_code.strip(), flags=re.M)
                                first_brace = s.find('{')
                                last_brace = s.rfind('}')
                                if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                                    s = s[first_brace:last_brace+1]
                                plotly_spec = json.loads(s)
                            except Exception as json_e:
                                logger.warning(f"解析 Plotly JSON 字符串失敗: {json_e}")
                                plotly_spec = None # 最终解析失败
                    else:
                        plotly_spec = None
                except Exception as e:
                    logger.error(f"處理 Plotly 圖表代碼時發生未知錯誤: {e}")
                    plotly_spec = None
                
                if plotly_spec and isinstance(plotly_spec, dict) and 'data' in plotly_spec:
                    vn_instance.log_queue.put({'type': 'chart', 'content': plotly_spec})
                else:
                    # 若解析失敗，仍回傳原始字串，交由前端顯示錯誤細節
                    vn_instance.log_queue.put({'type': 'chart', 'content': chart_code})
                
                # The new analysis step already provides an explanation.
                # The call to generate_explanatory_sql is redundant and has been removed.
                
                followup_questions = vn.generate_followup_questions(question=question, sql=sql, df=df, user_id=user_id)
                if followup_questions:
                    vn_instance.log_queue.put({'type': 'followup_questions', 'content': followup_questions})
                
                # This is already sent, but we ensure it's the last logical step before finally
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
                    time.sleep(0.1) # 給予前端一點時間處理最後的事件
                else:
                    logger.error("MyVanna instance has no log_queue attribute when trying to send termination signal.")

    def stream_logs():
        vanna_thread = threading.Thread(target=run_vanna_in_thread, args=(vn_instance, question, dataset_id, user_id, server_paginate, page, page_size))
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
