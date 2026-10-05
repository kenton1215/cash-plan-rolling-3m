"""ORM 数据模型 (金额单位统一为万元, 日期/月份统一为字符串便于在线编辑)"""
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, Float, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Company(Base):
    """企业"""
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    credit_code = Column(String(64), default="")
    industry = Column(String(100), default="研产销一体")
    created_at = Column(DateTime, default=datetime.now)


class User(Base):
    """用户/操作员 (RBAC: company_admin/finance/sales/purchase/rd/hr/admin_dept/management)"""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    username = Column(String(64), nullable=False)
    password_hash = Column(String(256), nullable=False)
    name = Column(String(64), default="")
    role = Column(String(32), nullable=False, default="finance")
    created_at = Column(DateTime, default=datetime.now)
    __table_args__ = (UniqueConstraint("company_id", "username", name="uq_users_company_username"),)


class SafetyConfig(Base):
    """现金安全底线配置: 底线 = 月均刚性付现成本 × 安全系数"""
    __tablename__ = "safety_config"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    monthly_rigid_cost = Column(Float, default=0)
    safety_factor = Column(Float, default=1.5)
    safety_line = Column(Float, default=0)


class RollingConfig(Base):
    """滚动编制配置"""
    __tablename__ = "rolling_config"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    rolling_months = Column(Integer, default=3)
    update_day = Column(Integer, default=25)


class OpeningCash(Base):
    """期初现金余额 (每月一行, 仅第一月需要, 其后各月期初=上月期末)"""
    __tablename__ = "opening_cash"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    month = Column(String(7), nullable=False)  # YYYY-MM
    amount = Column(Float, default=0)
    note = Column(String(300), default="")
    __table_args__ = (UniqueConstraint("company_id", "month", name="uq_opening_company_month"),)


class Receivable(Base):
    """应收账款台账 (销售)"""
    __tablename__ = "receivables"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    customer = Column(String(100), default="")
    contract_no = Column(String(100), default="")
    amount = Column(Float, default=0)
    credit_days = Column(Integer, default=0)
    due_date = Column(String(10), default="")  # YYYY-MM-DD
    history_rate = Column(Float, default=1.0)  # 历史回款率 0~1
    note = Column(String(300), default="")


class SalesOrder(Base):
    """销售订单 (已签/预测)"""
    __tablename__ = "sales_orders"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    customer = Column(String(100), default="")
    order_no = Column(String(100), default="")
    amount = Column(Float, default=0)
    sign_date = Column(String(10), default="")
    ship_month = Column(String(7), default="")  # 预计发货月份 YYYY-MM
    credit_days = Column(Integer, default=0)    # 信用期(天)
    win_prob = Column(Float, default=1.0)       # 赢单概率 0~1
    is_forecast = Column(Boolean, default=False)  # 是否预测订单
    note = Column(String(300), default="")


class NoteBill(Base):
    """应收票据 (银行承兑/商业承兑)"""
    __tablename__ = "note_bills"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    bill_type = Column(String(20), default="银行承兑")
    bill_no = Column(String(100), default="")
    amount = Column(Float, default=0)
    due_date = Column(String(10), default="")
    accept_rate = Column(Float, default=1.0)  # 兑付概率 0~1
    note = Column(String(300), default="")


class OtherInflow(Base):
    """其他现金流入 (退税/补贴/利息等)"""
    __tablename__ = "other_inflows"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    item = Column(String(100), default="")
    month = Column(String(7), default="")
    amount = Column(Float, default=0)
    note = Column(String(300), default="")


class Payable(Base):
    """应付账款台账 (采购)"""
    __tablename__ = "payables"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    supplier = Column(String(100), default="")
    po_no = Column(String(100), default="")
    amount = Column(Float, default=0)
    due_date = Column(String(10), default="")
    note = Column(String(300), default="")


class PurchaseForecast(Base):
    """采购预测 (排产×BOM推算; is_rd=研发试产, 单独列示)"""
    __tablename__ = "purchase_forecasts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    material = Column(String(100), default="")
    qty = Column(Float, default=0)
    unit_price = Column(Float, default=0)
    purchase_month = Column(String(7), default="")
    credit_days = Column(Integer, default=0)   # 账期(天), 0=现款
    prepay_ratio = Column(Float, default=0)    # 预付比例 0~1
    is_rd = Column(Boolean, default=False)
    note = Column(String(300), default="")


class PayrollPlan(Base):
    """人工付现计划 (人力)"""
    __tablename__ = "payroll_plans"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    month = Column(String(7), nullable=False)
    salary = Column(Float, default=0)
    social = Column(Float, default=0)
    bonus = Column(Float, default=0)
    note = Column(String(300), default="")
    __table_args__ = (UniqueConstraint("company_id", "month", name="uq_payroll_company_month"),)


class ExpensePlan(Base):
    """费用计划 (研发/销售/管理/行政/财务; is_cash=False 的非付现项自动剔除)"""
    __tablename__ = "expense_plans"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    department = Column(String(32), default="")
    item = Column(String(100), default="")
    month = Column(String(7), default="")
    amount = Column(Float, default=0)
    is_cash = Column(Boolean, default=True)
    note = Column(String(300), default="")


class CapexPlan(Base):
    """资本支出计划"""
    __tablename__ = "capex_plans"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    project = Column(String(100), default="")
    amount = Column(Float, default=0)
    pay_month = Column(String(7), default="")
    note = Column(String(300), default="")


class TaxPlan(Base):
    """税务计划"""
    __tablename__ = "tax_plans"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    tax_type = Column(String(32), default="")
    period = Column(String(64), default="")
    amount = Column(Float, default=0)
    pay_month = Column(String(7), default="")
    note = Column(String(300), default="")


class LoanSchedule(Base):
    """贷款与筹资台账 (direction: borrow=新增借款[流入] / repay=还款[流出])"""
    __tablename__ = "loan_schedules"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    bank = Column(String(100), default="")
    direction = Column(String(8), default="repay")
    amount = Column(Float, default=0)
    month = Column(String(7), default="")
    note = Column(String(300), default="")


class MonthActual(Base):
    """月度实际数: 每月月末填写, 生成计划时直接替换预测数(滚动更新)"""
    __tablename__ = "month_actuals"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    month = Column(String(7), nullable=False)
    opening_cash = Column(Float, nullable=True)
    inflow = Column(Float, nullable=True)
    outflow = Column(Float, nullable=True)
    closing_cash = Column(Float, nullable=True)
    note = Column(String(300), default="")
    __table_args__ = (UniqueConstraint("company_id", "month", name="uq_actual_company_month"),)


class CashPlan(Base):
    """滚动资金计划结果 (每行=一个期间月度)"""
    __tablename__ = "cash_plans"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False, index=True)
    plan_month = Column(String(7), nullable=False)   # 编制月
    period_month = Column(String(7), nullable=False)  # 计划期间
    month_index = Column(Integer, default=1)
    opening_cash = Column(Float, default=0)
    inflow = Column(Float, default=0)
    outflow = Column(Float, default=0)
    net = Column(Float, default=0)
    closing_cash = Column(Float, default=0)
    safety_line = Column(Float, default=0)
    gap = Column(Float, default=0)
    is_actual = Column(Boolean, default=False)
    detail_json = Column(Text, default="{}")          # 流入/流出明细(JSON)
    diagnosis_text = Column(Text, default="")         # 智能诊断(LLM)
    report_text = Column(Text, default="")            # 文字报告(LLM)
    created_at = Column(DateTime, default=datetime.now)
    __table_args__ = (UniqueConstraint("company_id", "plan_month", "period_month",
                                       name="uq_plan_company_period"),)
