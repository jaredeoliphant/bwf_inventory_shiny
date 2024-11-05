import bcrypt
import secrets

password_length = 8
password = secrets.token_urlsafe(password_length)

print(password)

# Generate a salt
salt = bcrypt.gensalt()

# Hash a password
hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)

print("Hashed Password:", hashed_password.decode('utf-8'))
