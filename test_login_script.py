import requests

# URL for the login endpoint
url = 'http://localhost:5002/login'

# User credentials from the .env file
data = {
    'username': 'user1',
    'password': 'pass1'
}

# Send POST request with proper form data
response = requests.post(url, data=data, allow_redirects=False)

# Print status code and response content
print(f'Status Code: {response.status_code}')
print(f'Response Headers: {response.headers}')
print(f'Response Content: {response.text[:500]}...') # Print first 500 characters

if response.status_code == 302:  # Check for redirect which indicates successful login
    print('Login successful! Server returned redirect.')
else:
    print('Login failed.')