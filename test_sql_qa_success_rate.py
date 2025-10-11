#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
import pandas as pd
from app.core.vanna_core import get_vanna_instance, configure_vanna_for_request
from app.core.helpers import write_ask_log
from app.vanna_wrapper import MyVanna

# 加载.env文件中的环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("已成功加载.env文件中的环境变量")
except ImportError:
    print("未找到python-dotenv库，无法加载.env文件")
    # 尝试安装python-dotenv
    try:
        import subprocess
        subprocess.run(["pip", "install", "python-dotenv"], check=True)
        from dotenv import load_dotenv
        load_dotenv()
        print("已成功安装python-dotenv并加载.env文件")
    except Exception as e:
        print(f"安装python-dotenv失败: {e}")
        print("将使用系统环境变量或默认值")

# 如果.env中没有设置OLLAMA_MODEL，则使用默认值
if not os.getenv('OLLAMA_MODEL'):
    os.environ['OLLAMA_MODEL'] = 'mistral:latest'
    print("未在.env中找到OLLAMA_MODEL，使用默认值: mistral:latest")
else:
    print(f"使用.env中的OLLAMA_MODEL: {os.getenv('OLLAMA_MODEL')}")

class SQLQATester:
    def __init__(self, qa_file_path=None, ddl_file_path=None, docs_file_path=None, user_id="test_user", dataset_id="1", db_path=None):
        """初始化SQL QA测试器"""
        self.qa_file_path = qa_file_path
        self.ddl_file_path = ddl_file_path
        self.docs_file_path = docs_file_path
        self.user_id = user_id
        self.dataset_id = dataset_id
        self.db_path = db_path or f"user_data/training_data_{self.user_id}.sqlite"
        self.vanna_instance = None
        self.results = []
        self.failed_cases = []
        self.total_tested = 0
        self.success_count = 0
        
        # 创建日志目录
        self.log_dir = os.path.join("test_logs", self.user_id, self.dataset_id)
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 初始化时间戳用于日志文件命名
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.failure_log_file = os.path.join(self.log_dir, f"failed_cases_{self.timestamp}.json")
        self.results_log_file = os.path.join(self.log_dir, f"test_results_{self.timestamp}.json")
    
    def initialize_vanna(self):
        """初始化Vanna实例"""
        try:
            # 创建MyVanna实例
            self.vanna_instance = MyVanna(
                user_id=self.user_id,
            )
            
            # 配置数据集
            print(f"正在配置数据集: {self.dataset_id}")
            from app.vanna_wrapper import configure_vanna_for_request
            self.vanna_instance = configure_vanna_for_request(
                self.vanna_instance, 
                self.user_id, 
                self.dataset_id
            )
            
            # 尝试连接数据库以验证配置是否正确
            if not hasattr(self.vanna_instance, 'run_sql_is_set') or not self.vanna_instance.run_sql_is_set:
                print("无法连接到数据库")
                return False
            
            # 训练DDL语句
            print("正在加载并训练DDL语句...")
            if self.ddl_file_path:
                ddl_content = self.load_ddl()
                if ddl_content:
                    self.train_ddl(ddl_content)
                    print("DDL语句训练完成")
                else:
                    print("警告：未加载到DDL语句文件内容")
            else:
                # 如果没有提供DDL文件路径，尝试从数据库中加载
                self.load_ddl_from_db()
            
            # 训练Documentation
            print("正在加载并训练Documentation...")
            if self.docs_file_path:
                docs_content = self.load_docs()
                if docs_content:
                    self.train_docs(docs_content)
                    print("Documentation训练完成")
                else:
                    print("警告：未加载到Documentation文件内容")
            else:
                # 如果没有提供Documentation文件路径，尝试从数据库中加载
                self.load_docs_from_db()
            
            print(f"Vanna实例初始化成功，用户ID: {self.user_id}，数据集ID: {self.dataset_id}")
            return True
        except Exception as e:
            print(f"初始化Vanna实例失败: {str(e)}")
            return False

    def load_ddl_from_db(self):
        """从数据库中加载DDL语句"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 查询training_ddl表
            cursor.execute("SELECT ddl_statement FROM training_ddl")
            rows = cursor.fetchall()
            
            if rows:
                print(f"从数据库加载了 {len(rows)} 条DDL语句")
                for row in rows:
                    ddl_content = row[0]
                    self.train_ddl(ddl_content)
            else:
                print(f"数据库中未找到DDL语句")
            
            conn.close()
        except Exception as e:
            print(f"从数据库加载DDL语句失败: {str(e)}")

    def load_docs_from_db(self):
        """从数据库中加载Documentation"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 查询training_documentation表
            cursor.execute("SELECT documentation_text FROM training_documentation")
            rows = cursor.fetchall()
            
            if rows:
                print(f"从数据库加载了 {len(rows)} 条Documentation")
                for row in rows:
                    docs_content = row[0]
                    self.train_docs(docs_content)
            else:
                print(f"数据库中未找到Documentation")
            
            conn.close()
        except Exception as e:
            print(f"从数据库加载Documentation失败: {str(e)}")

    def load_qa_from_db(self, max_pairs=50):
        """从数据库中加载SQL问答配对"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 查询training_qa表，限制最大数量
            cursor.execute("SELECT question, sql_query FROM training_qa LIMIT ?", (max_pairs,))
            rows = cursor.fetchall()
            
            conn.close()
            
            if not rows:
                print(f"数据库中未找到问答配对")
                return []
            
            # 转换为测试脚本需要的格式
            qa_pairs = []
            for row in rows:
                qa_pairs.append({
                    'question': row[0],
                    'sql': row[1]
                })
            
            print(f"从数据库加载了 {len(qa_pairs)} 条问答配对")
            return qa_pairs
        except Exception as e:
            print(f"从数据库加载问答配对失败: {str(e)}")
            return []
    
    def load_ddl(self):
        """加载DDL语句"""
        try:
            if not os.path.exists(self.ddl_file_path):
                print(f"DDL文件不存在: {self.ddl_file_path}")
                return None
            
            with open(self.ddl_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"加载DDL文件失败: {str(e)}")
            return None
    
    def load_docs(self):
        """加载Documentation"""
        try:
            if not os.path.exists(self.docs_file_path):
                print(f"Documentation文件不存在: {self.docs_file_path}")
                return None
            
            with open(self.docs_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"加载Documentation文件失败: {str(e)}")
            return None
    
    def train_ddl(self, ddl_content):
        """训练Vanna实例的DDL语句"""
        try:
            # 分割多个CREATE TABLE语句
            tables = re.split(r';+', ddl_content)
            for table in tables:
                table = table.strip()
                if table and table.upper().startswith('CREATE TABLE'):
                    self.vanna_instance.add_ddl(table)
        except Exception as e:
            print(f"DDL训练失败: {str(e)}")
    
    def train_docs(self, docs_content):
        """训练Vanna实例的Documentation"""
        try:
            self.vanna_instance.add_documentation(docs_content)
        except Exception as e:
            print(f"Documentation训练失败: {str(e)}")
    
    def load_qa_pairs(self, max_pairs=50):
        """从JSON文件中加载SQL问答配对"""
        try:
            if not os.path.exists(self.qa_file_path):
                print(f"QA文件不存在: {self.qa_file_path}")
                return []
            
            with open(self.qa_file_path, 'r', encoding='utf-8') as f:
                qa_pairs = json.load(f)
            
            # 确保返回的是列表格式
            if not isinstance(qa_pairs, list):
                qa_pairs = [qa_pairs]
            
            # 限制最大配对数量
            return qa_pairs[:max_pairs]
        except Exception as e:
            print(f"加载问答配对文件失败: {str(e)}")
            return []
    
    def normalize_sql(self, sql):
        """标准化SQL语句，用于比较"""
        # 去除多余空格和换行符
        normalized = re.sub(r'\s+', ' ', sql).strip().lower()
        # 去除注释
        normalized = re.sub(r'--.*?$', '', normalized, flags=re.MULTILINE)
        normalized = re.sub(r'/\*.*?\*/', '', normalized, flags=re.DOTALL)
        # 去除可能的分号结尾
        if normalized.endswith(';'):
            normalized = normalized[:-1].strip()
        return normalized
    
    def compare_sql(self, generated_sql, original_sql):
        """比较生成的SQL与原始SQL的相似性"""
        if not generated_sql or generated_sql.startswith('-- SQL生成失败'):
            return False, "SQL生成失败"
        
        # 标准化SQL语句
        normalized_generated = self.normalize_sql(generated_sql)
        normalized_original = self.normalize_sql(original_sql)
        
        # 基本比较 - 检查关键词和主要结构
        generated_keywords = set(re.findall(r'\b\w+\b', normalized_generated))
        original_keywords = set(re.findall(r'\b\w+\b', normalized_original))
        
        # 检查是否包含SELECT关键字
        if 'select' not in generated_keywords:
            return False, "生成的内容不是有效的SQL查询"
        
        # 检查关键字重叠度
        common_keywords = generated_keywords.intersection(original_keywords)
        keyword_similarity = len(common_keywords) / max(len(original_keywords), 1)
        
        # 如果关键词重叠度高于70%，认为基本成功
        if keyword_similarity >= 0.7:
            return True, f"SQL匹配成功，关键词相似度: {keyword_similarity:.2f}"
        else:
            return False, f"SQL不匹配，关键词相似度: {keyword_similarity:.2f}"
    
    def test_single_qa(self, qa_pair, batch_num, item_num):
        """测试单个问答配对"""
        question = qa_pair.get('question', '')
        original_sql = qa_pair.get('sql', '')
        
        if not question or not original_sql:
            print(f"批次 {batch_num}, 项目 {item_num}: 问题或SQL为空，跳过")
            return False, "问题或SQL为空"
        
        try:
            print(f"\n批次 {batch_num}, 项目 {item_num}: 测试问题 - {question[:50]}...")
            
            # 记录开始时间
            start_time = time.time()
            
            # 使用问题生成SQL
            generated_sql = self.vanna_instance.generate_sql(question)
            
            # 记录结束时间
            end_time = time.time()
            execution_time = end_time - start_time
            
            # 比较生成的SQL与原始SQL
            is_success, reason = self.compare_sql(generated_sql, original_sql)
            
            # 记录结果
            result = {
                'batch': batch_num,
                'item': item_num,
                'question': question,
                'original_sql': original_sql,
                'generated_sql': generated_sql,
                'is_success': is_success,
                'reason': reason,
                'execution_time': execution_time,
                'timestamp': datetime.now().isoformat()
            }
            
            self.results.append(result)
            
            # 记录失败案例
            if not is_success:
                self.failed_cases.append(result)
                print(f"  ❌ 失败: {reason}")
            else:
                self.success_count += 1
                print(f"  ✅ 成功: {reason}")
            
            print(f"  执行时间: {execution_time:.2f}秒")
            
            # 写入日志
            write_ask_log(self.user_id, f"test_qa_batch{batch_num}_item{item_num}", json.dumps(result, ensure_ascii=False))
            
            return is_success, reason
            
        except Exception as e:
            error_msg = f"执行测试时发生错误: {str(e)}"
            print(f"  ❌ 错误: {error_msg}")
            
            # 记录错误案例
            error_result = {
                'batch': batch_num,
                'item': item_num,
                'question': question,
                'original_sql': original_sql,
                'generated_sql': None,
                'is_success': False,
                'reason': error_msg,
                'execution_time': None,
                'timestamp': datetime.now().isoformat()
            }
            
            self.results.append(error_result)
            self.failed_cases.append(error_result)
            
            # 写入日志
            write_ask_log(self.user_id, f"test_qa_error_batch{batch_num}_item{item_num}", json.dumps(error_result, ensure_ascii=False))
            
            return False, error_msg
    
    def test_in_batches(self, qa_pairs, batch_size=10):
        """分批测试问答配对"""
        total_pairs = len(qa_pairs)
        print(f"开始分批测试，共 {total_pairs} 个问答配对，每批 {batch_size} 个")
        
        # 计算总批次数
        total_batches = (total_pairs + batch_size - 1) // batch_size
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, total_pairs)
            batch_pairs = qa_pairs[start_idx:end_idx]
            
            print(f"\n=== 批次 {batch_num + 1}/{total_batches}, 测试项目 {start_idx + 1}-{end_idx}/{total_pairs} ===")
            
            for item_num, qa_pair in enumerate(batch_pairs, 1):
                self.total_tested += 1
                self.test_single_qa(qa_pair, batch_num + 1, item_num)
                
                # 每测试一个项目后保存一次结果，防止程序意外中断导致数据丢失
                self.save_results()
                
                # 添加短暂延迟，避免请求过于频繁
                if item_num < len(batch_pairs):
                    time.sleep(2)
    
    def save_results(self):
        """保存测试结果和失败案例"""
        # 保存所有结果
        with open(self.results_log_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        
        # 保存失败案例
        with open(self.failure_log_file, 'w', encoding='utf-8') as f:
            json.dump(self.failed_cases, f, ensure_ascii=False, indent=2)
    
    def generate_summary(self):
        """生成测试摘要"""
        success_rate = (self.success_count / self.total_tested * 100) if self.total_tested > 0 else 0
        
        summary = {
            'total_tested': self.total_tested,
            'success_count': self.success_count,
            'failure_count': len(self.failed_cases),
            'success_rate': success_rate,
            'start_time': self.timestamp,
            'end_time': datetime.now().strftime("%Y%m%d_%H%M%S"),
            'qa_file_path': self.qa_file_path,
            'user_id': self.user_id,
            'dataset_id': self.dataset_id
        }
        
        # 保存摘要
        summary_file = os.path.join(self.log_dir, f"test_summary_{self.timestamp}.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        # 打印摘要
        print("\n" + "="*50)
        print("SQL问答配对测试摘要")
        print("="*50)
        print(f"总测试数量: {summary['total_tested']}")
        print(f"成功数量: {summary['success_count']}")
        print(f"失败数量: {summary['failure_count']}")
        print(f"成功率: {summary['success_rate']:.2f}%")
        print(f"开始时间: {summary['start_time']}")
        print(f"结束时间: {summary['end_time']}")
        print(f"结果日志文件: {self.results_log_file}")
        print(f"失败案例文件: {self.failure_log_file}")
        print(f"摘要文件: {summary_file}")
        print("="*50)
        
        return summary
    
    def run_test(self, max_pairs=50, batch_size=10):
        """运行完整的测试流程"""
        print("开始SQL问答配对成功率测试")
        print(f"用户ID: {self.user_id}, 数据集ID: {self.dataset_id}")
        
        # 1. 初始化Vanna实例
        if not self.initialize_vanna():
            print("无法初始化Vanna实例，测试终止")
            return False
        
        # 2. 加载问答配对
        qa_pairs = []
        if self.qa_file_path:
            qa_pairs = self.load_qa_pairs(max_pairs)
        
        # 如果文件加载失败或为空，尝试从数据库加载
        if not qa_pairs:
            print("尝试从数据库加载问答配对...")
            qa_pairs = self.load_qa_from_db(max_pairs)
        
        if not qa_pairs:
            print("没有找到有效的问答配对，测试终止")
            return False
        
        # 3. 分批测试
        self.test_in_batches(qa_pairs, batch_size)
        
        # 4. 生成并保存测试摘要
        self.generate_summary()
        
        print("测试完成")
        return True

if __name__ == "__main__":
    # 配置测试参数 - 使用user1的test_1008_0931数据集
    user_id = "user1"
    dataset_id = "1"  # 使用数字ID而不是名称
    
    # 用户训练数据库路径
    db_path = os.path.join(os.path.dirname(__file__), "user_data", f"training_data_{user_id}.sqlite")
    
    # 可选：使用文件数据源（如果需要）
    qa_file_path = None  # 不使用文件，直接从数据库加载
    ddl_file_path = None  # 不使用文件，直接从数据库加载
    docs_file_path = None  # 不使用文件，直接从数据库加载
    
    max_pairs = 50  # 总共测试50则样本
    batch_size = 10  # 每批测试10则
    
    # 检查数据库是否存在
    if not os.path.exists(db_path):
        print(f"错误：用户训练数据库不存在: {db_path}")
        print("测试无法继续进行")
        exit(1)
    
    # 创建测试器实例并运行测试
    tester = SQLQATester(
        qa_file_path=qa_file_path,
        ddl_file_path=ddl_file_path,
        docs_file_path=docs_file_path,
        user_id=user_id,
        dataset_id=dataset_id,
        db_path=db_path
    )
    tester.run_test(max_pairs=max_pairs, batch_size=batch_size)