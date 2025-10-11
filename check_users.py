from app import app

# Print configured users
print("Configured users in the application:")
print(app.config.get('USERS', {}))