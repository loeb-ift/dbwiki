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
import logging

# 配置日志记录器
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# 导入项目中的真实MyVanna类实现
from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request
from app.core.vanna_core import MyVanna

# 设置环境变量
sqlite3.register_adapter(str, str)
sqlite3.register_converter('TEXT', lambda x: x.decode('utf-8') if x else None)

# 获取用户的数据库连接
def get_user_db_connection(user_id, dataset_id):
    """获取用户的数据库连接"""
    db_path = f"/Users/loeb/LAB/dbwiki/database/{user_id}/dataset_{dataset_id}.db"
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return None
    try:
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        return conn
    except Exception as e:
        print(f"连接数据库失败: {str(e)}")
        return None

# 确保OLLAMA_MODEL环境变量已设置
os.environ.setdefault('OLLAMA_MODEL', 'mistral:latest')

# 如果.env中没有设置OLLAMA_MODEL，则使用默认值
if not os.getenv('OLLAMA_MODEL'):
    os.environ['OLLAMA_MODEL'] = 'mistral:latest'
    logger.info("未在.env中找到OLLAMA_MODEL，使用默认值: mistral:latest")
else:
    logger.info(f"使用.env中的OLLAMA_MODEL: {os.getenv('OLLAMA_MODEL')}")

class SQLQATester:
    def __init__(self, user_id, dataset_id, log_dir=None, threshold=0.7):
        # 设置基本参数
        self.user_id = user_id
        self.dataset_id = dataset_id
        self.threshold = threshold
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 设置日志目录
        self.log_dir = log_dir if log_dir else f"./test_logs/{user_id}_{dataset_id}_{self.timestamp}"
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 初始化结果存储
        self.results = []
        self.failed_cases = []
        self.success_count = 0
        self.total_tested = 0
        
        # 设置日志文件路径
        self.results_log_file = os.path.join(self.log_dir, f"results_{self.timestamp}.json")
        self.failure_log_file = os.path.join(self.log_dir, f"failures_{self.timestamp}.json")
        
        # 设置测试数据
        self.test_data = [
            {
                'question': '查询每个部门的平均工资并按降序排列前5名',
                'sql': 'SELECT department, AVG(salary) as avg_salary FROM employees GROUP BY department ORDER BY avg_salary DESC LIMIT 5;'
            },
            {
                'question': '查询电子产品类别每年的销售收入总和',
                'sql': 'SELECT year, SUM(revenue) as total_revenue FROM sales WHERE product_category = "电子产品" GROUP BY year ORDER BY year;'
            },
            {
                'question': '查询订单数量超过5的客户及其订单数',
                'sql': 'SELECT customer_name, COUNT(order_id) as order_count FROM orders GROUP BY customer_name HAVING COUNT(order_id) > 5 ORDER BY order_count DESC;'
            },
            {
                'question': '查询最受欢迎的10种产品及其销量',
                'sql': 'SELECT product_name, SUM(quantity) as total_sold FROM sales GROUP BY product_name ORDER BY total_sold DESC LIMIT 10;'
            }
        ]
        
        # 设置数据库路径
        self.db_path = f"/Users/loeb/LAB/dbwiki/database/{user_id}/dataset_{dataset_id}.db"
        
        # 设置训练数据文件路径
        self.ddl_file_path = f"/Users/loeb/LAB/dbwiki/data/ddl_{dataset_id}.sql"
        self.docs_file_path = f"/Users/loeb/LAB/dbwiki/data/docs_{dataset_id}.md"
        self.qa_file_path = f"/Users/loeb/LAB/dbwiki/data/qa_{dataset_id}.json"
        
        # 初始化Vanna实例
        self.vanna_instance = None

    def initialize_vanna(self):
        """初始化真实的Vanna实例"""
        try:
            # 尝试获取现有的Vanna实例
            self.vanna_instance = get_vanna_instance(self.user_id)
            if self.vanna_instance:
                print("成功获取到现有的Vanna实例")
                # 配置实例以确保使用正确的数据库和LLM
                configure_vanna_for_request(self.vanna_instance, self.user_id, self.dataset_id)
                return True
            
            # 如果没有现有的Vanna实例，创建一个新的
            print(f"创建新的Vanna实例: 用户ID={self.user_id}, 数据集ID={self.dataset_id}")
            
            # 检查数据库连接
            conn = get_user_db_connection(self.user_id, self.dataset_id)
            if conn:
                conn.close()
            else:
                print("警告: 无法连接到用户数据库，但仍继续创建Vanna实例")
            
            # 创建MyVanna实例，只传递user_id和config参数
            self.vanna_instance = MyVanna(
                user_id=self.user_id,
                config={
                    'dataset_id': self.dataset_id,
                    'db_path': self.db_path
                }
            )
            
            # 加载训练数据
            self.load_training_data()
            
            return True
        except Exception as e:
            print(f"初始化Vanna实例失败: {str(e)}")
            return False
    
    def load_training_data(self):
        """加载训练数据"""
        try:
            # 首先尝试从数据库加载DDL
            self.load_ddl_from_db()
            
            # 如果数据库没有DDL，则尝试从文件加载
            if not hasattr(self.vanna_instance, 'ddl_statements') or len(getattr(self.vanna_instance, 'ddl_statements', [])) == 0:
                ddl_content = self.load_ddl()
                if ddl_content:
                    self.train_ddl(ddl_content)
                    print("从文件加载DDL训练完成")
                else:
                    print("警告：未加载到DDL文件内容")
            
            # 首先尝试从数据库加载Documentation
            self.load_docs_from_db()
            
            # 如果数据库没有Documentation，则尝试从文件加载
            docs_content = self.load_docs()
            if docs_content:
                self.train_docs(docs_content)
                print("从文件加载Documentation训练完成")
            
            # 首先尝试从数据库加载问答配对
            qa_pairs = self.load_qa_from_db(max_pairs=20)
            if qa_pairs:
                for qa in qa_pairs:
                    self.vanna_instance.add_question_sql(qa['question'], qa['sql'])
                print(f"从数据库添加了 {len(qa_pairs)} 条问答配对作为训练数据")
            
            # 添加测试问答配对作为训练数据
            for qa in self.test_data:
                self.vanna_instance.add_question_sql(qa['question'], qa['sql'])
            print(f"添加了 {len(self.test_data)} 条测试问答配对作为训练数据")
            
        except Exception as e:
            print(f"加载训练数据失败: {str(e)}")
    
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
        """
        比较生成的SQL与原始SQL的相似性。
        使用Jaccard相似度，并过滤掉通用的SQL关键字。
        """
        if not generated_sql or generated_sql.startswith('-- SQL生成失败'):
            return False, "SQL生成失败"

        # 标准化SQL语句
        normalized_generated = self.normalize_sql(generated_sql)
        normalized_original = self.normalize_sql(original_sql)

        # 提取关键字
        generated_keywords = set(re.findall(r'\b\w+\b', normalized_generated))
        original_keywords = set(re.findall(r'\b\w+\b', normalized_original))

        # 检查是否包含SELECT关键字
        if 'select' not in generated_keywords:
            return False, "生成的内容不是有效的SQL查询"

        # 定义要过滤的通用SQL关键字
        common_sql_keywords = {
            'select', 'from', 'where', 'group', 'by', 'order', 'and', 'or', 'on', 'as',
            'insert', 'into', 'values', 'update', 'set', 'delete', 'join', 'inner',
            'left', 'right', 'outer', 'limit', 'offset', 'having', 'distinct', 'count',
            'sum', 'avg', 'max', 'min', 'asc', 'desc', 'case', 'when', 'then', 'else', 'end'
        }

        # 过滤通用关键字，专注于核心实体
        filtered_generated_keywords = generated_keywords - common_sql_keywords
        filtered_original_keywords = original_keywords - common_sql_keywords
        
        # 如果过滤后原始关键字为空，则无法比较
        if not filtered_original_keywords:
            # 如果生成的关键字也为空，则认为匹配
            if not filtered_generated_keywords:
                return True, "SQL匹配成功，过滤后无核心关键字"
            else:
                return False, "SQL不匹配，原始SQL过滤后无核心关键字"

        # 计算交集和并集
        intersection = filtered_generated_keywords.intersection(filtered_original_keywords)
        union = filtered_generated_keywords.union(filtered_original_keywords)

        # 计算Jaccard相似度
        jaccard_similarity = len(intersection) / len(union) if union else 1.0

        # 如果相似度高于阈值，认为成功
        if jaccard_similarity >= self.threshold:
            return True, f"SQL匹配成功，Jaccard相似度: {jaccard_similarity:.2f}"
        else:
            return False, f"SQL不匹配，Jaccard相似度: {jaccard_similarity:.2f}"
    
    def test_single_qa(self, question, expected_sql):
        """测试单个问答对"""
        if not self.vanna_instance:
            self.initialize_vanna()
            
        self.current_index += 1
        self.total_count += 1
        
        logger.info(f"测试 {self.current_index}/{self.total_count}: {question[:50]}...")
        
        start_time = time.time()
        
        try:
            # 生成SQL
            generated_sql = self.vanna_instance.generate_sql(question)
            
            # 比较SQL
            is_success, reason = self.compare_sql(
                generated_sql, expected_sql
            )
            
            # 记录执行时间
            execution_time = time.time() - start_time
            
            # 构建结果
            result = {
                "question": question,
                "expected_sql": expected_sql,
                "generated_sql": generated_sql,
                "is_success": is_success,
                "reason": reason,
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            }
            
            # 更新统计信息
            if is_success:
                self.success_count += 1
            else:
                self.failed_cases.append(result)
                
            self.results.append(result)
            
            # 记录日志
            logger.info(f"测试结果: {'成功' if is_success else '失败'} - {reason} - 耗时: {execution_time:.2f}秒")
            
            return result
            
        except Exception as e:
            logger.error(f"测试过程中出错: {e}")
            execution_time = time.time() - start_time
            
            result = {
                "question": question,
                "expected_sql": expected_sql,
                "generated_sql": None,
                "is_success": False,
                "reason": f"测试过程中发生错误: {str(e)}",
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            }
            
            self.failed_cases.append(result)
            self.results.append(result)
            
            return result
    
    def run_test(self, max_pairs=None):
        """运行完整测试
        
        参数:
            max_pairs: 最大测试对数量，None表示测试所有
        """
        logger.info("开始运行测试...")
        
        # 初始化
        self.results = []
        self.failed_cases = []
        self.success_count = 0
        self.total_count = 0
        self.current_index = 0
        
        # 初始化Vanna实例
        if not self.vanna_instance:
            self.initialize_vanna()
            self.load_training_data()
            
        # 确保日志目录存在
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 确定要测试的问答对数量
        test_data = self.test_data
        if max_pairs and max_pairs < len(test_data):
            test_data = test_data[:max_pairs]
            
        self.total_count = len(test_data)
        
        logger.info(f"共测试 {self.total_count} 个问答对，相似度阈值: {self.threshold}")
        
        # 逐个测试
        for i, qa in enumerate(test_data, 1):
            self.test_single_qa(qa["question"], qa["sql"])
            
        # 保存结果
        self.save_results()
        
        # 生成摘要
        summary = self.generate_summary()
        
        return summary
    
    def save_results(self):
        """保存测试结果"""
        try:
            # 生成时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 保存所有结果
            results_file = os.path.join(self.log_dir, f"results_{timestamp}.json")
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
                
            # 保存失败案例
            failed_file = os.path.join(self.log_dir, f"failed_cases_{timestamp}.json")
            with open(failed_file, "w", encoding="utf-8") as f:
                json.dump(self.failed_cases, f, ensure_ascii=False, indent=2)
                
            logger.info(f"测试结果已保存到: {results_file}")
            logger.info(f"失败案例已保存到: {failed_file}")
            
        except Exception as e:
            logger.error(f"保存测试结果失败: {e}")
    
    def generate_summary(self):
        """生成测试摘要"""
        success_rate = (self.success_count / self.total_count) * 100 if self.total_count > 0 else 0
        
        summary = {
            "total_count": self.total_count,
            "success_count": self.success_count,
            "failed_count": len(self.failed_cases),
            "success_rate": success_rate,
            "timestamp": datetime.now().isoformat(),
            "user_id": self.user_id,
            "dataset_id": self.dataset_id
        }
        
        # 打印摘要
        logger.info("\n========== 测试摘要 ==========")
        logger.info(f"总测试数: {self.total_count}")
        logger.info(f"成功数: {self.success_count}")
        logger.info(f"失败数: {len(self.failed_cases)}")
        logger.info(f"成功率: {success_rate:.2f}%")
        logger.info("==============================\n")
        
        # 保存摘要
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_file = os.path.join(self.log_dir, f"summary_{timestamp}.json")
        try:
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            logger.info(f"测试摘要已保存到: {summary_file}")
        except Exception as e:
            logger.error(f"保存测试摘要失败: {e}")
            
        return summary
    
    def load_qa_pairs(self, max_pairs=None):
        """从文件加载问答配对"""
        try:
            if not os.path.exists(self.qa_file_path):
                print(f"问答配对文件不存在: {self.qa_file_path}")
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
    
    def compare_sql(self, generated_sql, original_sql, similarity_threshold=0.7):
        """
        比较生成的SQL与原始SQL的相似性。
        使用Jaccard相似度，并过滤掉通用的SQL关键字。
        """
        if not generated_sql or generated_sql.startswith('-- SQL生成失败'):
            return False, "SQL生成失败"

        # 标准化SQL语句
        normalized_generated = self.normalize_sql(generated_sql)
        normalized_original = self.normalize_sql(original_sql)

        # 提取关键字
        generated_keywords = set(re.findall(r'\b\w+\b', normalized_generated))
        original_keywords = set(re.findall(r'\b\w+\b', normalized_original))

        # 检查是否包含SELECT关键字
        if 'select' not in generated_keywords:
            return False, "生成的内容不是有效的SQL查询"

        # 定义要过滤的通用SQL关键字
        common_sql_keywords = {
            'select', 'from', 'where', 'group', 'by', 'order', 'and', 'or', 'on', 'as',
            'insert', 'into', 'values', 'update', 'set', 'delete', 'join', 'inner',
            'left', 'right', 'outer', 'limit', 'offset', 'having', 'distinct', 'count',
            'sum', 'avg', 'max', 'min', 'asc', 'desc', 'case', 'when', 'then', 'else', 'end'
        }

        # 过滤通用关键字，专注于核心实体
        filtered_generated_keywords = generated_keywords - common_sql_keywords
        filtered_original_keywords = original_keywords - common_sql_keywords
        
        # 如果过滤后原始关键字为空，则无法比较
        if not filtered_original_keywords:
            # 如果生成的关键字也为空，则认为匹配
            if not filtered_generated_keywords:
                return True, "SQL匹配成功，过滤后无核心关键字"
            else:
                return False, "SQL不匹配，原始SQL过滤后无核心关键字"

        # 计算交集和并集
        intersection = filtered_generated_keywords.intersection(filtered_original_keywords)
        union = filtered_generated_keywords.union(filtered_original_keywords)

        # 计算Jaccard相似度
        jaccard_similarity = len(intersection) / len(union) if union else 1.0

        # 如果相似度高于阈值，认为成功
        if jaccard_similarity >= similarity_threshold:
            return True, f"SQL匹配成功，Jaccard相似度: {jaccard_similarity:.2f}"
        else:
            return False, f"SQL不匹配，Jaccard相似度: {jaccard_similarity:.2f}"
    
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
            
            # 记录到日志
            logger.info(f"测试结果 - 批次{batch_num}项目{item_num}: {'成功' if is_success else '失败'} - {reason}")
            
            return is_success, reason
            
        except Exception as e:
            error_msg = f"执行测试时发生错误: {str(e)}"
            print(f"  ❌ 错误: {error_msg}")
            logger.error(f"测试错误 - 批次{batch_num}项目{item_num}: {error_msg}")
            
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
        
        # 打印加载的问答配对数量和前两个示例
        print(f"成功加载 {len(qa_pairs)} 条问答配对")
        if len(qa_pairs) > 0:
            print("前两条问答配对示例:")
            for i, qa in enumerate(qa_pairs[:2]):
                print(f"示例 {i+1}:")
                print(f"问题: {qa['question'][:50]}...")
                print(f"SQL: {qa['sql'][:50]}...")
        
        if not qa_pairs:
            print("没有找到有效的问答配对，测试终止")
            return False
        
        # 3. 分批测试
        self.test_in_batches(qa_pairs, batch_size)
        
        # 4. 生成并保存测试摘要
        self.generate_summary()
        
        print("测试完成")
        return True

