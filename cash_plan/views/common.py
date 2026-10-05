"""公共组件: 侧边栏导航 / 通用表格编辑器 / 编制日自动生成"""
import math
from datetime import date

import pandas as pd
import streamlit as st

from ..config import PAGE_ACCESS, ROLE_LABELS
from ..database import session_scope
from ..engine import add_months, generate_plan, load_plan, save_plan
from ..llm import get_llm

PAGES = [
    ("dashboard", "📊 首页看板"),
    ("data_entry", "📥 数据录入"),
    ("plan", "📈 资金计划"),
    ("diagnosis", "🧭 缺口诊断与情景模拟"),
    ("admin", "⚙️ 系统管理"),
]


def require_login():
    if not st.session_state.get("user"):
        st.warning("请先登录")
        st.stop()


def sidebar():
    """渲染侧边栏导航, 返回当前页面key"""
    user = st.session_state["user"]
    allowed = [(k, label) for k, label in PAGES if user["role"] in PAGE_ACCESS.get(k, set())]
    with st.sidebar:
        st.markdown("## 💰 滚动资金计划")
        st.caption(f"企业: {st.session_state.get('company_name', '')}")
        st.caption(f"用户: {user['name']}({ROLE_LABELS.get(user['role'], user['role'])})")
        llm = get_llm()
        st.caption("🤖 AI: " + ("DeepSeek 已连接" if llm.available else "未配置Key(规则引擎模式)"))
        st.divider()
        page = st.radio("导航", [k for k, _ in allowed], format_func=dict(allowed).get, key="nav_page")
        st.divider()
        if st.button("🚪 退出登录", width="stretch"):
            st.session_state.clear()
            st.rerun()
    return page


def ensure_due_plan(cid, role):
    """每月编制日(默认25日)及之后首次访问时, 自动生成下月编制的滚动计划"""
    if role not in ("finance", "company_admin"):
        return
    if st.session_state.get("_auto_gen_checked"):
        return
    st.session_state["_auto_gen_checked"] = True
    from .. import models as M
    with session_scope() as sess:
        rc = sess.query(M.RollingConfig).filter(M.RollingConfig.company_id == cid).first()
    update_day = rc.update_day if rc else 25
    today = date.today()
    if today.day < update_day:
        return
    cur = today.strftime("%Y-%m")
    pm = add_months(cur, 1)
    if load_plan(cid, pm) is None:
        plan = generate_plan(cid, pm)
        save_plan(plan)
        st.toast(f"🤖 已到编制日(每月{update_day}日), 系统已自动生成 {pm} 编制的滚动资金计划", icon="🤖")


def apply_editor_changes(model_cls, company_id, fields, edited_df):
    """将 data_editor 返回的DataFrame应用到数据库(增/改/删), 返回变更行数"""
    n_added = n_updated = n_deleted = 0
    with session_scope() as sess:
        existing = {o.id: o for o in sess.query(model_cls)
                    .filter(model_cls.company_id == company_id).all()}
        kept = set()
        for _, row in edited_df.iterrows():
            if bool(row.get("_del")):
                continue
            data = {}
            for attr, label, kind in fields:
                v = row.get(attr)
                if isinstance(v, float) and math.isnan(v):
                    v = None if kind in ("num", "int", "rate") else ""
                if kind == "int" and v is not None:
                    v = int(v)
                elif kind in ("num", "rate") and v is not None:
                    v = float(v)
                elif kind == "bool":
                    v = bool(v)
                elif kind in ("text", "month", "date"):
                    v = (str(v).strip() if v not in (None, "") else "")
                data[attr] = v
            rid = row.get("_id")
            if isinstance(rid, float) and math.isnan(rid):
                rid = None
            if rid in existing:
                kept.add(rid)
                for k, v in data.items():
                    setattr(existing[rid], k, v)
                n_updated += 1
            else:
                # 跳过全空的新行
                if all((data[k] in (None, "", 0, 0.0, False)) for k in data):
                    continue
                sess.add(model_cls(company_id=company_id, **data))
                n_added += 1
        for rid, o in existing.items():
            if rid not in kept:
                sess.delete(o)
                n_deleted += 1
    return n_added, n_updated, n_deleted


def editor_table(title, model_cls, fields, company_id, key, hint=""):
    """通用表格编辑器: 在线增删改 + 一键保存

    fields: [(属性名, 中文列名, kind)], kind ∈ {num 小数, int 整数, rate 比例0~1,
    text 文本, month 月份YYYY-MM, date 日期YYYY-MM-DD, bool 勾选}
    """
    st.markdown(f"**{title}**")
    if hint:
        st.caption(hint)

    with session_scope() as sess:
        objs = sess.query(model_cls).filter(model_cls.company_id == company_id).all()

    cols = [f[0] for f in fields] + ["_del", "_id"]
    rows_data = []
    for o in objs:
        d = {f[0]: getattr(o, f[0], None) for f in fields}
        d["_del"] = False
        d["_id"] = o.id
        rows_data.append(d)
    df = pd.DataFrame(rows_data, columns=cols)

    dtype_map = {"_del": "bool", "_id": "float64"}
    cc = {}
    for attr, label, kind in fields:
        if kind in ("num", "int", "rate"):
            dtype_map[attr] = "float64"
            fmt = "%d" if kind == "int" else "%.2f"
            cc[attr] = st.column_config.NumberColumn(label, format=fmt)
        elif kind == "bool":
            dtype_map[attr] = "bool"
            cc[attr] = st.column_config.CheckboxColumn(label)
        else:
            cc[attr] = st.column_config.TextColumn(label)
    df = df.astype(dtype_map)
    cc["_del"] = st.column_config.CheckboxColumn("🗑 删除")
    cc["_id"] = st.column_config.NumberColumn("ID", disabled=True)

    edited = st.data_editor(df, num_rows="dynamic", hide_index=True,
                            key=f"ed_{key}", column_config=cc, width="stretch")

    if st.button("💾 保存", key=f"save_{key}"):
        added, updated, deleted = apply_editor_changes(model_cls, company_id, fields, edited)
        st.success(f"「{title}」已保存(新增{added}/修改{updated}/删除{deleted})")
        st.rerun()
