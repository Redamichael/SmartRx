"""
SmartRx AI — Auth utilities
JWT token generation/verification + password hashing (SHA-256 for demo,
bcrypt recommended for production).
"""

import hashlib
import jwt
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g

SECRET_KEY      = "smartrx-secret-2024-ethiopia"   # env var in production
ALGORITHM       = "HS256"
ACCESS_EXPIRE   = timedelta(hours=8)
REFRESH_EXPIRE  = timedelta(days=30)
OFFLINE_EXPIRE  = timedelta(days=7)

ROLE_PERMISSIONS = {
    "admin":          {"*"},
    "analyst":        {"read:*", "export:*"},
    "health_worker":  {"read:inventory", "read:alerts", "read:forecasts", "read:redistribution"},
    "pharmacy_staff": {"read:inventory", "write:inventory", "read:transactions", "write:transactions",
                       "read:prescriptions", "write:prescriptions"},
    "patient":        {"read:pharmacies", "read:medicines", "write:prescriptions", "read:own_prescriptions"},
}


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


def create_token(payload: dict, expires: timedelta = ACCESS_EXPIRE, token_type: str = "access") -> str:
    data = {**payload, "type": token_type,
            "exp": datetime.utcnow() + expires,
            "iat": datetime.utcnow()}
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def create_offline_token(user_id: int, pharmacy_id: int | None) -> str:
    """Long-lived token for offline pharmacy staff."""
    return create_token(
        {"user_id": user_id, "pharmacy_id": pharmacy_id, "offline": True},
        expires=OFFLINE_EXPIRE,
        token_type="offline"
    )


# ── Decorators ────────────────────────────────────────────────

def require_auth(f):
    """Require valid JWT. Sets g.user_id, g.role, g.pharmacy_id."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing token", "code": 401}), 401
        token = auth.split(" ", 1)[1]
        payload = decode_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token", "code": 401}), 401
        g.user_id    = payload.get("user_id")
        g.role       = payload.get("role", "patient")
        g.pharmacy_id = payload.get("pharmacy_id")
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    """Require one of the specified roles."""
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated(*args, **kwargs):
            if g.role not in roles and "admin" not in roles:
                if g.role != "admin":
                    return jsonify({"error": "Insufficient permissions", "code": 403}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def optional_auth(f):
    """Set g.user_id if token present, don't fail if missing."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        g.user_id    = None
        g.role       = "anonymous"
        g.pharmacy_id = None
        if auth.startswith("Bearer "):
            payload = decode_token(auth.split(" ", 1)[1])
            if payload:
                g.user_id     = payload.get("user_id")
                g.role        = payload.get("role", "patient")
                g.pharmacy_id = payload.get("pharmacy_id")
        return f(*args, **kwargs)
    return decorated
