"""初始化演示企业「演示科技有限公司」及完整演示数据

用法: python init_demo_data.py

演示账号(密码):
  admin/admin123        企业管理员   finance/finance123 资金计划专员
  sales/sales123        销售         purchase/purchase123 采购
  rd/rd123              研发         hr/hr123            人力
  xz/xz123              行政         mgmt/mgmt123        管理层
"""
from cash_plan import models as M
from cash_plan.auth import hash_password
from cash_plan.database import init_db, session_scope
from cash_plan.demo_data import DEMO_USERS, seed_demo


def main():
    init_db()
    with session_scope() as sess:
        if sess.query(M.Company).filter(M.Company.name == "演示科技有限公司").first():
            print("演示企业已存在, 跳过创建。")
            return
        company = M.Company(name="演示科技有限公司", credit_code="91310000MA1DEMO000",
                            industry="研产销一体(智能制造)")
        sess.add(company)
        sess.flush()
        for username, password, name, role in DEMO_USERS:
            sess.add(M.User(company_id=company.id, username=username,
                            password_hash=hash_password(password), name=name, role=role))
        sess.flush()
        ok, msg = seed_demo(sess, company.id, create_users=False)
        print(msg)

    print("\n初始化完成!")
    print("启动系统: streamlit run app.py")
    print("登录演示: admin/admin123 (企业管理员) 或 finance/finance123 (资金计划专员)")


if __name__ == "__main__":
    main()
