"""
SmartRx AI — Auth Routes
POST /api/auth/login
POST /api/auth/register
POST /api/auth/refresh
GET  /api/auth/me
POST /api/auth/offline-token
POST /api/auth/logout
"""

from flask import Blueprint, request, jsonify, g
from datetime import datetime
from ..database.db import query, execute
from .auth_utils import (
    hash_password, verify_password,
    create_token, create_offline_token,
    require_auth, ACCESS_EXPIRE, REFRESH_EXPIRE
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    user = query(
        "SELECT * FROM users WHERE (username=? OR email=?) AND is_active=1",
        (username, username), one=True
    )
    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid credentials"}), 401

    # Update last login
    execute("UPDATE users SET last_login=? WHERE id=?",
            (datetime.now().isoformat(), user["id"]))

    payload = {"user_id": user["id"], "role": user["role"],
               "pharmacy_id": user["pharmacy_id"]}

    return jsonify({
        "access_token":  create_token(payload),
        "refresh_token": create_token(payload, REFRESH_EXPIRE, "refresh"),
        "token_type":    "bearer",
        "expires_in":    int(ACCESS_EXPIRE.total_seconds()),
        "user": {
            "id":          user["id"],
            "username":    user["username"],
            "email":       user["email"],
            "full_name":   user["full_name"],
            "full_name_am": user["full_name_am"],
            "role":        user["role"],
            "pharmacy_id": user["pharmacy_id"],
        }
    })


@auth_bp.post("/register")
def register():
    body = request.get_json(silent=True) or {}
    required = ["username", "email", "password"]
    missing  = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    # Check duplicate
    existing = query(
        "SELECT id FROM users WHERE username=? OR email=?",
        (body["username"], body["email"]), one=True
    )
    if existing:
        return jsonify({"error": "Username or email already exists"}), 409

    # Patients self-register; staff/admin created by admin
    role = "patient"

    uid = execute(
        """INSERT INTO users (username, email, password_hash, full_name, full_name_am,
           role, phone, is_active, is_verified)
           VALUES (?,?,?,?,?,?,?,1,0)""",
        (body["username"], body["email"], hash_password(body["password"]),
         body.get("full_name"), body.get("full_name_am"),
         role, body.get("phone"))
    )

    payload = {"user_id": uid, "role": role, "pharmacy_id": None}
    return jsonify({
        "access_token": create_token(payload),
        "token_type":   "bearer",
        "user_id":      uid,
        "role":         role,
    }), 201


@auth_bp.post("/refresh")
def refresh():
    body  = request.get_json(silent=True) or {}
    token = body.get("refresh_token", "")
    if not token:
        return jsonify({"error": "refresh_token required"}), 400

    from .auth_utils import decode_token
    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        return jsonify({"error": "Invalid or expired refresh token"}), 401

    new_payload = {"user_id": payload["user_id"], "role": payload["role"],
                   "pharmacy_id": payload.get("pharmacy_id")}
    return jsonify({
        "access_token": create_token(new_payload),
        "token_type":   "bearer",
        "expires_in":   int(ACCESS_EXPIRE.total_seconds()),
    })


@auth_bp.get("/me")
@require_auth
def me():
    user = query("SELECT * FROM users WHERE id=?", (g.user_id,), one=True)
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.pop("password_hash", None)
    user.pop("refresh_token", None)
    user.pop("offline_token", None)
    return jsonify(user)


@auth_bp.post("/offline-token")
@require_auth
def offline_token():
    """Generate long-lived offline token for pharmacy staff."""
    if g.role not in ("pharmacy_staff", "admin"):
        return jsonify({"error": "Only pharmacy staff can get offline tokens"}), 403

    token = create_offline_token(g.user_id, g.pharmacy_id)
    expires = (datetime.now() + __import__("datetime").timedelta(days=7)).isoformat()

    execute("UPDATE users SET offline_token=?, offline_token_expires=? WHERE id=?",
            (token, expires, g.user_id))

    return jsonify({
        "offline_token": token,
        "expires_at":    expires,
        "pharmacy_id":   g.pharmacy_id,
        "note":          "Store securely. Valid 7 days. Works without internet.",
    })


@auth_bp.post("/logout")
@require_auth
def logout():
    execute("UPDATE users SET refresh_token=NULL WHERE id=?", (g.user_id,))
    return jsonify({"message": "Logged out successfully"})
