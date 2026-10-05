"""缺口诊断与情景模拟页"""
import pandas as pd
import streamlit as st

from ..agents import gap_diagnosis, interpret_scenario, validation_feedback
from ..engine import (list_plan_months, load_plan, save_diagnosis, simulate_plan,
                      validate_company_data)
from .common import require_login

ADJ_LABELS = [
    ("collection", "加速回款(万元)", "现金折扣/保理贴现带来的当月新增流入"),
    ("loan", "新增贷款(万元)", "银行流贷/授信提款"),
    ("capex_defer", "推迟资本支出(万元)", "顺延至下月支付"),
    ("payable_defer", "延后采购付款(万元)", "与供应商协商展期, 顺延至下月"),
    ("expense_cut", "压缩费用(万元)", "削减非刚性费用支出"),
]


def view():
    require_login()
    user = st.session_state["user"]
    cid = user["company_id"]
    company_name = st.session_state.get("company_name", "")
    editable = user["role"] in ("finance", "company_admin")

    st.header("🧭 缺口诊断与情景模拟")

    months_list = list_plan_months(cid)
    if not months_list:
        st.info("暂无已生成计划, 请先在「资金计划」页生成。")
        return
    pm = st.selectbox("选择计划(编制月)", months_list)
    plan = load_plan(cid, pm)

    # ---------------- 1. 数据校验 ----------------
    with st.expander("🔎 数据校验结果", expanded=False):
        issues = validate_company_data(cid, plan["months"])
        if issues:
            st.dataframe(pd.DataFrame(issues), width="stretch", hide_index=True)
            st.markdown(validation_feedback(company_name, issues))
        else:
            st.success("数据校验通过, 未发现明显异常。")

    # ---------------- 2. 缺口诊断 ----------------
    st.markdown("#### 🧠 缺口诊断与应对建议")
    if plan.get("diagnosis_text"):
        st.markdown(plan["diagnosis_text"])
        if editable and st.button("🔄 重新生成诊断", key="diag_regen"):
            with st.spinner("大模型分析中…"):
                diag = gap_diagnosis(company_name, plan, issues)
            save_diagnosis(cid, pm, diag)
            st.rerun()
    else:
        if editable:
            if st.button("🤖 生成智能诊断", type="primary"):
                with st.spinner("大模型分析中…"):
                    diag = gap_diagnosis(company_name, plan, issues)
                save_diagnosis(cid, pm, diag)
                st.rerun()
        else:
            st.caption("诊断尚未生成, 请联系资金计划专员。")

    # ---------------- 3. 情景模拟 ----------------
    st.markdown("#### 🧪 情景模拟(What-If)")
    st.caption("输入假设调整动作, 系统重新计算未来各月期末现金与缺口(推迟/延后的支出顺延至下月)。")
    with st.form("scenario_form"):
        adjustments = {}
        for r in plan["rows"]:
            st.markdown(f"**{r['month']}**")
            cols = st.columns(len(ADJ_LABELS))
            month_adj = {}
            for (key, label, help_text), col in zip(ADJ_LABELS, cols):
                month_adj[key] = col.number_input(label, min_value=0.0, step=50.0,
                                                  value=0.0, key=f"sim_{r['month']}_{key}",
                                                  help=help_text)
            adjustments[r["month"]] = month_adj
        submitted = st.form_submit_button("🚀 运行模拟", type="primary")

    if submitted:
        sim_rows = simulate_plan(plan, adjustments)
        comp = pd.DataFrame({
            "指标": [f"{r['month']}期末现金" for r in plan["rows"]] +
                    [f"{r['month']}资金缺口" for r in plan["rows"]],
            "原计划": [r["closing"] for r in plan["rows"]] + [r["gap"] for r in plan["rows"]],
            "模拟结果": [s["closing"] for s in sim_rows] + [s["gap"] for s in sim_rows],
        })
        comp["差异"] = comp["模拟结果"] - comp["原计划"]
        st.dataframe(comp.style.format({c: "{:,.2f}" for c in comp.columns[1:]}),
                     width="stretch", hide_index=True)
        with st.spinner("大模型解读中…"):
            interp = interpret_scenario(company_name, plan, sim_rows, adjustments)
        st.markdown(interp)
