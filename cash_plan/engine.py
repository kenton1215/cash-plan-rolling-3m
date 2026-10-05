"""核心计算引擎: 规则化编制三个月滚动资金计划 (金额单位: 万元)

运算逻辑(每月):
  现金流入 = 应收到期×历史回款率 + 订单回款(发货月+账期)×概率 + 票据到期×兑付率
           + 其他流入 + 新增借款
  现金流出 = 到期应付 + 采购付现(预付当月/余款按账期递延) + 研发试产现款
           + 工资社保 + 费用付现 + 资本支出 + 税负 + 偿还借款
  净流量 = 流入 - 流出
  期末现金 = 期初现金 + 净流量
  资金缺口 = max(0, 安全底线 - 期末现金)

滚动机制: 每月月末用实际数(MonthActual)替换预测数, 期末实际现金自动结转下月期初,
向前滚动补充新的第N月预测。
"""
import json
import math

from . import models as M
from .database import session_scope


def R2(x):
    return round(float(x or 0), 2)


def add_months(month_str, n):
    """月份字符串 YYYY-MM 加减 n 个月"""
    try:
        y, m = (int(p) for p in str(month_str).split("-")[:2])
    except Exception:
        return ""
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def month_of(date_str):
    """日期字符串 YYYY-MM-DD -> 所属月份 YYYY-MM"""
    s = (date_str or "").strip()
    return s[:7] if len(s) >= 7 and s[4] == "-" else ""


def collect_month(ship_month, credit_days):
    """订单回款月 = 发货月 + 账期(不足30天按0.5月保守进整)"""
    if not ship_month:
        return ""
    cd = int(credit_days or 0)
    return add_months(ship_month, math.ceil(cd / 30.0)) if cd > 0 else ship_month


