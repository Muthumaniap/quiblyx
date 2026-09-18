import os
import base64
os.environ.setdefault("SECRET_KEY", base64.urlsafe_b64encode(b"t" * 32).decode())
os.environ.setdefault("DEV_IDENTITY", "true")
os.environ.setdefault("DEV_LOGIN_TOKEN", "test-local-token")
