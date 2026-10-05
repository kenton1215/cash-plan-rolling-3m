"""首页看板: 最新计划KPI / 资金安全状态 / 数据待办"""
from datetime import date

import streamlit as st

from ..database import session_scope
from ..engine import add_months, list_plan_months, load_plan, validate_company_data
from .. import models as M
from .common import ensure_due_plan, require_login
from .plan import plan_chart


def view():
    require_login()
    user = st.session_state["user"]
    cid = user["company_id"]
    company_name = st.session_state.get("company_name", "")
    ensure_due_plan(cid, user["role"])

    st.header(f"📊 {company_name} · 资金计划看板")

    months_list = list_plan_months(cid)
    if not months_list:
        st.info("暂无资金计划。请前往「📈 资金计划」页生成第一期计划; 此后系统会在每月编制日自动滚动生成。")
        _todo_checklist(cid)
        return

    plan = load_plan(cid, months_list[0])
    rows = plan["rows"]
    worst = max(rows, key=lambda r: r["gap"])
    lowest = min(rows, key=lambda r: r["closing"])
    total_net = sum(r["net"] for r in rows)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("最新编制月", plan["plan_month"])
    c2.metric("三个月累计净流量", f"{total_net:,.2f} 万元")
    c3.metric("最低期末现金", f"{lowest['closing']:,.2f} 万元", delta=lowest["month"])
    c4.metric("资金安全状态", "🔴 缺口" if worst["gap"] > 0 else "🟢 安全",
              delta=f"最大缺口 {worst['gap']:,.2f} 万元" if worst["gap"] > 0 else "期末现金均高于底线",
              delta_color="inverse" if worst["gap"] > 0 else "normal")

    st.plotly_chart(plan_chart(plan), width="stretch")

    with st.expander("📋 数据待办清单"):
        _todo_checklist(cid, plan)

    st.caption("💡 使用提示: 每月编制日前各部门在「数据录入」页更新数据; 编制日后系统自动生成下月滚动计划; "
               "月末在「实际数与期初现金」填写实际数, 下期计划自动用实际数替换预测数。")


def _todo_checklist(cid, plan=None):
    months = plan["months"] if plan else [add_months(date.today().strftime("%Y-%m"), i)
                                          for i in range(3)]
    issues = validate_company_data(cid, months)
    with session_scope() as sess:
        counts = {
            "应收账款": sess.query(M.Receivable).filter(M.Receivable.company_id == cid).count(),
            "销售订单": sess.query(M.SalesOrder).filter(M.SalesOrder.company_id == cid).count(),
            "应付账款": sess.query(M.Payable).filter(M.Payable.company_id == cid).count(),
            "采购预测": sess.query(M.PurchaseForecast).filter(M.PurchaseForecast.company_id == cid).count(),
        }
    st.markdown("**基础数据完善度**")
    for k, v in counts.items():
        st.write(f"- {k}: {v} 条" + ("　✅" if v > 0 else "　⚠️ 暂无数据"))
    st.markdown("**校验问题**")
    if issues:
        for i in issues[:8]:
            icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(i["level"], "⚪")
            st.write(f"{icon} [{i['module']}] {i['message']}")
    else:
        st.write("✅ 数据完整, 无校验问题")
