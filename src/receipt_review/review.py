"""识别风险提示，不代表税务审核、真伪鉴定或付款批准。"""
from datetime import date
from receipt_review.schemas import FIELD_NAMES

MESSAGES = {
    'ambiguous_total': '发现不同的总金额候选，请核对原图',
    'ambiguous_date': '日/月顺序存在歧义，当前暂按 DD/MM/YYYY',
    'multiple_dates': '票据中存在多个日期',
    'heuristic_company': '商家来自顶部文字规则，需要人工确认',
    'heuristic_address': '地址来自关键词规则，可能漏掉续行',
}


def inspect(fields, lines, *, today=None):
    today = today or date.today()
    available = {line.id for line in lines}
    issues = []
    for name in FIELD_NAMES:
        item = fields[name]
        if item.value is None:
            issues.append({'field': name, 'code': 'missing', 'message': '未提取到字段'})
            continue
        if not item.evidence or not set(item.evidence) <= available:
            raise ValueError('字段引用不存在的 OCR 证据')
        if item.ocr_score is not None and item.ocr_score < .85:
            issues.append({'field': name, 'code': 'low_ocr_score', 'message': '证据文字识别分数低，请查看原图'})
        for warning in item.warnings:
            issues.append({'field': name, 'code': warning, 'message': MESSAGES[warning]})
        if name == 'date' and date.fromisoformat(item.value) > today:
            issues.append({'field': name, 'code': 'future_date', 'message': '日期晚于当前日期'})
    return issues
