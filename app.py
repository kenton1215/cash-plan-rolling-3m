"""智能三个月滚动资金计划系统 - Streamlit 主入口

启动: streamlit run app.py
演示数据: python init_demo_data.py (演示账号 admin/admin123)
"""
import streamlit as st

st.set_page_config(page_title="智能三个月滚动资金计划系统", page_icon="💰", layout="wide")

from cash_plan.auth import authenticate, get_company_name, register_company
from cash_plan.database import init_db
from cash_plan.views import admin, dashboard, data_entry, diagnosis, plan
from cash_plan.views.common import sidebar

init_db()


def auth_page():
    st.title("💰 智能三个月滚动资金计划系统")
    st.caption("研产销一体企业 · 三个月滚动编制 · 大模型智能诊断 · 一键导出Excel")
    st.divider()
    tab_login, tab_register = st.tabs(["🔑 登录", "🏢 企业注册"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", type="primary", width="stretch")
            if submitted:
                u = authenticate(username, password)
                if u:
                    st.session_state["user"] = u
                    st.session_state["company_name"] = get_company_name(u["company_id"])
                    st.rerun()
                else:
                    st.error("用户名或密码错误")

    with tab_register:
        st.markdown("注册后自动创建**企业管理员**账号, 管理员可在「系统管理」中为各部门创建操作员。")
        with st.form("register_form"):
            c1, c2 = st.columns(2)
            company_name = c1.text_input("企业名称")
            credit_code = c2.text_input("统一社会信用代码(选填)")
            industry = st.text_input("所属行业", value="研产销一体")
            c3, c4 = st.columns(2)
            admin_username = c3.text_input("管理员用户名")
            admin_name = c4.text_input("管理员姓名")
            c5, c6 = st.columns(2)
            pw1 = c5.text_input("管理员密码", type="password")
            pw2 = c6.text_input("确认密码", type="password")
            submitted = st.form_submit_button("注册企业", type="primary", width="stretch")
            if submitted:
                if not company_name.strip():
                    st.error("请填写企业名称")
                elif len(admin_username.strip()) < 2:
                    st.error("管理员用户名至少2个字符")
                elif len(pw1 or "") < 6 or pw1 != pw2:
                    st.error("密码至少6位且两次输入一致")
                else:
                    _, err = register_company(company_name.strip(), credit_code.strip(),
                                              industry.strip(), admin_username.strip(),
                                              admin_name.strip(), pw1)
                    if err:
                        st.error(err)
                    else:
                        st.success(f"✅ 企业「{company_name}」注册成功! 请切换到「登录」页使用管理员账号登录。")

    st.divider()
    st.caption("💡 快速体验: 命令行运行 `python init_demo_data.py` 导入演示数据(演示账号 admin/admin123, "
               "或注册企业后在「系统管理」→「演示数据」一键导入)。")


def main():
    if "user" not in st.session_state:
        auth_page()
        return
    page = sidebar()
    views = {"dashboard": dashboard.view, "data_entry": data_entry.view,
             "plan": plan.view, "diagnosis": diagnosis.view, "admin": admin.view}
    views[page]()


if __name__ == "__main__":
    main()
