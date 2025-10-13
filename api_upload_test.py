import os
import sys
import logging
import requests
import uuid
from io import StringIO

# 配置日志
handlers = [
    logging.FileHandler('api_upload_test.log', encoding='utf-8'),
    logging.StreamHandler(sys.stdout)
]
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# 服务器信息
BASE_URL = "http://localhost:5004"
USERNAME = "user1"
PASSWORD = "pass1"

# 生成测试CSV数据
def generate_test_csv():
    csv_data = "column1,column2,column3\n"
    csv_data += "1,test1,value1\n"
    csv_data += "2,test2,value2\n"
    csv_data += "3,test3,value3\n"
    return csv_data

# 获取登录会话
def login():
    logger.info(f"尝试登录用户: {USERNAME}")
    session = requests.Session()
    login_response = session.post(
        f"{BASE_URL}/login",
        data={"username": USERNAME, "password": PASSWORD}
    )
    
    if login_response.status_code == 200:
        logger.info("登录成功")
        return session
    else:
        logger.error(f"登录失败: 状态码 {login_response.status_code}")
        logger.error(f"响应内容: {login_response.text}")
        return None

# 创建新数据集
def create_dataset(session, dataset_name):
    logger.info(f"尝试创建数据集: {dataset_name}")
    # 首先生成测试CSV数据
    csv_data = generate_test_csv()
    
    # 使用BytesIO替代StringIO，确保二进制数据格式正确
    from io import BytesIO
    csv_buffer = BytesIO(csv_data.encode('utf-8'))
    
    # 准备文件和表单数据
    # 使用标准的文件上传格式
    files = {
        'files': (
            'test_data.csv',  # 文件名
            csv_buffer,       # 文件对象
            'text/csv'        # MIME类型
        )
    }
    data = {'dataset_name': dataset_name}
    
    # 发送请求
    response = session.post(
        f"{BASE_URL}/api/datasets",
        files=files,
        data=data
    )
    
    logger.info(f"创建数据集响应状态码: {response.status_code}")
    logger.info(f"创建数据集响应内容: {response.text}")
    
    if response.status_code == 201:
        logger.info(f"数据集 '{dataset_name}' 创建成功")
        try:
            return response.json()
        except:
            logger.error("无法解析JSON响应")
            return None
    else:
        logger.error(f"创建数据集失败: 状态码 {response.status_code}")
        return None

# 列出所有数据集
def list_datasets(session):
    logger.info("尝试列出所有数据集")
    response = session.get(f"{BASE_URL}/api/datasets")
    
    if response.status_code == 200:
        datasets = response.json().get('datasets', [])
        logger.info(f"成功获取 {len(datasets)} 个数据集")
        for dataset in datasets:
            logger.info(f"- 数据集: {dataset['name']} (ID: {dataset['id']})")
        return datasets
    else:
        logger.error(f"列出数据集失败: 状态码 {response.status_code}")
        return None

# 删除数据集
def delete_dataset(session, dataset_id):
    logger.info(f"尝试删除数据集 ID: {dataset_id}")
    response = session.delete(
        f"{BASE_URL}/api/datasets",
        json={'dataset_id': dataset_id}
    )
    
    if response.status_code == 200:
        logger.info(f"数据集 ID {dataset_id} 删除成功")
        return True
    else:
        logger.error(f"删除数据集失败: 状态码 {response.status_code}")
        logger.error(f"响应内容: {response.text}")
        return False

# 向现有数据集添加文件
def add_file_to_dataset(session, dataset_id):
    logger.info(f"尝试向数据集 ID {dataset_id} 添加文件")
    # 生成新的测试CSV数据
    csv_data = "new_column1,new_column2\n"
    csv_data += "4,new_value4\n"
    csv_data += "5,new_value5\n"
    
    # 使用BytesIO确保二进制数据格式正确
    from io import BytesIO
    csv_buffer = BytesIO(csv_data.encode('utf-8'))
    
    # 准备文件数据
    files = {
        'files': (
            'additional_data.csv',  # 文件名
            csv_buffer,              # 文件对象
            'text/csv'               # MIME类型
        )
    }
    
    # 发送请求
    response = session.post(
        f"{BASE_URL}/api/datasets/files?dataset_id={dataset_id}",
        files=files
    )
    
    logger.info(f"添加文件响应状态码: {response.status_code}")
    logger.info(f"添加文件响应内容: {response.text}")
    
    if response.status_code == 200:
        logger.info(f"成功向数据集 ID {dataset_id} 添加文件")
        return True
    else:
        logger.error(f"向数据集添加文件失败: 状态码 {response.status_code}")
        return False

# 主函数
def main():
    logger.info("=== 开始API上传功能测试 ===")
    
    # 生成唯一的数据集名称以避免冲突
    dataset_name = f"api_test_dataset_{uuid.uuid4().hex[:8]}"
    
    try:
        # 步骤1: 登录
        session = login()
        if not session:
            logger.error("登录失败，无法继续测试")
            return
        
        # 步骤2: 创建新数据集
        create_result = create_dataset(session, dataset_name)
        if not create_result:
            logger.error("创建数据集失败，无法继续测试")
            return
        
        dataset_id = create_result['new_dataset']['id']
        logger.info(f"新创建的数据集ID: {dataset_id}")
        
        # 步骤3: 列出所有数据集，验证新数据集是否存在
        datasets = list_datasets(session)
        if datasets:
            created_dataset = next((d for d in datasets if d['id'] == dataset_id), None)
            if created_dataset:
                logger.info(f"确认数据集已创建: {created_dataset['name']}")
            else:
                logger.warning("在数据集列表中未找到新创建的数据集")
        
        # 步骤4: 向现有数据集添加文件
        add_file_success = add_file_to_dataset(session, dataset_id)
        if add_file_success:
            logger.info("文件添加功能测试成功")
        
        # 步骤5: 清理 - 删除测试数据集
        delete_dataset(session, dataset_id)
        
    except Exception as e:
        logger.error(f"测试过程中发生异常: {str(e)}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
    
    logger.info("\n=== API上传功能测试完成 ===")

if __name__ == "__main__":
    main()