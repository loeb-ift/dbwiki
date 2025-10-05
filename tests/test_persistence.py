import pytest
import requests
import os
import time
import json

# 基本配置
BASE_URL = "http://127.0.0.1:5001"
TEST_USER = "test_user"
TEST_PASSWORD = "test_password"
USER_DATA_DIR = os.path.join(os.getcwd(), 'user_data')
DATASET_DIR = os.path.join(USER_DATA_DIR, 'datasets')

# 测试数据
TEST_DDL = "CREATE TABLE employees (id INT, name VARCHAR(50));"
TEST_DOC = "This is a test documentation."
TEST_QA = [{"question": "How many employees?", "sql": "SELECT count(*) FROM employees"}]
TEST_RULE = {"incorrect_name": "employes", "correct_name": "employees"}

@pytest.fixture(scope="module")
def session():
    """创建一个 requests session 以在测试中保持 cookie。"""
    return requests.Session()

def cleanup_user_data():
    """清理测试用户的数据。"""
    user_db = os.path.join(USER_DATA_DIR, f'training_data_{TEST_USER}.sqlite')
    if os.path.exists(user_db):
        os.remove(user_db)
    
    # 清理上传的数据集文件
    if os.path.exists(DATASET_DIR):
        for f in os.listdir(DATASET_DIR):
            if f.startswith(TEST_USER):
                os.remove(os.path.join(DATASET_DIR, f))

@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    """在测试开始前和结束后进行设置和清理。"""
    # 确保测试用户存在于 app 的用户字典中
    # 注意：这需要手动或通过某种方式确保 app 知道这个测试用户
    # 在这个测试中，我们假设 app.py 已经重启并加载了包含测试用户的配置
    cleanup_user_data()
    yield
    cleanup_user_data()

def test_full_user_workflow(session):
    """
    测试完整的用户工作流程：
    1. 登录
    2. 上传 CSV 创建数据集
    3. 激活数据集
    4. 上传训练数据 (DDL, Doc, QA)
    5. 添加校对规则
    6. 登出
    7. 重新登录
    8. 验证所有数据是否持久化
    """
    # 步骤 1: 登录
    login_payload = {"username": TEST_USER, "password": TEST_PASSWORD}
    res = session.post(f"{BASE_URL}/login", data=login_payload)
    assert res.status_code == 200
    assert "session" in session.cookies

    # 步骤 2: 上传 CSV 创建数据集
    dataset_name = "test_dataset"
    with open("test_employees.csv", "w") as f:
        f.write("id,name\n1,Alice\n2,Bob")
    
    files = {'files': ('test_employees.csv', open('test_employees.csv', 'rb'), 'text/csv')}
    data = {'dataset_name': dataset_name}
    res = session.post(f"{BASE_URL}/api/datasets", files=files, data=data)
    os.remove("test_employees.csv") # 清理临时文件
    
    assert res.status_code == 201
    dataset_info = res.json()
    assert dataset_info['status'] == 'success'
    dataset_id = dataset_info['dataset']['id']

    # 步骤 3: 激活数据集
    res = session.post(f"{BASE_URL}/api/datasets/activate", json={"dataset_id": dataset_id})
    assert res.status_code == 200
    assert res.json()['status'] == 'success'

    # 步骤 4: 上传训练数据
    train_payload = {
        "ddl": TEST_DDL,
        "doc": TEST_DOC,
        "qa_pairs": json.dumps(TEST_QA)
    }
    res = session.post(f"{BASE_URL}/api/train", data=train_payload)
    assert res.status_code == 200

    # 步骤 5: 添加校对规则
    res = session.post(f"{BASE_URL}/api/correction_rules", json=TEST_RULE)
    assert res.status_code == 201
    rule_id = res.json()['rule']['id']

    # 步骤 6: 登出
    res = session.get(f"{BASE_URL}/logout")
    # After logout, the session cookie might still exist but be empty.
    # A better check is to see if a subsequent request to a protected route fails.
    res = session.get(f"{BASE_URL}/api/datasets")
    assert res.status_code == 401 # Unauthorized


    # 步骤 7: 重新登录
    res = session.post(f"{BASE_URL}/login", data=login_payload)
    assert res.status_code == 200
    assert "session" in session.cookies

    # 步骤 8: 验证数据持久性
    # 验证数据集
    res = session.get(f"{BASE_URL}/api/datasets")
    assert res.status_code == 200
    datasets = res.json()['datasets']
    assert any(d['id'] == dataset_id and d['dataset_name'] == dataset_name for d in datasets)

    # 验证校对规则
    res = session.get(f"{BASE_URL}/api/correction_rules")
    assert res.status_code == 200
    rules = res.json()['rules']
    assert any(r['id'] == rule_id and r['incorrect_name'] == TEST_RULE['incorrect_name'] for r in rules)

    # 验证训练数据 (通过检查数据库)
    # 注意：直接检查数据库是更可靠的验证方式
    user_db = os.path.join(USER_DATA_DIR, f'training_data_{TEST_USER}.sqlite')
    assert os.path.exists(user_db)
    
    import sqlite3
    conn = sqlite3.connect(user_db)
    cursor = conn.cursor()
    
    cursor.execute("SELECT ddl_statement FROM training_ddl")
    ddl_data = cursor.fetchone()
    assert ddl_data and ddl_data[0] == TEST_DDL

    cursor.execute("SELECT documentation_text FROM training_documentation")
    doc_data = cursor.fetchone()
    assert doc_data and doc_data[0] == TEST_DOC

    cursor.execute("SELECT question, sql_query FROM training_qa")
    qa_data = cursor.fetchone()
    assert qa_data and qa_data[0] == TEST_QA[0]['question'] and qa_data[1] == TEST_QA[0]['sql']
    
    conn.close()

    print("\n✅ All persistence checks passed!")