# ---------------------------------------------------------------------------
# 单月预测
# ---------------------------------------------------------------------------
def forecast_month(company_id, month, sess):
    """按规则引擎推算某月现金流入/流出明细"""
    inflows, outflows = [], []

    # ---- 现金流入 ----
    # 1. 应收账款到期回款 = 金额 × 历史回款率
    for r in sess.query(M.Receivable).filter(M.Receivable.company_id == company_id).all():
        if month_of(r.due_date) == month:
            rate = r.history_rate if r.history_rate is not None else 1.0
            amt = R2((r.amount or 0) * rate)
            if amt > 0:
                inflows.append({"category": "应收回款", "item": f"{r.customer}(合同{r.contract_no or '-'})",
                                "amount": amt, "note": f"应收{r.amount or 0}万×回款率{rate:.0%}"})
    # 2. 订单回款: 已签订单按100%, 预测订单按赢单概率加权
    for o in sess.query(M.SalesOrder).filter(M.SalesOrder.company_id == company_id).all():
        cm = collect_month(o.ship_month, o.credit_days)
        if cm == month:
            prob = (o.win_prob if o.win_prob is not None else 1.0) if o.is_forecast else 1.0
            amt = R2((o.amount or 0) * prob)
            if amt > 0:
                cat = "预测订单回款" if o.is_forecast else "订单回款"
                note = f"发货{o.ship_month}+账期{o.credit_days}天"
                if o.is_forecast:
                    note += f"×赢单率{prob:.0%}"
                inflows.append({"category": cat, "item": f"{o.customer}(单号{o.order_no or '-'})",
                                "amount": amt, "note": note})
    # 3. 票据到期托收
    for b in sess.query(M.NoteBill).filter(M.NoteBill.company_id == company_id).all():
        if month_of(b.due_date) == month:
            rate = b.accept_rate if b.accept_rate is not None else 1.0
            amt = R2((b.amount or 0) * rate)
            if amt > 0:
                inflows.append({"category": "票据到期", "item": f"{b.bill_type}(票号{b.bill_no or '-'})",
                                "amount": amt, "note": f"票面{b.amount or 0}万×兑付率{rate:.0%}"})
    # 4. 其他流入 (退税/补贴/利息等)
    for x in sess.query(M.OtherInflow).filter(M.OtherInflow.company_id == company_id).all():
        if x.month == month and (x.amount or 0) > 0:
            inflows.append({"category": "其他流入", "item": x.item or "其他", "amount": R2(x.amount), "note": x.note or ""})
    # 5. 新增借款
    for l in sess.query(M.LoanSchedule).filter(M.LoanSchedule.company_id == company_id).all():
        if l.direction == "borrow" and l.month == month and (l.amount or 0) > 0:
            inflows.append({"category": "新增借款", "item": l.bank or "银行", "amount": R2(l.amount), "note": l.note or ""})

    # ---- 现金流出 ----
    # 1. 到期应付账款
    for p in sess.query(M.Payable).filter(M.Payable.company_id == company_id).all():
        if month_of(p.due_date) == month and (p.amount or 0) > 0:
            outflows.append({"category": "到期应付", "item": f"{p.supplier}(单号{p.po_no or '-'})",
                             "amount": R2(p.amount), "note": f"到期日{p.due_date}"})
    # 2. 采购预测: 预付部分当月支付, 余款按账期递延; 研发试产单独列示
    for pf in sess.query(M.PurchaseForecast).filter(M.PurchaseForecast.company_id == company_id).all():
        if not pf.purchase_month:
            continue
        total = R2((pf.qty or 0) * (pf.unit_price or 0))
        if total <= 0:
            continue
        prepay = R2(total * (pf.prepay_ratio if pf.prepay_ratio is not None else 0))
        rest = R2(total - prepay)
        cd = int(pf.credit_days or 0)
        rest_month = add_months(pf.purchase_month, math.ceil(cd / 30.0)) if cd > 0 else pf.purchase_month
        rd_tag = "研发试产付现" if pf.is_rd else None
        if pf.purchase_month == month and prepay > 0:
            cat = rd_tag or "采购预付"
            outflows.append({"category": cat, "item": f"{pf.material}(预付)",
                             "amount": prepay, "note": f"总额{total}万×预付比例{(pf.prepay_ratio or 0):.0%}"})
        if rest_month == month and rest > 0:
            cat = rd_tag or "采购付现"
            outflows.append({"category": cat, "item": f"{pf.material}(余款)",
                             "amount": rest, "note": f"总额{total}万, 账期{cd}天递延"})
    # 3. 工资社保奖金
    for w in sess.query(M.PayrollPlan).filter(M.PayrollPlan.company_id == company_id,
                                              M.PayrollPlan.month == month).all():
        total = R2((w.salary or 0) + (w.social or 0) + (w.bonus or 0))
        if total > 0:
            outflows.append({"category": "工资社保", "item": "工资+社保+奖金",
                             "amount": total, "note": w.note or ""})
    # 4. 费用付现 (非付现项如折旧摊销自动剔除)
    for e in sess.query(M.ExpensePlan).filter(M.ExpensePlan.company_id == company_id,
                                              M.ExpensePlan.month == month,
                                              M.ExpensePlan.is_cash == True).all():  # noqa: E712
        if (e.amount or 0) > 0:
            outflows.append({"category": "费用付现", "item": f"{e.department or '-'}-{e.item or ''}",
                             "amount": R2(e.amount), "note": e.note or ""})
    # 5. 资本支出
    for c in sess.query(M.CapexPlan).filter(M.CapexPlan.company_id == company_id,
                                            M.CapexPlan.pay_month == month).all():
        if (c.amount or 0) > 0:
            outflows.append({"category": "资本支出", "item": c.project or "项目",
                             "amount": R2(c.amount), "note": c.note or ""})
    # 6. 税负
    for t in sess.query(M.TaxPlan).filter(M.TaxPlan.company_id == company_id,
                                          M.TaxPlan.pay_month == month).all():
        if (t.amount or 0) > 0:
            outflows.append({"category": "税负", "item": t.tax_type or "税费",
                             "amount": R2(t.amount), "note": f"所属期间{t.period or '-'}"})
    # 7. 偿还借款
    for l in sess.query(M.LoanSchedule).filter(M.LoanSchedule.company_id == company_id).all():
        if l.direction == "repay" and l.month == month and (l.amount or 0) > 0:
            outflows.append({"category": "偿还借款", "item": l.bank or "银行",
                             "amount": R2(l.amount), "note": l.note or ""})

    return {"inflows": inflows, "outflows": outflows,
            "inflow_total": R2(sum(d["amount"] for d in inflows)),
            "outflow_total": R2(sum(d["amount"] for d in outflows))}


