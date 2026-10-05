"""演示数据 (金额单位: 万元; 月份基于当前月动态生成, 长期有效)

演示场景: 研产销一体企业, 应收账期长+采购预付+资本支出集中,
未来三个月资金缺口逐步扩大 → 便于演示缺口诊断与情景模拟。
"""
from datetime import date

from . import models as M
from .auth import hash_password
from .engine import add_months

DEMO_USERS = [
    ("admin", "admin123", "张总", "company_admin"),
    ("finance", "finance123", "王专员", "finance"),
    ("sales", "sales123", "李销售", "sales"),
    ("purchase", "purchase123", "赵采购", "purchase"),
    ("rd", "rd123", "钱研发", "rd"),
    ("hr", "hr123", "孙人力", "hr"),
    ("xz", "xz123", "周行政", "admin_dept"),
    ("mgmt", "mgmt123", "吴总", "management"),
]


def seed_demo(sess, company_id, create_users=False):
    """向指定企业导入演示数据; create_users=True 时同时创建演示操作员账号"""
    if (sess.query(M.Receivable).filter(M.Receivable.company_id == company_id).count() > 0
            or sess.query(M.OpeningCash).filter(M.OpeningCash.company_id == company_id).count() > 0):
        return False, "该公司已有业务数据, 未重复导入。"

    m1 = date.today().strftime("%Y-%m")
    m2, m3 = add_months(m1, 1), add_months(m1, 2)

    # ---- 计划参数 ----
    if not sess.query(M.SafetyConfig).filter(M.SafetyConfig.company_id == company_id).first():
        sess.add(M.SafetyConfig(company_id=company_id, monthly_rigid_cost=800,
                                safety_factor=1.5, safety_line=1200))
    if not sess.query(M.RollingConfig).filter(M.RollingConfig.company_id == company_id).first():
        sess.add(M.RollingConfig(company_id=company_id, rolling_months=3, update_day=25))

    # ---- 演示操作员 ----
    if create_users:
        for username, password, name, role in DEMO_USERS:
            if not sess.query(M.User).filter(M.User.company_id == company_id,
                                             M.User.username == username).first():
                sess.add(M.User(company_id=company_id, username=username,
                                password_hash=hash_password(password), name=name, role=role))

    # ---- 期初现金 ----
    sess.add(M.OpeningCash(company_id=company_id, month=m1, amount=1500,
                           note=f"{m1}月初实际可用现金"))

    # ---- 应收台账 (销售) ----
    for row in [
        ("客户A", "HT-2026-001", 300, 60, f"{m1}-15", 0.95),
        ("客户B", "HT-2026-002", 150, 30, f"{m1}-20", 0.80),
        ("客户C", "HT-2026-003", 200, 60, f"{m2}-05", 0.90),
        ("客户D", "HT-2026-004", 120, 45, f"{m3}-10", 0.85),
    ]:
        sess.add(M.Receivable(company_id=company_id, customer=row[0], contract_no=row[1],
                              amount=row[2], credit_days=row[3], due_date=row[4],
                              history_rate=row[5], note="演示数据"))

    # ---- 销售订单 (已签 + 预测) ----
    for row in [
        ("客户E", "SO-2026-101", 200, f"{m1}-01", m1, 30, 1.0, False),
        ("客户F", "SO-2026-102", 150, f"{m2}-01", m2, 30, 1.0, False),
        ("客户G", "SO-2026-103", 300, f"{m3}-01", m3, 30, 0.7, True),
        ("客户H", "SO-2026-104", 200, f"{m2}-15", m2, 30, 0.6, True),
    ]:
        sess.add(M.SalesOrder(company_id=company_id, customer=row[0], order_no=row[1],
                              amount=row[2], sign_date=row[3], ship_month=row[4],
                              credit_days=row[5], win_prob=row[6], is_forecast=row[7],
                              note="演示数据"))

    # ---- 应收票据 ----
    sess.add(M.NoteBill(company_id=company_id, bill_type="银行承兑", bill_no="YH-001",
                        amount=50, due_date=f"{m1}-25", accept_rate=1.0, note="演示数据"))
    sess.add(M.NoteBill(company_id=company_id, bill_type="商业承兑", bill_no="SY-001",
                        amount=30, due_date=f"{m2}-10", accept_rate=0.9, note="演示数据"))

    # ---- 其他流入 ----
    for item, month, amount in [("出口退税", m1, 20), ("政府补贴", m2, 10), ("利息收入", m3, 15)]:
        sess.add(M.OtherInflow(company_id=company_id, item=item, month=month,
                               amount=amount, note="演示数据"))

    # ---- 应付台账 (采购) ----
    for row in [
        ("供应商甲", "PO-2026-001", 400, f"{m1}-18"),
        ("供应商乙", "PO-2026-002", 350, f"{m2}-12"),
        ("供应商丙", "PO-2026-003", 380, f"{m3}-08"),
        ("供应商丁", "PO-2026-004", 90, f"{m1}-25"),
    ]:
        sess.add(M.Payable(company_id=company_id, supplier=row[0], po_no=row[1],
                           amount=row[2], due_date=row[3], note="演示数据"))

    # ---- 采购预测 (排产×BOM推算; 研发试产现款单独列示) ----
    for row in [
        ("核心原材料", 100, 2.0, m1, 30, 0.3, False),
        ("核心原材料", 110, 2.0, m2, 30, 0.3, False),
        ("核心原材料", 125, 2.0, m3, 30, 0.3, False),
        ("研发试产物料", 1, 30.0, m1, 0, 1.0, True),
        ("研发试产物料", 1, 25.0, m2, 0, 1.0, True),
        ("外协加工", 1, 40.0, m3, 30, 0.5, False),
    ]:
        sess.add(M.PurchaseForecast(company_id=company_id, material=row[0], qty=row[1],
                                    unit_price=row[2], purchase_month=row[3],
                                    credit_days=row[4], prepay_ratio=row[5], is_rd=row[6],
                                    note="演示数据"))

    # ---- 人工计划 (人力) ----
    for month, salary, social, bonus in [(m1, 200, 60, 20), (m2, 200, 60, 20), (m3, 200, 60, 40)]:
        sess.add(M.PayrollPlan(company_id=company_id, month=month, salary=salary,
                               social=social, bonus=bonus, note="演示数据"))

    # ---- 费用计划 ----
    for dept, item, month, amount, is_cash in [
        ("研发", "材料测试费", m1, 80, True), ("研发", "材料测试费", m2, 90, True),
        ("研发", "材料测试费", m3, 100, True), ("研发", "专利费", m3, 10, True),
        ("销售", "差旅展会", m1, 60, True), ("销售", "差旅展会", m2, 55, True),
        ("销售", "差旅展会", m3, 70, True),
        ("管理", "办公租金", m1, 40, True), ("管理", "办公租金", m2, 40, True),
        ("管理", "办公租金", m3, 40, True),
        ("财务", "贷款利息", m1, 25, True), ("财务", "贷款利息", m2, 25, True),
        ("财务", "贷款利息", m3, 25, True),
        ("行政", "水电物业", m1, 15, True), ("行政", "水电物业", m2, 15, True),
        ("行政", "水电物业", m3, 15, True),
        ("生产", "设备折旧(非付现)", m1, 20, False),
    ]:
        sess.add(M.ExpensePlan(company_id=company_id, department=dept, item=item,
                               month=month, amount=amount, is_cash=is_cash, note="演示数据"))

    # ---- 资本支出 ----
    sess.add(M.CapexPlan(company_id=company_id, project="自动化产线设备", amount=100,
                         pay_month=m1, note="演示数据"))
    sess.add(M.CapexPlan(company_id=company_id, project="检测设备", amount=50,
                         pay_month=m2, note="演示数据"))

    # ---- 税负 ----
    sess.add(M.TaxPlan(company_id=company_id, tax_type="增值税", period=f"{m1}所属",
                       amount=80, pay_month=m1, note="演示数据"))
    sess.add(M.TaxPlan(company_id=company_id, tax_type="企业所得税", period="季度预缴",
                       amount=120, pay_month=m3, note="演示数据"))

    # ---- 贷款与筹资 ----
    for month in (m1, m2, m3):
        sess.add(M.LoanSchedule(company_id=company_id, bank="银行A", direction="repay",
                                amount=200, month=month, note="流贷分期还款"))
    sess.add(M.LoanSchedule(company_id=company_id, bank="银行B", direction="borrow",
                            amount=300, month=m2, note="授信提款(应对缺口)"))

    sess.flush()
    return True, "演示数据导入完成: 应收4笔/订单4笔/票据2笔/应付4笔/采购预测6笔/工资3月/费用17笔/资本2笔/税务2笔/贷款4笔"
