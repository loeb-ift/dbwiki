import requests
import json

# Create a session object to persist cookies
session = requests.Session()

# Login to get session cookie using the correct credentials found in the config
login_data = {
    'username': 'user1',
    'password': 'pass1'
}

# Send login request
print("Sending login request...")
login_response = session.post('http://localhost:5001/login', data=login_data, allow_redirects=False)

print(f"Login Response Status: {login_response.status_code}")
print(f"Login Response Headers: {login_response.headers}")
print(f"Cookies after login: {session.cookies.get_dict()}")
print(f"Is there a redirect? {'Location' in login_response.headers}")
if 'Location' in login_response.headers:
    print(f"Redirect location: {login_response.headers['Location']}")

# If login was successful, try to access index page directly
if login_response.status_code == 302:
    print("\nFollowing redirect to index page...")
    index_response = session.get('http://localhost:5001/' + login_response.headers['Location'])
    print(f"Index Response Status: {index_response.status_code}")
    print(f"Cookies after index: {session.cookies.get_dict()}")
    
    # Now try to access a protected route
    print("\nTrying to access protected API endpoint...")
    ask_data = {
        'question': 'test question'
    }
    ask_response = session.post('http://localhost:5001/api/ask', json=ask_data)
    print(f"API Response Status: {ask_response.status_code}")
    print(f"API Response Content: {ask_response.text[:500]}")
else:
    print("\nLogin did not result in redirect - checking if login page was returned...")
    print(f"Response contains login form: {'<form' in login_response.text}")