# ---------------------------------------------------------------------------
# 滚动计划编制
# ---------------------------------------------------------------------------
def generate_plan(company_id, plan_month, rolling_months=None):
    """编制 plan_month 起未来 rolling_months 个月的滚动资金计划"""
    with session_scope() as sess:
        rc = sess.query(M.RollingConfig).filter(M.RollingConfig.company_id == company_id).first()
        n = rolling_months or (rc.rolling_months if rc else 3)
        sc = sess.query(M.SafetyConfig).filter(M.SafetyConfig.company_id == company_id).first()
        safety_line = R2(sc.safety_line if sc else 0)

        months = [add_months(plan_month, i) for i in range(n)]
        prev_month = add_months(plan_month, -1)
        act_map = {a.month: a for a in sess.query(M.MonthActual).filter(
            M.MonthActual.company_id == company_id,
            M.MonthActual.month.in_(months + [prev_month])).all()}
        oc_map = {o.month: o for o in sess.query(M.OpeningCash).filter(
            M.OpeningCash.company_id == company_id).all()}

        rows = []
        prev_act = act_map.get(prev_month)
        for i, m in enumerate(months):
            act = act_map.get(m)
            if act is not None:
                # 已有实际数 → 直接替换预测数 (滚动更新)
                inflow, outflow = R2(act.inflow or 0), R2(act.outflow or 0)
                details = {
                    "inflows": [{"category": "实际数", "item": "当月实际现金流入",
                                 "amount": inflow, "note": "已用实际数替换预测数"}],
                    "outflows": [{"category": "实际数", "item": "当月实际现金流出",
                                  "amount": outflow, "note": "已用实际数替换预测数"}],
                }
                is_actual = True
            else:
                fc = forecast_month(company_id, m, sess)
                inflow, outflow = fc["inflow_total"], fc["outflow_total"]
                details = {"inflows": fc["inflows"], "outflows": fc["outflows"]}
                is_actual = False

            if i == 0:
                opening = None
                if act is not None and act.opening_cash is not None:
                    opening = R2(act.opening_cash)
                if opening is None:
                    oc = oc_map.get(m)
                    if oc is not None:
                        opening = R2(oc.amount)
                if opening is None and prev_act is not None and prev_act.closing_cash is not None:
                    opening = R2(prev_act.closing_cash)  # 上月期末实际现金结转
                opening = opening or 0.0
            else:
                opening = (R2(act.opening_cash) if (act is not None and act.opening_cash is not None)
                           else rows[-1]["closing"])

            net = R2(inflow - outflow)
            closing = R2(opening + net)
            gap = R2(max(0.0, safety_line - closing))
            rows.append({"month": m, "opening": opening, "inflow": inflow, "outflow": outflow,
                         "net": net, "closing": closing, "safety_line": safety_line,
                         "gap": gap, "is_actual": is_actual, "details": details})

        return {"company_id": company_id, "plan_month": plan_month, "months": months,
                "rows": rows, "safety_line": safety_line}


# ---------------------------------------------------------------------------
# 计划持久化
# ---------------------------------------------------------------------------
def save_plan(plan):
    """保存(覆盖)编制月计划; 保留已有诊断/报告文本"""
    with session_scope() as sess:
        q = sess.query(M.CashPlan).filter(M.CashPlan.company_id == plan["company_id"],
                                          M.CashPlan.plan_month == plan["plan_month"])
        old = q.first()
        keep_diag = old.diagnosis_text if old else ""
        keep_report = old.report_text if old else ""
        q.delete()
        for i, r in enumerate(plan["rows"]):
            sess.add(M.CashPlan(
                company_id=plan["company_id"], plan_month=plan["plan_month"],
                period_month=r["month"], month_index=i + 1,
                opening_cash=r["opening"], inflow=r["inflow"], outflow=r["outflow"],
                net=r["net"], closing_cash=r["closing"], safety_line=r["safety_line"],
                gap=r["gap"], is_actual=r["is_actual"],
                detail_json=json.dumps(r["details"], ensure_ascii=False),
                diagnosis_text=keep_diag, report_text=keep_report))


