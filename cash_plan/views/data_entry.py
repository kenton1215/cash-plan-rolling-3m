"""数据录入页: 各角色维护本部门数据, 支持Excel模板下载→离线填报→一键导入→在线编辑"""
import streamlit as st

from ..excel_io import build_template, import_excel, module_name
from ..schema import MODULES, MODULES_BY_KEY, TABLES
from .common import editor_table, require_login


def view():
    require_login()
    user = st.session_state["user"]
    cid = user["company_id"]
    role = user["role"]
    st.header("📥 业务数据录入")
    if role in ("finance", "company_admin"):
        st.info("💡 资金计划专员可代录所有模块; 业务部门可下载Excel模板离线填写, 由专员一键导入后再在线微调。"
                "所有金额单位为万元。")
    else:
        st.caption("维护本部门数据, 保存后资金计划专员即可编制计划; 也可下载本部门Excel模板离线填写, 交给专员导入。"
                   "所有金额单位为万元。")
    st.caption("💡 在线编辑方法: 直接修改单元格 → 点「保存」; 在表格最后一行填写新数据可新增; "
               "勾选「🗑 删除」并保存可删除该行。")

    _excel_section(role, cid)

    allowed_mods = [m for m in MODULES if role in m[2]]
    tabs = st.tabs([label for _, label, _ in allowed_mods])
    for (key, _label, _roles), tab in zip(allowed_mods, tabs):
        with tab:
            for _mk, sheet, model, fields, hint in [t for t in TABLES if t[0] == key]:
                editor_table(sheet, model, fields, cid, f"{key}_{sheet}", hint)


def _excel_section(role, cid):
    """Excel 模板下载(按业务模块) / 分模块一键导入"""
    allowed_mods = [m for m in MODULES if role in m[2]]
    with st.expander("📤 Excel模板下载 / 📥 一键导入(按业务模块)", expanded=True):
        st.markdown("**① 下载模板** — 按业务模块分别下载, 发给对应部门离线填写; 数据简单的也可直接在下方在线编辑。")
        cols = st.columns(3)
        for i, (key, label, _roles) in enumerate(allowed_mods):
            with cols[i % 3]:
                st.download_button(f"📤 {label}", build_template(role, key),
                                   file_name=f"{module_name(key)}_填报模板.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key=f"tpl_{key}", width="stretch")
        st.divider()
        st.markdown("**② 分模块导入** — 选择业务模块, 上传该模块已填写的Excel, 一键导入(逐行校验, 重复行自动跳过)。")
        c1, c2 = st.columns([1, 2])
        mod_key = c1.selectbox("业务模块", [m[0] for m in allowed_mods],
                               format_func=lambda k: MODULES_BY_KEY[k][1], key="imp_mod")
        uploaded = c2.file_uploader(f"上传「{MODULES_BY_KEY[mod_key][1]}」的xlsx文件",
                                    type=["xlsx"], key=f"imp_file_{mod_key}")
        if uploaded is not None and st.button("📥 一键导入", type="primary", key=f"imp_btn_{mod_key}"):
            with st.spinner("校验并导入中…"):
                report = import_excel(uploaded.getvalue(), cid, role, mod_key)
            st.session_state["import_report"] = report
            st.rerun()
        rep = st.session_state.get("import_report")
        if rep:
            st.markdown("**导入结果**")
            n_data = sum(1 for r in rep if r.get("added") or r.get("updated") or r.get("skipped"))
            n_empty = sum(1 for r in rep if r.get("empty"))
            st.caption(f"共处理 {len(rep)} 个工作表: {n_data} 个有数据, {n_empty} 个为空。")
            for r in rep:
                if r.get("empty"):
                    continue
                if r["errors"]:
                    with st.expander(f"⚠️ {r['sheet']}({len(r['errors'])}个问题, 错误行未导入)"):
                        st.write("\n".join(f"- {e}" for e in r["errors"]))
                else:
                    st.success(f"✅ {r['sheet']}: 新增 {r['added']} 行, 更新 {r['updated']} 行, "
                               f"跳过重复 {r['skipped']} 行")
            if st.button("清除导入结果提示", key="clear_imp"):
                st.session_state.pop("import_report", None)
                st.rerun()
