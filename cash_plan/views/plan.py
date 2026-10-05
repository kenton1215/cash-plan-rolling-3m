"""资金计划页: 生成/查看三个月滚动资金计划, 智能诊断, 导出Excel"""
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import models as M
from ..agents import gap_diagnosis, generate_report, validation_feedback
from ..database import session_scope
from ..engine import (add_months, generate_plan, load_plan, save_diagnosis, save_plan,
                      validate_company_data)
from ..excel_export import build_excel
from .common import ensure_due_plan, require_login


def view():
    require_login()
    user = st.session_state["user"]
    cid = user["company_id"]
    company_name = st.session_state.get("company_name", "")
    editable = user["role"] in ("finance", "company_admin")
    ensure_due_plan(cid, user["role"])

    with session_scope() as sess:
        rc = sess.query(M.RollingConfig).filter(M.RollingConfig.company_id == cid).first()
        sc = sess.query(M.SafetyConfig).filter(M.SafetyConfig.company_id == cid).first()
    n = rc.rolling_months if rc else 3
    update_day = rc.update_day if rc else 25

    st.header("📈 三个月滚动资金计划")
    st.caption(f"滚动月数 {n} · 每月{update_day}日滚动更新 · 期初→流入→流出→期末现金→安全底线预警")
    if sc is None or not sc.safety_line:
        st.warning("⚠️ 尚未配置现金安全底线, 请管理员在「系统管理」中配置。")

    today = date.today()
    cur = today.strftime("%Y-%m")
    options = [add_months(cur, i) for i in range(-6, 4)]
    plan_month = st.selectbox("编制月份", options, index=6)

    plan = load_plan(cid, plan_month)
    if plan is None:
        st.info(f"本期({plan_month}编制)计划尚未生成。")
        if editable:
            if st.button("🚀 生成滚动资金计划", type="primary", width="stretch"):
                plan = generate_plan(cid, plan_month)
                save_plan(plan)
                st.toast("✅ 计划已生成", icon="✅")
                st.rerun()
        else:
            st.caption("请联系资金计划专员生成。")
        return

    # ---------------- 汇总表 ----------------
    st.markdown(f"#### {plan_month} 编制 · 未来 {n} 个月滚动资金计划")
    df, styled = plan_summary(plan)
    st.dataframe(styled, width="stretch")

    # ---------------- 指标卡 ----------------
    rows = plan["rows"]
    worst = max(rows, key=lambda r: r["gap"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"期末现金({rows[-1]['month']})", f"{rows[-1]['closing']:,.2f} 万元",
              delta=f"净流量 {rows[-1]['net']:,.2f}")
    m2.metric("三个月累计净流量", f"{sum(r['net'] for r in rows):,.2f} 万元")
    m3.metric("最大缺口", f"{worst['gap']:,.2f} 万元" if worst["gap"] > 0 else "✅ 无缺口",
              delta=worst["month"], delta_color="inverse")
    m4.metric("安全底线", f"{plan['safety_line']:,.2f} 万元")

    # ---------------- 图表 ----------------
    st.plotly_chart(plan_chart(plan), width="stretch")

    # ---------------- 分月明细 ----------------
    with st.expander("🔍 查看分月明细"):
        for r in rows:
            tag = "　✅实际数" if r["is_actual"] else ""
            with st.expander(f"{r['month']} · 流入 {r['inflow']:,.2f} / 流出 {r['outflow']:,.2f} "
                             f"/ 期末 {r['closing']:,.2f} 万元{tag}"):
                ci, co = st.columns(2)
                ci.markdown("**现金流入明细**")
                ci.dataframe(pd.DataFrame(r["details"].get("inflows", [])), width="stretch")
                co.markdown("**现金流出明细**")
                co.dataframe(pd.DataFrame(r["details"].get("outflows", [])), width="stretch")

    # ---------------- 操作按钮 ----------------
    issues = validate_company_data(cid, plan["months"])
    if editable:
        c1, c2 = st.columns(2)
        excel_bytes = build_excel(company_name, plan, plan.get("diagnosis_text", ""), issues)
        c1.download_button("📥 导出Excel", excel_bytes,
                           f"滚动资金计划_{company_name}_{plan_month}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width="stretch")
        if c2.button("🔄 重新生成(含最新实际数滚动更新)", width="stretch",
                     help="重新读取全部最新数据编制计划; 若已在「数据录入-实际数」填写当月实际数, "
                          "将自动用实际数替换预测并滚动更新"):
            plan = generate_plan(cid, plan_month)
            save_plan(plan)
            st.toast("✅ 计划已重新生成", icon="✅")
            st.rerun()

    # ---------------- 数据校验 ----------------
    with st.expander(f"🔎 数据校验({len(issues)}条)"):
        if issues:
            fb = validation_feedback(company_name, issues)
            st.markdown(fb)
        else:
            st.success("数据校验通过, 未发现明显异常。")

    # ---------------- 智能诊断与报告 ----------------
    st.markdown("#### 🧠 智能诊断与报告(DeepSeek + 规则引擎)")
    if plan.get("diagnosis_text"):
        st.markdown(plan["diagnosis_text"])
        if editable and st.button("🔄 重新生成诊断", key="regen_diag"):
            _run_diagnosis(cid, company_name, plan, issues, plan_month)
    elif editable:
        if st.button("🤖 生成智能诊断", type="primary"):
            _run_diagnosis(cid, company_name, plan, issues, plan_month)
    else:
        st.caption("诊断尚未生成, 请联系资金计划专员。")

    if plan.get("report_text"):
        with st.expander("📄 文字版资金计划说明(管理层汇报)"):
            st.markdown(plan["report_text"])
    elif editable and st.button("📝 生成文字报告"):
        with st.spinner("大模型撰写中…"):
            report = generate_report(company_name, plan, plan.get("diagnosis_text", ""))
        save_diagnosis(cid, plan_month, plan.get("diagnosis_text", ""), report)
        st.rerun()


def _run_diagnosis(cid, company_name, plan, issues, plan_month):
    with st.spinner("大模型分析中…"):
        diag = gap_diagnosis(company_name, plan, issues)
    save_diagnosis(cid, plan_month, diag)
    st.rerun()


# ---------------------------------------------------------------------------
# 展示辅助
# ---------------------------------------------------------------------------
def _ordered_cats(plan, kind):
    cats = []
    for r in plan["rows"]:
        for d in r["details"].get(kind, []):
            if d.get("category") not in cats:
                cats.append(d["category"])
    return cats


def _cat_values(plan, kind, cat):
    return [round(sum(d.get("amount", 0) for d in r["details"].get(kind, [])
                      if d.get("category") == cat), 2) for r in plan["rows"]]


def plan_summary(plan):
    rows = plan["rows"]
    cols = [f"{r['month']}({'实际' if r['is_actual'] else '预测'})" for r in rows]
    data = {"期初现金余额": [r["opening"] for r in rows]}
    for cat in _ordered_cats(plan, "inflows"):
        data[f"　{cat}"] = _cat_values(plan, "inflows", cat)
    data["一、现金流入合计"] = [r["inflow"] for r in rows]
    for cat in _ordered_cats(plan, "outflows"):
        data[f"　{cat}"] = _cat_values(plan, "outflows", cat)
    data["二、现金流出合计"] = [r["outflow"] for r in rows]
    data["三、现金净流量"] = [r["net"] for r in rows]
    data["四、期末现金余额"] = [r["closing"] for r in rows]
    data["五、现金安全底线"] = [r["safety_line"] for r in rows]
    data["六、资金缺口"] = [r["gap"] for r in rows]
    df = pd.DataFrame(data, index=cols).T

    safety = plan["safety_line"]

    def _row_style(s):
        styles = []
        for v in s.values:
            if s.name == "四、期末现金余额" and isinstance(v, (int, float)) and v < safety:
                styles.append("color:#c62828;font-weight:bold;background-color:#fdecea")
            elif s.name == "六、资金缺口" and isinstance(v, (int, float)) and v > 0:
                styles.append("color:#c62828;font-weight:bold;background-color:#fdecea")
            elif s.name in ("一、现金流入合计", "二、现金流出合计", "三、现金净流量"):
                styles.append("font-weight:bold")
            else:
                styles.append("")
        return styles

    styled = df.style.apply(_row_style, axis=1).format("{:,.2f}")
    return df, styled


def plan_chart(plan):
    rows = plan["rows"]
    months = [r["month"] for r in rows]
    fig = go.Figure()
    fig.add_bar(name="现金流入", x=months, y=[r["inflow"] for r in rows], marker_color="#4472C4")
    fig.add_bar(name="现金流出", x=months, y=[r["outflow"] for r in rows], marker_color="#ED7D31")
    fig.add_scatter(name="期末现金", x=months, y=[r["closing"] for r in rows],
                    mode="lines+markers", line=dict(color="#70AD47", width=3))
    fig.add_hline(y=plan["safety_line"], line_dash="dash", line_color="#C00000",
                  annotation_text=f"安全底线 {plan['safety_line']:,.0f}", annotation_position="top left")
    fig.update_layout(barmode="group", height=420,
                      margin=dict(l=20, r=20, t=50, b=20),
                      yaxis_title="万元",
                      legend=dict(orientation="h", y=1.15, x=0))
    return fig
