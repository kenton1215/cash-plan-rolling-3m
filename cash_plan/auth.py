"""认证与用户管理 (PBKDF2 口令哈希, 无需额外依赖)"""
import hashlib
import secrets

from .database import session_scope
from .models import Company, User


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return secrets.compare_digest(dk.hex(), expected)
    except Exception:
        return False


def authenticate(username: str, password: str):
    """登录校验, 返回用户dict或None"""
    with session_scope() as sess:
        u = sess.query(User).filter(User.username == username.strip()).first()
        if not u or not verify_password(password, u.password_hash):
            return None
        return {"id": u.id, "company_id": u.company_id, "username": u.username,
                "name": u.name or u.username, "role": u.role}


def register_company(company_name, credit_code, industry, admin_username, admin_name, password):
    """企业注册 + 创建企业管理员账号"""
    with session_scope() as sess:
        if sess.query(Company).filter(Company.name == company_name).first():
            return None, "企业名称已存在"
        if sess.query(User).filter(User.username == admin_username).first():
            return None, "该用户名已被占用"
        c = Company(name=company_name, credit_code=credit_code or "", industry=industry or "研产销一体")
        sess.add(c)
        sess.flush()
        sess.add(User(company_id=c.id, username=admin_username,
                      password_hash=hash_password(password),
                      name=admin_name or "管理员", role="company_admin"))
        return c.id, None


def create_operator(company_id, username, name, role, password):
    with session_scope() as sess:
        if sess.query(User).filter(User.company_id == company_id,
                                   User.username == username).first():
            return None, "该用户名在本企业已存在"
        u = User(company_id=company_id, username=username, password_hash=hash_password(password),
                 name=name or username, role=role)
        sess.add(u)
        sess.flush()
        return u.id, None


def list_users(company_id):
    with session_scope() as sess:
        return sess.query(User).filter(User.company_id == company_id).order_by(User.id).all()


def delete_user(user_id, company_id):
    with session_scope() as sess:
        u = sess.query(User).filter(User.id == user_id, User.company_id == company_id).first()
        if u:
            sess.delete(u)
            return True
        return False


def reset_password(user_id, company_id, new_password):
    with session_scope() as sess:
        u = sess.query(User).filter(User.id == user_id, User.company_id == company_id).first()
        if u:
            u.password_hash = hash_password(new_password)
            return True
        return False


def get_company_name(company_id):
    with session_scope() as sess:
        c = sess.query(Company).filter(Company.id == company_id).first()
        return c.name if c else ""