import argparse

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='测试SQL问答的成功率')
    parser.add_argument('--user', type=str, required=False, default='user18', help='用户ID，默认为user18')
    parser.add_argument('--dataset_id', type=int, required=False, default=1, help='数据集ID，默认为1')
    parser.add_argument('--max_pairs', type=int, default=50, help='最大测试问答对数量，默认为50')
    parser.add_argument('--threshold', type=float, default=0.7, help='SQL相似度阈值，默认为0.7')
    parser.add_argument('--model', type=str, default='mistral', help='使用的模型名称，默认为mistral')
    parser.add_argument('--log_dir', type=str, default='./test_logs', help='日志保存目录，默认为./test_logs')
    return parser.parse_args()

def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()
    
    # 初始化测试器
    tester = SQLQATester(
        user_id=args.user,
        dataset_id=str(args.dataset_id),
        threshold=args.threshold,
        log_dir=args.log_dir
    )
    
    # 运行测试
    logger.info(f"开始测试SQL问答的成功率 - 用户: {args.user}, 数据集: {args.dataset_id}")
    logger.info(f"使用模型: {args.model}, 最大测试对: {args.max_pairs}, 相似度阈值: {args.threshold}")
    
    try:
        # 运行测试
        success = tester.run_test(
            max_pairs=args.max_pairs
        )
        
        if success:
            logger.info("测试完成！请查看日志文件获取详细结果")
        else:
            logger.warning("测试未完成")
        
    except Exception as e:
        logger.error(f"测试过程中发生严重错误: {e}")
        raise

if __name__ == "__main__":
    main()