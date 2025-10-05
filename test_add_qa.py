import requests
import json
import time

# Test configuration
BASE_URL = "http://localhost:5001"
USERNAME = "user1"
PASSWORD = "pass1"  # Default password from tests

# Create a session object to persist cookies
session = requests.Session()

# First, we need to login to get a session cookie
print("Testing login...")
print(f"URL: {BASE_URL}/login")
print(f"Username: {USERNAME}")
print(f"Password: {PASSWORD}")

# In the multi-user app, login uses form data, not JSON
login_response = session.post(f"{BASE_URL}/login", data={"username": USERNAME, "password": PASSWORD}, allow_redirects=False)
print(f"Login status code: {login_response.status_code}")
print(f"Response headers: {login_response.headers}")
print(f"Response text length: {len(login_response.text)} characters")
print(f"Response text preview: {login_response.text[:200]}...")
print(f"Cookies: {session.cookies.get_dict()}")

# Let's check if the login page is being served (indicating login failure)
if "login" in login_response.text.lower() or login_response.status_code == 200:
    print("Login failed - received login page again.")
    exit(1)

# For login, we expect a redirect (302) if successful
if login_response.status_code != 302:
    print("Login failed - unexpected status code.")
    exit(1)

print("Login successful!")

# Test the add_qa_question endpoint
print("\nTesting /api/add_qa_question endpoint...")

# Test data
qa_test_data = {
    "question": "這是一條測試問題",
    "sql": "SELECT * FROM users LIMIT 10;"
}

# Make the POST request to add a new QA pair using the session object
add_qa_response = session.post(
    f"{BASE_URL}/api/add_qa_question",
    json=qa_test_data
)

print(f"Add QA status code: {add_qa_response.status_code}")
print(f"Add QA response: {add_qa_response.text}")

# Check if the request was successful
if add_qa_response.status_code == 200:
    print("✅ Test passed: Successfully added a QA pair!")
    # Parse the response to get the new QA ID
    response_data = add_qa_response.json()
    if response_data.get('status') == 'success':
        qa_id = response_data.get('id')
        print(f"New QA ID: {qa_id}")
    elif response_data.get('status') == 'info':
        print(f"ℹ️  QA pair already exists with ID: {response_data.get('id')}")
else:
    print("❌ Test failed: Could not add QA pair.")

print("\nTest completed.")