def load_plan(company_id, plan_month):
    with session_scope() as sess:
        rs = sess.query(M.CashPlan).filter(M.CashPlan.company_id == company_id,
                                           M.CashPlan.plan_month == plan_month) \
            .order_by(M.CashPlan.month_index).all()
        if not rs:
            return None
        rows = []
        for r in rs:
            try:
                details = json.loads(r.detail_json or "{}")
            except Exception:
                details = {}
            rows.append({"month": r.period_month, "opening": r.opening_cash,
                         "inflow": r.inflow, "outflow": r.outflow, "net": r.net,
                         "closing": r.closing_cash, "safety_line": r.safety_line,
                         "gap": r.gap, "is_actual": r.is_actual, "details": details})
        return {"company_id": company_id, "plan_month": plan_month,
                "months": [x["month"] for x in rows], "rows": rows,
                "safety_line": rows[0]["safety_line"],
                "diagnosis_text": rs[0].diagnosis_text or "",
                "report_text": rs[0].report_text or ""}


def save_diagnosis(company_id, plan_month, diagnosis_text="", report_text=None):
    with session_scope() as sess:
        for r in sess.query(M.CashPlan).filter(M.CashPlan.company_id == company_id,
                                               M.CashPlan.plan_month == plan_month).all():
            r.diagnosis_text = diagnosis_text or ""
            if report_text is not None:
                r.report_text = report_text


def list_plan_months(company_id):
    with session_scope() as sess:
        return [p[0] for p in sess.query(M.CashPlan.plan_month)
                .filter(M.CashPlan.company_id == company_id).distinct()
                .order_by(M.CashPlan.plan_month.desc()).all()]


# ---------------------------------------------------------------------------
# 数据校验 (规则版)
# ---------------------------------------------------------------------------
def validate_company_data(company_id, months):
    """校验数据完整性与逻辑一致性, 返回问题列表 [{level, module, message}]"""
    issues = []
    with session_scope() as sess:
        sc = sess.query(M.SafetyConfig).filter(M.SafetyConfig.company_id == company_id).first()
        if sc is None or not sc.safety_line:
            issues.append({"level": "warning", "module": "系统配置",
                           "message": "未配置现金安全底线, 缺口预警无法生效, 请在系统管理中配置"})
        has_opening = sess.query(M.OpeningCash).filter(M.OpeningCash.company_id == company_id,
                                                       M.OpeningCash.month == months[0]).first()
        has_actual = sess.query(M.MonthActual).filter(M.MonthActual.company_id == company_id,
                                                      M.MonthActual.month == months[0]).first()
        if not has_opening and not has_actual:
            issues.append({"level": "warning", "module": "期初现金",
                           "message": f"未设置 {months[0]} 期初现金余额, 首月期初将按0计算"})
        for r in sess.query(M.Receivable).filter(M.Receivable.company_id == company_id).all():
            if not r.due_date:
                issues.append({"level": "error", "module": "应收账款",
                               "message": f"客户「{r.customer or '-'}」应收 {r.amount or 0} 万缺少到期日"})
            if r.history_rate is None:
                issues.append({"level": "warning", "module": "应收账款",
                               "message": f"客户「{r.customer or '-'}」未填历史回款率, 暂按100%计入"})
            elif r.history_rate < 0.5:
                issues.append({"level": "warning", "module": "应收账款",
                               "message": f"客户「{r.customer or '-'}」历史回款率仅{r.history_rate:.0%}, 回款风险高"})
            elif r.history_rate > 1:
                issues.append({"level": "error", "module": "应收账款",
                               "message": f"客户「{r.customer or '-'}」历史回款率{r.history_rate}超过100%, 请修正"})
        for o in sess.query(M.SalesOrder).filter(M.SalesOrder.company_id == company_id).all():
            if not o.ship_month:
                issues.append({"level": "error", "module": "销售订单",
                               "message": f"订单「{o.order_no or o.customer or '-'}」缺少预计发货月份"})
            if o.is_forecast and o.win_prob is None:
                issues.append({"level": "warning", "module": "销售订单",
                               "message": f"预测订单「{o.order_no or o.customer or '-'}」未填赢单概率, 暂按100%计入"})
        for b in sess.query(M.NoteBill).filter(M.NoteBill.company_id == company_id).all():
            if b.bill_type and "商" in b.bill_type and (b.accept_rate or 1.0) < 1:
                issues.append({"level": "info", "module": "应收票据",
                               "message": f"商业承兑票据{b.bill_no or '-'}已按{b.accept_rate:.0%}兑付率打折, 建议关注承兑人信用"})
        for p in sess.query(M.Payable).filter(M.Payable.company_id == company_id).all():
            if not p.due_date:
                issues.append({"level": "error", "module": "应付账款",
                               "message": f"供应商「{p.supplier or '-'}」应付 {p.amount or 0} 万缺少到期日"})
        for pf in sess.query(M.PurchaseForecast).filter(M.PurchaseForecast.company_id == company_id).all():
            if not pf.purchase_month:
                issues.append({"level": "error", "module": "采购预测",
                               "message": f"物料「{pf.material or '-'}」缺少采购月份"})
            if pf.is_rd and not (pf.credit_days or 0):
                issues.append({"level": "info", "module": "研发试产",
                               "message": f"研发试产物料「{pf.material or '-'}」为现款采购, 已单独列示"})
        for m in months:
            has_payroll = sess.query(M.PayrollPlan).filter(M.PayrollPlan.company_id == company_id,
                                                           M.PayrollPlan.month == m).first()
            if not has_payroll:
                issues.append({"level": "warning", "module": "人工付现",
                               "message": f"{m} 缺少工资社保计划(刚性支出), 请人力部门补充"})
    return issues


