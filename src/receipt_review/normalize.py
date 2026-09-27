"""明确的金额和日期口径；无法判断时拒绝猜测。"""
from datetime import date, datetime
from decimal import Decimal
import re


def money(text: str) -> str:
    cleaned = re.sub(r'^(?:RM|MYR|USD|CNY|RMB|[$¥￥])\s*', '', text.strip(), flags=re.I)
    if not re.fullmatch(r'(?:\d{1,9}|\d{1,3}(?:,\d{3}){1,2})\.\d{2}', cleaned):
        raise ValueError('金额需要非负数、两位小数，例如 1234.50；不猜测逗号小数')
    return format(Decimal(cleaned.replace(',', '')), '.2f')


def receipt_date(text: str) -> tuple[str, bool]:
    text = text.strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        return date.fromisoformat(text).isoformat(), False
    if not re.fullmatch(r'\d{1,2}[/.-]\d{1,2}[/.-]\d{4}', text):
        raise ValueError('日期需要 YYYY-MM-DD 或 DD/MM/YYYY')
    day, month, year = map(int, re.split(r'[/.-]', text))
    result = date(year, month, day)
    return result.isoformat(), day <= 12 and month <= 12 and day != month


def canonical(field: str, value) -> str | None:
    if value is None or not str(value).strip():
        return None
    if field == 'total':
        return money(str(value))
    if field == 'date':
        return receipt_date(str(value))[0]
    return ' '.join(str(value).casefold().split())
