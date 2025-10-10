import os
from app import MyVanna

# Set environment variables for testing
os.environ['OLLAMA_MODEL'] = 'gpt-oss:20b'
os.environ['OLLAMA_HOST'] = 'http://10.227.135.98:11434'

# Try to instantiate MyVanna
print("Attempting to instantiate MyVanna...")
try:
    vn = MyVanna(user_id="test_user")
    print("Success! MyVanna instance created without abstract method errors.")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")