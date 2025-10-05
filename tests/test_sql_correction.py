import unittest
import os
import json
import sqlite3
from unittest.mock import patch, MagicMock, mock_open
from multi_user_app import app, users, get_vanna_instance, init_training_db
import pandas as pd

class SQLCorrectionTestCase(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_key'
        self.app = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

        # 创建用户数据目录（如果不存在）
        self.user_data_dir = os.path.join(os.getcwd(), 'user_data')
        os.makedirs(self.user_data_dir, exist_ok=True)

        # 为测试创建独立的测试用户数据目录
        self.test_user_data_dir = os.path.join(self.user_data_dir, 'test_data')
        os.makedirs(self.test_user_data_dir, exist_ok=True)

        # 准备测试数据库路径
        self.db_path = os.path.join(self.test_user_data_dir, 'training_data_test_user.sqlite')

        # 创建测试用户
        users['test_user'] = 'test_password'

        # 模拟数据库连接路径
        self.original_os_path_join = os.path.join
        os.path.join = self._mock_os_path_join

        # 初始化测试用户的训练数据库
        with patch('multi_user_app.os.path.join', side_effect=self._mock_os_path_join):
            init_training_db('test_user')
        
        # 创建 correction_rules 表（如果不存在）
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS correction_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incorrect_name TEXT,
                correct_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            conn.commit()
            
        # 登录测试用户 - 使用session_transaction来确保session状态在测试中保持
        with self.app.session_transaction() as sess:
            sess['username'] = 'test_user'

    def _mock_os_path_join(self, *args):
        """模拟os.path.join，将训练数据指向测试目录"""
        # 匹配实际应用中使用的路径格式
        if len(args) >= 2 and args[-2] == 'user_data' and args[-1].startswith('training_data_') and args[-1].endswith('.sqlite'):
            return self.db_path
        # 保留原来的匹配逻辑以保持兼容性
        if len(args) >= 3 and 'user_data' in args and 'training_data_test_user.sqlite' in args:
            return self.db_path
        return self.original_os_path_join(*args)

    def tearDown(self):
        self.app_context.pop()
        # 恢复原始的os.path.join函数
        os.path.join = self.original_os_path_join
        # 清理测试数据
        if hasattr(self, 'test_user_data_dir') and os.path.exists(self.test_user_data_dir):
            try:
                for f in os.listdir(self.test_user_data_dir):
                    file_path = os.path.join(self.test_user_data_dir, f)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                os.rmdir(self.test_user_data_dir)
            except Exception as e:
                print(f"Warning: Failed to clean up test data: {e}")
        # 移除测试用户
        if 'test_user' in users:
            del users['test_user']

    def test_supermarket_analysis_table_name_correction(self):
        """测试数据表名称纠正功能"""
        # 首先添加一个纠正规则到数据库
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO correction_rules (incorrect_name, correct_name) VALUES (?, ?)", 
                          ('SuperMarket_Analysis', 'SuperMarketAnalysis'))
            conn.commit()

        # 模拟Vanna实例的generate_sql方法返回包含错误表名的SQL
        with patch('multi_user_app.get_vanna_instance') as mock_get_vn, \
             patch('multi_user_app.os.path.join', side_effect=self._mock_os_path_join), \
             patch('multi_user_app.os.getcwd', return_value=self.user_data_dir):
            mock_vn = MagicMock()
            # 模拟返回包含错误表名的SQL
            mock_vn.generate_sql.return_value = [MagicMock(sql="SELECT * FROM SuperMarket_Analysis;")]
            # 模拟run_sql方法返回一个可以序列化的DataFrame
            mock_vn.run_sql.return_value = pd.DataFrame()
            mock_vn.run_sql_is_set = True
            mock_get_vn.return_value = mock_vn

            # 调用/api/ask接口
            response = self.app.post('/api/ask', 
                                     data=json.dumps({'question': 'Test question', 'edited_sql': ''}),
                                     content_type='application/json')
            
            # 验证响应包含纠正后的表名，并且原始表名只出现在日志部分（而不是最终SQL结果中）
            response_data = response.data.decode('utf-8')
            self.assertIn('SuperMarketAnalysis', response_data)
            # 检查最终SQL结果中是否不包含原始表名
            self.assertNotIn('sql": "SELECT * FROM SuperMarket_Analysis', response_data)

    def test_correction_rules_api(self):
        """测试纠正规则API的CRUD操作"""
        # 模拟数据库路径
        with patch('multi_user_app.os.path.join', side_effect=self._mock_os_path_join):
            # 添加纠正规则
            add_response = self.app.post('/api/correction_rules',
                                        data=json.dumps({'incorrect_name': 'wrong_table', 'correct_name': 'right_table'}),
                                        content_type='application/json')
            self.assertEqual(add_response.status_code, 201)
            add_result = json.loads(add_response.data)
            self.assertEqual(add_result['status'], 'success')
            rule_id = add_result['id']

            # 获取所有纠正规则
            get_response = self.app.get('/api/correction_rules')
            # 打印错误信息以帮助调试
            print(f"GET Response Status Code: {get_response.status_code}")
            print(f"GET Response Data: {get_response.data}")
            self.assertEqual(get_response.status_code, 200)
            get_result = json.loads(get_response.data)
            self.assertEqual(get_result['status'], 'success')
            self.assertEqual(len(get_result['rules']), 1)
            self.assertEqual(get_result['rules'][0]['incorrect_name'], 'wrong_table')
            self.assertEqual(get_result['rules'][0]['correct_name'], 'right_table')

            # 删除纠正规则
            delete_response = self.app.delete(f'/api/correction_rules/{rule_id}')
            self.assertEqual(delete_response.status_code, 200)
            delete_result = json.loads(delete_response.data)
            self.assertEqual(delete_result['status'], 'success')

            # 验证规则已删除
            get_response_after_delete = self.app.get('/api/correction_rules')
            get_result_after_delete = json.loads(get_response_after_delete.data)
            self.assertEqual(len(get_result_after_delete['rules']), 0)

    def test_apply_correction_rules_in_sql_generation(self):
        """测试在SQL生成过程中应用纠正规则"""
        # 首先添加一个纠正规则到数据库
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO correction_rules (incorrect_name, correct_name) VALUES (?, ?)", 
                          ('incorrect_table', 'correct_table'))
            conn.commit()

        # 模拟Vanna实例的generate_sql方法返回包含错误表名的SQL
        with patch('multi_user_app.get_vanna_instance') as mock_get_vn, \
             patch('multi_user_app.os.path.join', side_effect=self._mock_os_path_join), \
             patch('multi_user_app.os.getcwd', return_value=self.user_data_dir):
            mock_vn = MagicMock()
            # 模拟返回包含我们添加规则的错误表名的SQL
            mock_vn.generate_sql.return_value = [MagicMock(sql="SELECT * FROM incorrect_table;")]
            # 模拟run_sql方法返回一个可以序列化的DataFrame
            mock_vn.run_sql.return_value = pd.DataFrame()
            mock_vn.run_sql_is_set = True
            mock_get_vn.return_value = mock_vn

            # 调用/api/ask接口
            response = self.app.post('/api/ask', 
                                     data=json.dumps({'question': 'Test question', 'edited_sql': ''}),
                                     content_type='application/json')
            
            # 验证响应包含纠正后的表名，并且原始表名只出现在日志部分（而不是最终SQL结果中）
            response_data = response.data.decode('utf-8')
            self.assertIn('correct_table', response_data)
            # 检查最终SQL结果中是否不包含原始表名
            self.assertNotIn('sql": "SELECT * FROM incorrect_table', response_data)

    def test_correction_rules_case_insensitivity(self):
        """测试纠正规则的大小写不敏感特性"""
        # 首先添加一个纠正规则到数据库
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO correction_rules (incorrect_name, correct_name) VALUES (?, ?)", 
                          ('CASE_SENSITIVE', 'case_corrected'))
            conn.commit()

        # 模拟Vanna实例的generate_sql方法返回包含不同大小写错误表名的SQL
        with patch('multi_user_app.get_vanna_instance') as mock_get_vn, \
             patch('multi_user_app.os.path.join', side_effect=self._mock_os_path_join), \
             patch('multi_user_app.os.getcwd', return_value=self.user_data_dir):
            mock_vn = MagicMock()
            # 模拟返回包含不同大小写错误表名的SQL
            mock_vn.generate_sql.return_value = [MagicMock(sql="SELECT * FROM case_sensitive;")]
            # 模拟run_sql方法返回一个可以序列化的DataFrame
            mock_vn.run_sql.return_value = pd.DataFrame()
            mock_vn.run_sql_is_set = True
            mock_get_vn.return_value = mock_vn

            # 调用/api/ask接口
            response = self.app.post('/api/ask', 
                                     data=json.dumps({'question': 'Test question', 'edited_sql': ''}),
                                     content_type='application/json')
            
            # 验证响应包含纠正后的表名
            response_data = response.data.decode('utf-8')
            self.assertIn('case_corrected', response_data)

    def test_word_boundary_in_correction_rules(self):
        """测试纠正规则中的单词边界匹配"""
        # 首先添加纠正规则
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO correction_rules (incorrect_name, correct_name) VALUES (?, ?)", 
                          ('test', 'corrected_test'))
            conn.commit()

        # 模拟Vanna实例的generate_sql方法返回包含部分匹配的SQL
        with patch('multi_user_app.get_vanna_instance') as mock_get_vn, \
             patch('multi_user_app.os.path.join', side_effect=self._mock_os_path_join), \
             patch('multi_user_app.os.getcwd', return_value=self.user_data_dir):
            mock_vn = MagicMock()
            # 模拟返回包含部分匹配的SQL，但不应该被纠正
            mock_vn.generate_sql.return_value = [MagicMock(sql="SELECT * FROM test_table;")]
            # 模拟run_sql方法返回一个可以序列化的DataFrame
            mock_vn.run_sql.return_value = pd.DataFrame()
            mock_vn.run_sql_is_set = True
            mock_get_vn.return_value = mock_vn

            # 调用/api/ask接口
            response = self.app.post('/api/ask', 
                                     data=json.dumps({'question': 'Test question', 'edited_sql': ''}),
                                     content_type='application/json')
            
            # 验证SQL没有被纠正，因为'test'不是一个完整的单词
            response_data = response.data.decode('utf-8')
            self.assertIn('test_table', response_data)
            self.assertNotIn('corrected_test_table', response_data)

if __name__ == '__main__':
    unittest.main()