# ---------------------------------------------------------------------------
# 缺口诊断 (规则版建议)
# ---------------------------------------------------------------------------
def rule_suggestions(plan):
    """基于缺口与明细数据生成规则版应对建议"""
    rows = plan["rows"]
    sugg = []
    if not any(r["gap"] > 0 for r in rows):
        return [{"action": "维持现状并持续监控", "impact": "未来各月期末现金均高于安全底线", "priority": "低"}]
    for r in rows:
        if r["gap"] <= 0:
            continue
        sugg.append({"action": f"{r['month']} 申请银行流贷/授信提款",
                     "impact": f"可补充资金缺口 {r['gap']:,.2f} 万元", "priority": "高"})
        for d in r["details"].get("inflows", []):
            if d.get("category") == "应收回款":
                sugg.append({"action": f"对{d['item']}提供现金折扣(如2/10, net30)加速回款",
                             "impact": f"可提前回收约 {d['amount']:,.2f} 万元", "priority": "中"})
            if d.get("category") == "票据到期":
                sugg.append({"action": f"将{d['item']}提前贴现",
                             "impact": f"可提前变现约 {d['amount']:,.2f} 万元(付贴现息)", "priority": "中"})
        for d in r["details"].get("outflows", []):
            if d.get("category") == "资本支出":
                sugg.append({"action": f"推迟/分期支付{d['item']}",
                             "impact": f"当月现金流出减少 {d['amount']:,.2f} 万元", "priority": "中"})
            if d.get("category") in ("到期应付", "采购付现"):
                sugg.append({"action": f"与{d['item']}协商付款展期30天",
                             "impact": f"当月现金流出减少 {d['amount']:,.2f} 万元", "priority": "中"})
    # 去重并控制条数
    seen, out = set(), []
    for s in sugg:
        k = (s["action"], s["impact"])
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out[:12]


# ---------------------------------------------------------------------------
# 情景模拟 (What-If)
# ---------------------------------------------------------------------------
def simulate_plan(plan, adjustments):
    """情景模拟: adjustments = {month: {collection, loan, capex_defer, payable_defer, expense_cut}}
    推迟/延后的支出顺延至下一月, 期末现金链重新计算"""
    import copy
    rows = copy.deepcopy(plan["rows"])
    carry = {}
    for i, r in enumerate(rows):
        m = r["month"]
        a = adjustments.get(m) or {}
        if m in carry:
            r["outflow"] = R2(r["outflow"] + carry[m])
        r["inflow"] = R2(r["inflow"] + (a.get("collection") or 0) + (a.get("loan") or 0))
        defer = (a.get("capex_defer") or 0) + (a.get("payable_defer") or 0) + (a.get("expense_cut") or 0)
        r["outflow"] = R2(r["outflow"] - defer)
        if defer > 0 and i < len(rows) - 1:
            nxt = rows[i + 1]["month"]
            carry[nxt] = R2(carry.get(nxt, 0) + defer)
    for i, r in enumerate(rows):
        r["net"] = R2(r["inflow"] - r["outflow"])
        if i == 0:
            r["closing"] = R2(r["opening"] + r["net"])
        else:
            r["closing"] = R2(rows[i - 1]["closing"] + r["net"])
        r["gap"] = R2(max(0.0, r["safety_line"] - r["closing"]))
    return rows
