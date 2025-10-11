import requests
import json
import os

# Login to get session cookie using the correct credentials
print("Using correct credentials: user1/pass1")
session = requests.Session()
login_data = {
    'username': 'user1',
    'password': 'pass1'
}

# Send login request
print("Sending login request...")
login_response = session.post('http://localhost:5001/login', data=login_data)

print(f"Login Response Status: {login_response.status_code}")
print(f"Login Response History: {login_response.history}")
print(f"Login Response Headers: {login_response.headers}")
print(f"Session Cookies: {session.cookies.get_dict()}")

# Now try to access a page that should require authentication
print("\nAccessing index page...")
index_response = session.get('http://localhost:5001/')
print(f"Index Response Status: {index_response.status_code}")

# Now make the API request
print("\nSending API request to /api/ask...")
ask_data = {
    'question': 'test question',
    'user_id': 'testuser',
    'model_type': 'ollama',
    'prompt_template': 'default'
}

ask_response = session.post('http://localhost:5001/api/ask', json=ask_data)

print(f"API Response Status: {ask_response.status_code}")
print(f"API Response Content (first 500 chars): {ask_response.text[:500]}")

# Check if log files were created
print("\nChecking if log files were created...")

# List files in ask_log directory
ask_log_dir = './ask_log'
if os.path.exists(ask_log_dir):
    print(f"Files in {ask_log_dir}:")
    for file in os.listdir(ask_log_dir):
        print(f"- {file}")
else:
    print(f"Directory {ask_log_dir} does not exist.")

# List files in prompt_history directory
prompt_history_dir = './prompt_history'
if os.path.exists(prompt_history_dir):
    print(f"Files in {prompt_history_dir}:")
    for file in os.listdir(prompt_history_dir):
        print(f"- {file}")
else:
    print(f"Directory {prompt_history_dir} does not exist.")