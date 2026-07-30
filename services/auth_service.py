import hmac

from flask import current_app
from werkzeug.security import check_password_hash


def credentials_configured() -> bool:
    return bool(
        current_app.config.get('ADMIN_USERNAME')
        and current_app.config.get('ADMIN_PASSWORD_HASH')
    )


def authenticate(username: str, password: str) -> bool:
    if not credentials_configured():
        return False

    expected_username = current_app.config['ADMIN_USERNAME']
    username_ok = hmac.compare_digest(username or '', expected_username)
    password_ok = check_password_hash(
        current_app.config['ADMIN_PASSWORD_HASH'], password or ''
    )
    return username_ok and password_ok
