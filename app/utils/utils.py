import os
import json
import pandas as pd
from datetime import datetime

# 写入日志文件
def write_log(filename, content):
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_path = os.path.join(log_dir, filename)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {content}\n")

# 读取日志文件
def read_log(filename):
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    log_path = os.path.join(log_dir, filename)
    
    if not os.path.exists(log_path):
        return []
    
    with open(log_path, 'r', encoding='utf-8') as f:
        return f.readlines()

# 删除日志文件
def delete_log(filename):
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    log_path = os.path.join(log_dir, filename)
    
    if os.path.exists(log_path):
        os.remove(log_path)

# 格式化DataFrame为JSON
def df_to_json(df):
    if df is None or df.empty:
        return {}
    
    # 处理numpy类型，确保可以JSON序列化
    def convert_numpy_types(obj):
        import numpy as np
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj
    
    # 转换DataFrame
    result = df.to_dict(orient='records')
    for row in result:
        for key, value in row.items():
            row[key] = convert_numpy_types(value)
    
    return result

# 提取相似问题详情
def extract_similar_qa_details(qa_pairs):
    details = []
    
    for qa in qa_pairs:
        if hasattr(qa, 'question') and hasattr(qa, 'sql'):
            details.append({
                'question': qa.question,
                'sql': qa.sql
            })
        elif isinstance(qa, dict) and 'question' in qa and 'sql' in qa:
            details.append({
                'question': qa['question'],
                'sql': qa['sql']
            })
    
    return details

# 保存临时文件
def save_temp_file(content, extension='json'):
    temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'temp')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    filename = f"temp_{datetime.now().strftime('%Y%m%d%H%M%S')}.{extension}"
    filepath = os.path.join(temp_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        if extension == 'json':
            json.dump(content, f, ensure_ascii=False, indent=2)
        else:
            f.write(content)
    
    return filepath

# 生成唯一ID
def generate_unique_id():
    import uuid
    return str(uuid.uuid4())

# 清理临时文件
def cleanup_temp_files(max_age_hours=24):
    import glob
    temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'temp')
    if not os.path.exists(temp_dir):
        return
    
    current_time = datetime.now()
    for file_path in glob.glob(os.path.join(temp_dir, 'temp_*')):
        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        if (current_time - file_time).total_seconds() > max_age_hours * 3600:
            try:
                os.remove(file_path)
            except:
                pass