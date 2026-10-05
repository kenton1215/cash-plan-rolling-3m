"""智能体层: 数据校验解读 / 缺口诊断 / 报告生成 / 情景解读

架构原则: 规则引擎负责"计算与校验"(结果稳定可靠), 大模型(DeepSeek)负责
"理解、解释、建议"。未配置API Key或调用失败时自动降级为规则引擎版文本,
系统功能不受影响。
"""
import json

from .engine import rule_suggestions
from .llm import get_llm

SYSTEM_PROMPT = (
    "你是资深的企业财务资金计划专家, 长期服务于研产销一体企业(研发投入大、生产备料占用资金、"
    "销售有账期)。你的输出使用简体中文, 简洁、专业、可执行, 金额单位均为万元。"
    "只输出结论与建议, 不要复述输入数据。"
)


def _compact_rows(plan):
    return [{"期间": r["month"], "性质": "实际数" if r["is_actual"] else "预测数",
             "期初": r["opening"], "流入": r["inflow"], "流出": r["outflow"],
             "净流量": r["net"], "期末": r["closing"], "安全底线": r["safety_line"],
             "缺口": r["gap"]} for r in plan["rows"]]


def validation_feedback(company_name, issues):
    """数据校验问题的解读与处理建议"""
    if not issues:
        return "✅ 数据校验通过, 未发现明显异常。"
    fallback = "数据校验问题清单:\n" + "\n".join(
        f"- [{i['level']}] {i['module']}: {i['message']}" for i in issues[:15])
    llm = get_llm()
    if not llm.available:
        return fallback
    user = (
        f"企业「{company_name}」月度资金计划数据校验发现以下问题:\n"
        f"{json.dumps([{'模块': i['module'], '级别': i['level'], '问题': i['message']} for i in issues[:15]], ensure_ascii=False)}\n"
        f"请用简洁中文说明: 1) 每个问题对资金计划的影响 2) 建议由哪个部门如何处理。"
    )
    out = llm.chat(SYSTEM_PROMPT, user, max_tokens=1500)
    return out.strip() if out else fallback


def gap_diagnosis(company_name, plan, issues):
    """缺口归因分析 + 应对行动方案 (LLM增强, 规则降级)"""
    suggs = rule_suggestions(plan)
    worst = max(plan["rows"], key=lambda r: r["gap"]) if plan["rows"] else None
    if worst and worst["gap"] > 0:
        head = (f"⚠️ 资金缺口预警: {worst['month']} 期末现金 {worst['closing']:,.2f} 万元, "
                f"低于安全底线 {worst['safety_line']:,.2f} 万元, 缺口 {worst['gap']:,.2f} 万元。")
    else:
        head = "✅ 资金面安全: 未来各月期末现金均高于安全底线。"
    fallback = head + "\n\n规则建议:\n" + "\n".join(
        f"{i + 1}. {s['action']} —— {s['impact']}(优先级: {s['priority']})"
        for i, s in enumerate(suggs))
    llm = get_llm()
    if not llm.available:
        return fallback
    user = (
        f"企业「{company_name}」的三个月滚动资金计划如下(单位万元):\n"
        f"{json.dumps(_compact_rows(plan), ensure_ascii=False)}\n\n"
        f"数据校验问题: {json.dumps([i['message'] for i in issues], ensure_ascii=False)}\n\n"
        f"规则引擎初步建议: {json.dumps(suggs, ensure_ascii=False)}\n\n"
        f"请输出:\n1. 缺口归因: 导致资金缺口的主要原因(结合研发/生产/销售特性)\n"
        f"2. 风险提示: 最需要警惕的风险点\n"
        f"3. 行动方案: 按优先级给出具体可执行的行动(含金额与时间)\n"
        f"如资金安全, 请简要说明维持策略。"
    )
    out = llm.chat(SYSTEM_PROMPT, user, max_tokens=2000)
    return out.strip() if out else fallback


def generate_report(company_name, plan, diagnosis_text=""):
    """生成管理层可读的资金计划说明"""
    rows = plan["rows"]
    total_net = round(sum(r["net"] for r in rows), 2)
    worst = max(rows, key=lambda r: r["gap"])
    month_lines = "\n".join(
        f"- {r['month']}({'实际' if r['is_actual'] else '预测'}): "
        f"流入 {r['inflow']:,.2f}, 流出 {r['outflow']:,.2f}, 净流量 {r['net']:,.2f}, "
        f"期末现金 {r['closing']:,.2f}, 缺口 {r['gap']:,.2f}"
        for r in rows)
    verdict = (f"资金存在缺口, 最大缺口 {worst['gap']:,.2f} 万元({worst['month']}), "
               f"需提前安排融资或压缩支出。" if worst["gap"] > 0
               else "资金面安全, 期末现金均高于安全底线。")
    fallback = (
        f"# {company_name} · {plan['plan_month']}编制 三个月滚动资金计划说明\n\n"
        f"## 一、总体判断\n未来三个月累计净现金流量 {total_net:,.2f} 万元, {verdict}\n\n"
        f"## 二、分月要点\n{month_lines}\n\n"
        f"## 三、应对建议\n{diagnosis_text or '见缺口诊断页。'}\n")
    llm = get_llm()
    if not llm.available:
        return fallback
    user = (
        f"请为管理层撰写企业「{company_name}」的{plan['plan_month']}编制·三个月滚动资金计划说明。\n"
        f"计划数据(单位万元):\n{json.dumps(_compact_rows(plan), ensure_ascii=False)}\n\n"
        f"智能诊断结论:\n{diagnosis_text or '无'}\n\n"
        f"要求: 使用Markdown, 包含「总体判断 / 分月要点 / 风险提示 / 行动建议」四个部分, "
        f"语言面向管理层, 突出资金安全与行动事项。"
    )
    out = llm.chat(SYSTEM_PROMPT, user, max_tokens=2500)
    return out.strip() if out else fallback


def interpret_scenario(company_name, plan, sim_rows, adjustments):
    """情景模拟结果解读"""
    lines = []
    for r, s in zip(plan["rows"], sim_rows):
        if (r["inflow"], r["outflow"]) != (s["inflow"], s["outflow"]):
            lines.append(f"- {r['month']}: 期末现金 {r['closing']:,.2f} → {s['closing']:,.2f} 万元, "
                         f"缺口 {r['gap']:,.2f} → {s['gap']:,.2f} 万元")
    fallback = "情景模拟结果:\n" + ("\n".join(lines) if lines else "- 未输入任何调整项")
    llm = get_llm()
    if not llm.available:
        return fallback
    user = (
        f"企业「{company_name}」进行了资金计划情景模拟。\n"
        f"调整动作: {json.dumps(adjustments, ensure_ascii=False)}\n"
        f"原计划(单位万元): {json.dumps(_compact_rows(plan), ensure_ascii=False)}\n"
        f"模拟结果: {json.dumps([{'期间': s['month'], '期末': s['closing'], '缺口': s['gap'],
                                 '流入': s['inflow'], '流出': s['outflow']} for s in sim_rows], ensure_ascii=False)}\n"
        f"请用简洁中文解读该情景的影响、可行性与建议(不超过200字)。"
    )
    out = llm.chat(SYSTEM_PROMPT, user, max_tokens=600)
    return out.strip() if out else fallback
