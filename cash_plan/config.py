"""全局配置"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

_default_db = f"sqlite:///{(BASE_DIR / 'cash_plan.db').as_posix()}"
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")

# 角色定义
ROLE_LABELS = {
    "company_admin": "企业管理员",
    "finance": "资金计划专员",
    "sales": "销售",
    "purchase": "采购",
    "rd": "研发",
    "hr": "人力",
    "admin_dept": "行政",
    "management": "管理层",
}

# 页面访问权限 (RBAC)
PAGE_ACCESS = {
    "dashboard": {"company_admin", "finance", "sales", "purchase", "rd", "hr", "admin_dept", "management"},
    "data_entry": {"company_admin", "finance", "sales", "purchase", "rd", "hr", "admin_dept"},
    "plan": {"company_admin", "finance", "management"},
    "diagnosis": {"company_admin", "finance", "management"},
    "admin": {"company_admin"},
}
