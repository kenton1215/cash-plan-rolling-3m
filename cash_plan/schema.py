"""数据表结构与字段定义(数据录入页与Excel模板导入导出共用)

字段类型 kind:
  text  文本 / num 小数 / int 整数 / bool 是-否 / rate 比例0~1
  month 月份YYYY-MM / date 日期YYYY-MM-DD (编辑时按文本, 导入时严格校验格式)
"""
from . import models as M

# (模块key, 模块标签, 可维护角色)
MODULES = [
    ("collection", "💵 销售回款", {"sales", "finance", "company_admin"}),
    ("bill_other", "💱 票据与其他流入", {"finance", "company_admin"}),
    ("purchase", "🛒 采购付现", {"purchase", "finance", "company_admin"}),
    ("payroll", "👥 人工付现", {"hr", "finance", "company_admin"}),
    ("expense", "🧾 费用计划", {"rd", "admin_dept", "finance", "company_admin"}),
    ("capex", "🏦 资本/税务/筹资", {"finance", "company_admin"}),
    ("actual", "📌 实际数与期初现金", {"finance", "company_admin"}),
]
MODULES_BY_KEY = {m[0]: m for m in MODULES}

# (模块key, 表名/工作表名, 模型, 字段列表[(属性, 中文列名, kind)], 填写说明)
TABLES = [
    ("collection", "应收账款台账", M.Receivable, [
        ("customer", "客户名称", "text"), ("contract_no", "合同号", "text"),
        ("amount", "应收金额(万元)", "num"), ("credit_days", "账期天数", "int"),
        ("due_date", "到期日(YYYY-MM-DD)", "date"), ("history_rate", "历史回款率(0~1)", "rate"),
        ("note", "备注", "text")],
     "回款预测 = 应收金额 × 历史回款率, 于到期日所在月计入现金流入。"),
    ("collection", "销售订单与预测订单", M.SalesOrder, [
        ("customer", "客户", "text"), ("order_no", "订单号", "text"),
        ("amount", "订单金额(万元)", "num"), ("sign_date", "签订日期", "date"),
        ("ship_month", "预计发货月(YYYY-MM)", "month"), ("credit_days", "信用期(天)", "int"),
        ("win_prob", "赢单概率(0~1)", "rate"), ("is_forecast", "预测订单(是/否)", "bool"),
        ("note", "备注", "text")],
     "已签订单按100%计入回款(发货月+信用期推算出回款月); 预测订单按赢单概率加权。"),
    ("bill_other", "应收票据", M.NoteBill, [
        ("bill_type", "票据类型", "text"), ("bill_no", "票号", "text"),
        ("amount", "票面金额(万元)", "num"), ("due_date", "到期日(YYYY-MM-DD)", "date"),
        ("accept_rate", "兑付概率(0~1)", "rate"), ("note", "备注", "text")],
     "银行承兑一般按100%; 商业承兑请按兑付风险打折(如0.9)。"),
    ("bill_other", "其他现金流入", M.OtherInflow, [
        ("item", "流入项目(如出口退税)", "text"), ("month", "流入月份(YYYY-MM)", "month"),
        ("amount", "金额(万元)", "num"), ("note", "备注", "text")],
     "出口退税、政府补贴、利息收入、资产处置等, 按预计流入月份填写。"),
    ("purchase", "应付账款台账", M.Payable, [
        ("supplier", "供应商", "text"), ("po_no", "采购单号", "text"),
        ("amount", "应付金额(万元)", "num"), ("due_date", "到期日(YYYY-MM-DD)", "date"),
        ("note", "备注", "text")],
     "按到期日所在月计入现金流出。"),
    ("purchase", "采购预测(排产推算)", M.PurchaseForecast, [
        ("material", "物料/用途", "text"), ("qty", "数量", "num"),
        ("unit_price", "单价(万元)", "num"), ("purchase_month", "采购月份(YYYY-MM)", "month"),
        ("credit_days", "账期(天,0=现款)", "int"), ("prepay_ratio", "预付比例(0~1)", "rate"),
        ("is_rd", "研发试产(是/否)", "bool"), ("note", "备注", "text")],
     "采购额 = 数量×单价; 预付部分在采购月支付, 余款按账期递延; 研发试产采购单独列示(通常现款)。"),
    ("payroll", "工资社保计划", M.PayrollPlan, [
        ("month", "月份(YYYY-MM)", "month"), ("salary", "应发工资(万元)", "num"),
        ("social", "社保公积金(万元)", "num"), ("bonus", "奖金(万元)", "num"),
        ("note", "备注", "text")],
     "每月一行(刚性支出); 金额 = 应发工资 + 社保公积金 + 奖金; 同一月份重复导入时按最新值更新。"),
    ("expense", "费用计划", M.ExpensePlan, [
        ("department", "部门", "text"), ("item", "费用项目", "text"),
        ("month", "月份(YYYY-MM)", "month"), ("amount", "金额(万元)", "num"),
        ("is_cash", "是否付现(是/否)", "bool"), ("note", "备注", "text")],
     "「是否付现」=否的项目(如折旧、摊销)自动剔除, 不计入现金流出。部门填: 研发/销售/管理/行政/财务。"),
    ("capex", "资本支出计划", M.CapexPlan, [
        ("project", "项目", "text"), ("amount", "金额(万元)", "num"),
        ("pay_month", "付款月份(YYYY-MM)", "month"), ("note", "备注", "text")],
     "设备购置、厂房装修、软件采购等, 按预计付款月份填写。"),
    ("capex", "税务计划", M.TaxPlan, [
        ("tax_type", "税种", "text"), ("period", "所属期间", "text"),
        ("amount", "应缴金额(万元)", "num"), ("pay_month", "缴纳月份(YYYY-MM)", "month"),
        ("note", "备注", "text")],
     "增值税、企业所得税等, 注意季度末与年度汇算清缴时点。"),
    ("capex", "贷款与筹资", M.LoanSchedule, [
        ("bank", "银行/来源", "text"), ("direction", "类型(borrow/repay)", "text"),
        ("amount", "金额(万元)", "num"), ("month", "发生月份(YYYY-MM)", "month"),
        ("note", "备注", "text")],
     "borrow=新增借款(现金流入); repay=还款(现金流出)。"),
    ("actual", "期初现金余额", M.OpeningCash, [
        ("month", "月份(YYYY-MM)", "month"), ("amount", "期初现金余额(万元)", "num"),
        ("note", "备注", "text")],
     "每月一行: 该月月初公司实际可用现金。仅首月需要, 其后各月期初 = 上月期末; 同一月份重复导入时按最新值更新。"),
    ("actual", "月度实际数(滚动替换预测)", M.MonthActual, [
        ("month", "月份(YYYY-MM)", "month"), ("opening_cash", "期初实际现金(万元)", "num"),
        ("inflow", "实际现金流入(万元)", "num"), ("outflow", "实际现金流出(万元)", "num"),
        ("closing_cash", "期末实际现金(万元)", "num"), ("note", "备注", "text")],
     "填写后, 该月计划将直接采用实际数(不再使用预测); 期末实际现金自动作为下月期初现金; "
     "同一月份重复导入时只更新非空单元格。"),
]

TABLE_BY_SHEET = {t[1]: t for t in TABLES}

# 按(企业, 月份)唯一 → 导入时更新覆盖; 其余表为追加模式(重复行自动跳过)
UNIQUE_MONTH_TABLES = {M.PayrollPlan, M.OpeningCash, M.MonthActual}
