import unittest
import json
import os
import tempfile
from unittest import mock
from flask import Flask

# 假設 app.py 在專案根目錄，且 connect_database 函數可以被導入
# 為了測試，我們需要模擬 app 和 vn 物件
from app import app, connect_database, vn, init_training_db

class TestDatabaseConnection(unittest.TestCase):

    def setUp(self):
        """
        在每個測試方法執行前設置環境。
        """
        app.config['TESTING'] = True
        self.app = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

        # 模擬 Vanna 實例的屬性
        self.mock_vn_connect_to_sqlite = mock.MagicMock()
        self.mock_vn_get_ddl = mock.MagicMock(return_value=["CREATE TABLE test_table (id INTEGER);"])
        self.mock_vn_connect_to_postgresql = mock.MagicMock()
        self.mock_vn_connect_to_mysql = mock.MagicMock()
        self.mock_vn_connect_to_mssql = mock.MagicMock()
        self.mock_vn_run_sql = mock.MagicMock()

        vn.connect_to_sqlite = self.mock_vn_connect_to_sqlite
        vn.get_ddl = self.mock_vn_get_ddl
        vn.connect_to_postgresql = self.mock_vn_connect_to_postgresql
        vn.connect_to_mysql = self.mock_vn_connect_to_mysql
        vn.connect_to_mssql = self.mock_vn_connect_to_mssql
        vn.run_sql = self.mock_vn_run_sql
        vn.run_sql_is_set = False # 預設為 False

        # 創建一個臨時的 .env 文件用於測試
        self.env_file = ".env.test"
        with open(self.env_file, "w") as f:
            f.write("DB_TYPE=sqlite\n")
            f.write("DB_PATH=test.db\n")
        os.environ['TRAINING_DATA_DB_PATH'] = 'test_training_data.sqlite'
        init_training_db() # 確保訓練資料庫被初始化

    def tearDown(self):
        """
        在每個測試方法執行後清理環境。
        """
        self.app_context.pop()
        if os.path.exists(self.env_file):
            os.remove(self.env_file)
        if os.path.exists('test.db'):
            os.remove('test.db')
        if os.path.exists('test_training_data.sqlite'):
            os.remove('test_training_data.sqlite')
        # 清理任何臨時文件或資料庫
        if hasattr(app.config, 'TEMP_DB_PATH') and os.path.exists(app.config['TEMP_DB_PATH']):
            os.remove(app.config['TEMP_DB_PATH'])

    def test_connect_sqlite_success(self):
        """
        測試成功連接 SQLite 資料庫。
        """
        with self.app.post('/api/connect', json={'type': 'sqlite', 'database': 'test.db'}) as response:
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('DDL extracted', data['message'])
            self.mock_vn_connect_to_sqlite.assert_called_once_with('test.db')
            self.mock_vn_get_ddl.assert_called_once()

    def test_connect_sqlite_file_not_found(self):
        """
        測試連接不存在的 SQLite 資料庫文件。
        """
        with self.app.post('/api/connect', json={'type': 'sqlite', 'database': 'non_existent.db'}) as response:
            self.assertEqual(response.status_code, 500) # 這裡應該是 500，因為底層會拋出異常
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'error')
            self.assertIn('unable to open database file', data['message']) # 檢查錯誤訊息

    @mock.patch('app.pd')
    @mock.patch('app.create_engine')
    @mock.patch('app.tempfile')
    @mock.patch('app.secure_filename', side_effect=lambda x: x)
    def test_connect_csv_upload_success(self, mock_secure_filename, mock_tempfile, mock_create_engine, mock_pd):
        """
        測試成功上傳 CSV 文件並轉換為 SQLite 資料庫。
        """
        # 模擬文件上傳
        mock_file = mock.MagicMock()
        mock_file.filename = 'test.csv'
        mock_file.read.return_value = b'col1,col2\n1,a\n2,b'

        # 模擬 tempfile
        mock_tempfile.gettempdir.return_value = '/tmp'
        mock_tempfile.NamedTemporaryFile.return_value.name = '/tmp/temp_db.sqlite'
        mock_tempfile.NamedTemporaryFile.return_value.close.return_value = None

        # 模擬 pandas
        mock_df = mock.MagicMock()
        mock_pd.read_csv.return_value = mock_df
        mock_pd.io.sql.get_schema.return_value = "CREATE TABLE test_csv (col1 INTEGER, col2 TEXT);"

        # 模擬 SQLAlchemy engine
        mock_engine = mock.MagicMock()
        mock_create_engine.return_value = mock_engine

        with self.app.post('/api/connect', data={'type': 'csv', 'database_file': mock_file}, content_type='multipart/form-data') as response:
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('CSV data loaded into in-memory database', data['message'])
            self.assertEqual(data['ddl'], "CREATE TABLE test_csv (col1 INTEGER, col2 TEXT);")
            mock_file.save.assert_called_once_with('/tmp/test.csv')
            mock_pd.read_csv.assert_called_once_with('/tmp/test.csv')
            mock_df.to_sql.assert_called_once_with('test_csv', mock_engine, index=False, if_exists='replace')
            self.assertTrue(vn.run_sql_is_set)
            self.assertEqual(vn.engine, mock_engine)

    def test_connect_unsupported_db_type(self):
        """
        測試連接不支援的資料庫類型。
        """
        with self.app.post('/api/connect', json={'type': 'unsupported', 'database': 'some_db'}) as response:
            self.assertEqual(response.status_code, 400)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'error')
            self.assertIn('Unsupported database type: unsupported', data['message'])

    def test_get_db_config_success(self):
        """
        測試成功獲取資料庫配置。
        """
        with self.app.get('/api/get_db_config') as response:
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['active_type'], 'sqlite')
            self.assertIn('sqlite', data['configs'])
            self.assertEqual(data['configs']['sqlite']['type'], 'sqlite')
            self.assertEqual(data['configs']['sqlite']['path'], 'test.db')

    def test_get_db_config_no_env_file(self):
        """
        測試 .env 文件不存在時獲取資料庫配置。
        """
        os.remove(self.env_file) # 刪除測試用的 .env 文件
        with self.app.get('/api/get_db_config') as response:
            self.assertEqual(response.status_code, 404)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'error')
            self.assertIn('.env file not found', data['message'])

    def test_connect_postgresql_success(self):
        """
        測試成功連接 PostgreSQL 資料庫。
        """
        with self.app.post('/api/connect', json={'type': 'postgresql', 'host': 'localhost', 'port': '5432', 'user': 'user', 'password': 'password', 'database': 'testdb'}) as response:
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('DDL extracted', data['message'])
            self.mock_vn_connect_to_postgresql.assert_called_once_with(host='localhost', port='5432', user='user', password='password', dbname='testdb')
            self.mock_vn_get_ddl.assert_called_once()

    def test_connect_mysql_success(self):
        """
        測試成功連接 MySQL 資料庫。
        """
        with self.app.post('/api/connect', json={'type': 'mysql', 'host': 'localhost', 'port': '3306', 'user': 'user', 'password': 'password', 'database': 'testdb'}) as response:
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('DDL extracted', data['message'])
            self.mock_vn_connect_to_mysql.assert_called_once_with(host='localhost', port='3306', user='user', password='password', dbname='testdb')
            self.mock_vn_get_ddl.assert_called_once()

    def test_connect_mssql_success(self):
        """
        測試成功連接 MSSQL 資料庫。
        """
        with self.app.post('/api/connect', json={'type': 'mssql', 'host': 'localhost', 'port': '1433', 'user': 'user', 'password': 'password', 'database': 'testdb'}) as response:
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('DDL extracted', data['message'])
            self.mock_vn_connect_to_mssql.assert_called_once_with(host='localhost', port='1433', user='user', password='password', dbname='testdb')
            self.mock_vn_get_ddl.assert_called_once()

    def test_connect_postgresql_failure(self):
        """
        測試連接 PostgreSQL 資料庫失敗。
        """
        self.mock_vn_connect_to_postgresql.side_effect = Exception("PostgreSQL connection error")
        with self.app.post('/api/connect', json={'type': 'postgresql', 'host': 'localhost', 'port': '5432', 'user': 'user', 'password': 'password', 'database': 'testdb'}) as response:
            self.assertEqual(response.status_code, 500)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'error')
            self.assertIn('PostgreSQL connection error', data['message'])

    def test_connect_mysql_failure(self):
        """
        測試連接 MySQL 資料庫失敗。
        """
        self.mock_vn_connect_to_mysql.side_effect = Exception("MySQL connection error")
        with self.app.post('/api/connect', json={'type': 'mysql', 'host': 'localhost', 'port': '3306', 'user': 'user', 'password': 'password', 'database': 'testdb'}) as response:
            self.assertEqual(response.status_code, 500)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'error')
            self.assertIn('MySQL connection error', data['message'])

    def test_connect_mssql_failure(self):
        """
        測試連接 MSSQL 資料庫失敗。
        """
        self.mock_vn_connect_to_mssql.side_effect = Exception("MSSQL connection error")
        with self.app.post('/api/connect', json={'type': 'mssql', 'host': 'localhost', 'port': '1433', 'user': 'user', 'password': 'password', 'database': 'testdb'}) as response:
            self.assertEqual(response.status_code, 500)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'error')
            self.assertIn('MSSQL connection error', data['message'])

if __name__ == '__main__':
    unittest.main()
