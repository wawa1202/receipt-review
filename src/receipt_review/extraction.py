"""可解释规则基线：返回字段以及产生该字段的 OCR 行证据。"""
import re

from receipt_review.schemas import FIELD_NAMES, Field, OCRLine
from receipt_review.normalize import money, receipt_date

DATE = re.compile(r'(?<!\d)(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{4})(?!\d)')
TOTAL = re.compile(r'^(?:grand\s+total|total(?:\s+(?:amount|due|payable))?|amount\s+due|balance\s+due|总金额|总计|合计)(?=\s|[:：]|\d|$)', re.I)
AMOUNT = re.compile(r'(?<![\w.,-])(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d.,])')
CURRENCY_AMOUNT = re.compile(r'^(?:(?:RM|MYR|USD|CNY|RMB|[$¥￥])\s*)?(?:\d{1,9}|\d{1,3}(?:,\d{3}){1,2})\.\d{2}$', re.I)
ADDRESS = re.compile(r'\b(?:jalan|street|road|avenue|lane|lorong|taman|lot|no\.)\b|路|街|巷', re.I)


def extract(lines: list[OCRLine]) -> dict[str, Field]:
    if len({line.id for line in lines}) != len(lines):
        raise ValueError('OCR 行 ID 重复')
    result = {name: Field(None) for name in FIELD_NAMES}
    if not lines:
        return result

    def field(value, sources, method, warnings=()):
        return Field(value, tuple(x.id for x in sources), min(x.score for x in sources), method, tuple(warnings))

    # 商家只取顶部的文本候选，明确标注这是一条位置启发式规则。
    for line in lines[:4]:
        if not DATE.search(line.text) and not TOTAL.search(line.text) and not ADDRESS.search(line.text) and re.search(r'[A-Za-z\u4e00-\u9fff]{2}', line.text) and not re.match(r'^(?:receipt|invoice|tax invoice|tel|date)\b', line.text, re.I):
            result['company'] = field(line.text.strip(), [line], 'top_text', ['heuristic_company'])
            break

    address_lines = []
    for index, line in enumerate(lines):
        if ADDRESS.search(line.text):
            address_lines = [line]
            for next_line in lines[index + 1:index + 4]:
                if re.search(r'\b(?:tel|gst|tax|receipt|invoice|date|total|cash)\b', next_line.text, re.I) or DATE.search(next_line.text) or AMOUNT.search(next_line.text):
                    break
                if ADDRESS.search(next_line.text) or re.search(r'\b\d{5}\b', next_line.text):
                    address_lines.append(next_line)
                else:
                    break
            break
    if address_lines:
        result['address'] = field(' '.join(x.text.strip() for x in address_lines), address_lines, 'address_keywords', ['heuristic_address'])

    dates = []
    for line in lines:
        for hit in DATE.findall(line.text):
            try:
                value, ambiguous = receipt_date(hit)
                dates.append((value, line, ambiguous))
            except ValueError:
                continue
    if dates:
        value, line, ambiguous = dates[0]
        warnings = ['ambiguous_date'] if ambiguous else []
        if len({x[0] for x in dates}) > 1:
            warnings.append('multiple_dates')
        result['date'] = field(value, [line], 'date_pattern', warnings)

    totals = []
    for index, line in enumerate(lines):
        match = TOTAL.search(line.text.strip())
        if not match:
            continue
        sources = [line]
        tail = line.text.strip()[match.end():]
        tail = re.sub(r'^[：:]\s*', '', tail).strip()
        values = [tail] if CURRENCY_AMOUNT.fullmatch(tail) else []
        if not tail and index + 1 < len(lines):
            next_line = lines[index + 1]
            try:
                values = [money(next_line.text)]
                sources.append(next_line)
            except ValueError:
                pass
        # 不把最大金额当 total，不从 cash/change/subtotal 偷取金额。
        for raw in values:
            totals.append((money(raw), sources))
    if totals:
        value, sources = totals[0]
        warnings = ['ambiguous_total'] if len({x[0] for x in totals}) > 1 else []
        result['total'] = field(value, sources, 'total_label', warnings)
    return result
