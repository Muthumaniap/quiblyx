"""Generate local-only secrets without printing them or overwriting existing settings."""
from pathlib import Path
import base64
import secrets

target = Path(".env")
if target.exists():
    raise SystemExit(".env already exists; preserved")
source = Path(".env.example").read_text()
source = source.replace("SECRET_KEY=GENERATE_WITH_INIT_ENV", "SECRET_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
source = source.replace("DEV_LOGIN_TOKEN=GENERATE_WITH_INIT_ENV", "DEV_LOGIN_TOKEN=" + secrets.token_urlsafe(32))
target.write_text(source)
print("Created .env with fresh local development credentials. Do not commit this file.")
