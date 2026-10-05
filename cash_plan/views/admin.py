"""系统管理页 (仅企业管理员): 操作员管理 / 计划参数 / 演示数据"""
import pandas as pd
import streamlit as st

from .. import models as M
from ..auth import (create_operator, delete_user, list_users, reset_password)
from ..config import ROLE_LABELS
from ..database import session_scope
from ..demo_data import seed_demo
from .common import require_login


def view():
    require_login()
    user = st.session_state["user"]
    if user["role"] != "company_admin":
        st.warning("无权限访问")
        return
    cid = user["company_id"]
    st.header("⚙️ 系统管理")

    tab1, tab2, tab3 = st.tabs(["👥 操作员管理", "📐 计划参数", "🧪 演示数据"])

    with tab1:
        _users_tab(cid, user)
    with tab2:
        _params_tab(cid)
    with tab3:
        _demo_tab(cid)


def _users_tab(cid, current_user):
    users = list_users(cid)
    df = pd.DataFrame([{"用户名": u.username, "姓名": u.name, "角色": ROLE_LABELS.get(u.role, u.role)}
                       for u in users])
    st.dataframe(df, width="stretch", hide_index=True)
    st.caption(f"共 {len(users)} 名操作员。各部门操作员只能维护本部门数据; 资金计划专员可代录全部。")

    with st.expander("➕ 新增操作员"):
        with st.form("add_user"):
            c1, c2 = st.columns(2)
            username = c1.text_input("用户名(登录用)")
            name = c2.text_input("姓名")
            c3, c4 = st.columns(2)
            role = c3.selectbox("角色", list(ROLE_LABELS.keys()), format_func=ROLE_LABELS.get)
            password = c4.text_input("初始密码", type="password")
            if st.form_submit_button("创建操作员", type="primary"):
                if len(username.strip()) < 2:
                    st.error("用户名至少2个字符")
                elif len(password or "") < 6:
                    st.error("密码至少6位")
                else:
                    _, err = create_operator(cid, username.strip(), name.strip(), role, password)
                    if err:
                        st.error(err)
                    else:
                        st.success(f"操作员「{username}」已创建")
                        st.rerun()

    with st.expander("🗑 删除操作员 / 🔑 重置密码"):
        others = [u for u in users if u.id != current_user["id"]]
        if not others:
            st.caption("暂无其他操作员")
        else:
            labels = {f"{u.username}({u.name or '-'})": u for u in others}
            sel = st.selectbox("选择操作员", list(labels.keys()))
            c1, c2 = st.columns(2)
            if c1.button("删除该操作员"):
                target = labels[sel]
                if target.role == "company_admin":
                    admins = [u for u in users if u.role == "company_admin"]
                    if len(admins) <= 1:
                        st.error("不能删除唯一的企业管理员")
                    else:
                        delete_user(target.id, cid)
                        st.success("已删除")
                        st.rerun()
                else:
                    delete_user(target.id, cid)
                    st.success("已删除")
                    st.rerun()
            new_pw = c2.text_input("新密码", type="password", key="reset_pw")
            if c2.button("重置密码"):
                if len(new_pw or "") < 6:
                    st.error("密码至少6位")
                else:
                    reset_password(labels[sel].id, cid, new_pw)
                    st.success("密码已重置")
                    st.rerun()


def _params_tab(cid):
    with session_scope() as sess:
        sc = sess.query(M.SafetyConfig).filter(M.SafetyConfig.company_id == cid).first()
        rc = sess.query(M.RollingConfig).filter(M.RollingConfig.company_id == cid).first()

    with st.form("params_form"):
        st.markdown("**① 现金安全底线**")
        c1, c2 = st.columns(2)
        rigid = c1.number_input("月均刚性付现成本(万元)", min_value=0.0, step=10.0,
                                value=float(sc.monthly_rigid_cost if sc else 800))
        factor = c2.number_input("安全系数(建议1.5~2)", min_value=0.5, max_value=5.0, step=0.1,
                                 value=float(sc.safety_factor if sc else 1.5))
        st.caption(f"安全底线 = {rigid:,.0f} × {factor:,.1f} = **{rigid * factor:,.2f} 万元**"
                   f"　(工资+社保+房租+到期贷款+核心供应商货款等刚性付现 × 安全系数)")

        st.markdown("**② 滚动编制参数**")
        c3, c4 = st.columns(2)
        n = c3.selectbox("滚动月数", [2, 3, 4, 6],
                         index=[2, 3, 4, 6].index(rc.rolling_months if rc else 3))
        update_day = c4.slider("每月编制日", 1, 28, value=int(rc.update_day if rc else 25),
                               help="每月该日及之后首次访问系统时, 自动生成下月编制的滚动计划")
        if st.form_submit_button("💾 保存参数", type="primary"):
            with session_scope() as sess:
                if sc is None:
                    sess.add(M.SafetyConfig(company_id=cid, monthly_rigid_cost=rigid,
                                            safety_factor=factor,
                                            safety_line=round(rigid * factor, 2)))
                else:
                    sc.monthly_rigid_cost = rigid
                    sc.safety_factor = factor
                    sc.safety_line = round(rigid * factor, 2)
                if rc is None:
                    sess.add(M.RollingConfig(company_id=cid, rolling_months=n, update_day=update_day))
                else:
                    rc.rolling_months = n
                    rc.update_day = update_day
            st.success("参数已保存")
            st.rerun()


def _demo_tab(cid):
    st.markdown("一键导入研产销演示数据(应收4笔/订单4笔/票据2笔/应付4笔/采购预测6笔/工资3月/费用17笔/资本2笔/税务2笔/贷款4笔), 便于快速体验系统。")
    st.caption("演示场景: 账期长+采购预付+资本支出集中, 未来三个月缺口逐步扩大, 适合演示缺口诊断与情景模拟。")
    create_users = st.checkbox("同时创建演示操作员账号(销售/采购/研发/人力/行政/管理层)")
    if st.button("🧪 导入演示数据", type="primary"):
        with session_scope() as sess:
            ok, msg = seed_demo(sess, cid, create_users=create_users)
        if ok:
            st.success(msg + ("(演示账号见README)" if create_users else ""))
        else:
            st.warning(msg)
        st.rerun()
