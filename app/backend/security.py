import hashlib
import hmac
import secrets
import time
import uuid
from fastapi import HTTPException, Request
from app.backend.database import timestamp

COOKIE = 'studio_session'
ITERATIONS = 600_000


def fail(status, code, message):
    raise HTTPException(status_code=status, detail={'code': code, 'message': message})


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt}${key.hex()}'


def verify_password(password, encoded):
    algorithm, iterations, salt, expected = encoded.split('$')
    if algorithm != 'pbkdf2_sha256':
        return False
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(actual, expected)


def provision_user(database, username, password):
    username = username.strip().lower()
    if not 3 <= len(username) <= 64 or not all(c in 'abcdefghijklmnopqrstuvwxyz0123456789._-' for c in username):
        raise ValueError('Username must be 3–64 lowercase letters, digits, dots, underscores or hyphens')
    if not 12 <= len(password) <= 128:
        raise ValueError('Password must be 12–128 characters')
    user_id = str(uuid.uuid4())
    with database.transaction(write=True) as db:
        db.execute('INSERT INTO users VALUES (?,?,?,?)', (user_id, username, hash_password(password), timestamp()))
    return user_id


def reset_password(database, username, password):
    """Trusted local recovery; revoke all sessions without deleting saved work."""
    if not 12 <= len(password) <= 128:
        raise ValueError('Password must be 12–128 characters')
    username = username.strip().lower()
    encoded = hash_password(password)
    with database.transaction(write=True) as db:
        user = db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
        if not user:
            raise ValueError('Account not found. Use create-user for a new account.')
        db.execute('UPDATE users SET password_hash=? WHERE id=?', (encoded, user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
        db.execute('DELETE FROM login_attempts WHERE bucket=?', (digest('user:' + username),))


def check_origin(request):
    origin = request.headers.get('origin')
    if origin is not None and origin not in request.app.state.settings.allowed_origins:
        fail(403, 'origin_denied', 'Request origin is not allowed.')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        fail(403, 'origin_denied', 'Cross-site requests are not allowed.')


def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 128:
        fail(401, 'authentication_required', 'Sign in to access saved work.')
    with request.app.state.database.transaction() as db:
        session = db.execute('SELECT s.*, u.username FROM sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=? AND expires_at>?', (digest(token), int(time.time()))).fetchone()
    if not session:
        fail(401, 'session_expired', 'Your session has expired. Sign in again.')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        check_origin(request)
        csrf = request.headers.get('x-csrf-token', '')
        if len(csrf) > 128 or not hmac.compare_digest(digest(csrf), session['csrf_hash']):
            fail(403, 'csrf_invalid', 'A valid CSRF token is required.')
    return dict(session)
