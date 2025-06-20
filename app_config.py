import os

# Make sure these match your Azure Entra ID app registration
AUTHORITY = os.getenv("AUTHORITY", "https://login.microsoftonline.com/common")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
ENDPOINT = os.getenv("ENDPOINT", "https://graph.microsoft.com/v1.0/me")
SCOPE = os.getenv("SCOPE", "User.Read")

# Session configs
SESSION_TYPE = "filesystem"
SECRET_KEY = os.urandom(24)
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "True").lower() == "true"
PREFERRED_URL_SCHEME = 'https'  # Add this line for SSL