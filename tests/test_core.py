from datetime import date
import pytest

from receipt_review.schemas import OCRLine
from receipt_review.normalize import money, receipt_date
from receipt_review.extraction import extract
from receipt_review.review import inspect
from receipt_review.store import Store, Conflict
from receipt_review.evaluation import evaluate


def lines(*values):
    return [OCRLine(i, text, (0, i * 30, 500, i * 30 + 25), .99) for i, text in enumerate(values)]


@pytest.mark.parametrize('text,expected', [('RM 1,234.50', '1234.50'), ('12.00', '12.00'), ('0.00', '0.00')])
def test_money(text, expected):
    assert money(text) == expected


@pytest.mark.parametrize('text', ['NaN', '-1.00', '12,50', '1,23.00', '1e5', ''])
def test_money_rejects_unclear_formats(text):
    with pytest.raises(ValueError):
        money(text)


def test_date_ambiguity():
    assert receipt_date('04/05/2024') == ('2024-05-04', True)
    assert receipt_date('27/05/2024') == ('2024-05-27', False)
    with pytest.raises(ValueError):
        receipt_date('31/02/2024')


def test_total_is_not_cash_or_subtotal():
    found = extract(lines('DEMO MART', '12 JALAN MAJU', '27/05/2024', 'SUBTOTAL 90.00', 'TOTAL 95.00', 'CASH 100.00'))
    assert found['total'].value == '95.00'
    assert found['total'].evidence == (4,)
    assert found['company'].value == 'DEMO MART'
    assert found['address'].value == '12 JALAN MAJU'


def test_total_below_label_and_missing():
    assert extract(lines('DEMO MART', 'TOTAL', 'RM 12.50'))['total'].value == '12.50'
    assert extract(lines('DEMO MART', 'CASH 100.00'))['total'].value is None


@pytest.mark.parametrize('text', ['TOTAL CASH 100.00', 'TOTAL TAX 6.00', 'TOTAL -12.00', 'TOTAL -$12.00'])
def test_total_rejects_non_total_suffix_and_negative_amount(text):
    assert extract(lines('DEMO MART', text))['total'].value is None


@pytest.mark.parametrize('label', ['TOTAL CASH', 'TOTAL TAX'])
def test_total_does_not_use_next_line_after_non_total_suffix(label):
    assert extract(lines('DEMO MART', label, '100.00'))['total'].value is None


def test_multiple_totals_require_review():
    document = lines('DEMO MART', 'TOTAL 12.50', 'TOTAL 14.50')
    fields = extract(document)
    assert 'ambiguous_total' in fields['total'].warnings
    assert any(i['code'] == 'ambiguous_total' for i in inspect(fields, document))


def test_future_and_low_score_are_issues():
    document = lines('DEMO MART', '12 JALAN MAJU', '27/05/2099', 'TOTAL 10.00')
    document[-1] = OCRLine(3, 'TOTAL 10.00', (0, 90, 500, 115), .4)
    codes = {i['code'] for i in inspect(extract(document), document, today=date(2026, 1, 1))}
    assert {'future_date', 'low_ocr_score'} <= codes


def test_empty_and_invalid_ocr():
    assert all(f.value is None for f in extract([]).values())
    with pytest.raises(ValueError):
        OCRLine(0, 'x', (0, 0, 1, 1), float('nan'))


def test_duplicate_and_review_history(tmp_path):
    store = Store(tmp_path / 'db.sqlite')
    prediction = {'fields': {}, 'lines': [], 'issues': []}
    first, duplicate = store.add('a' * 64, 'image.png', prediction)
    second, duplicate2 = store.add('a' * 64, 'image.png', {'fields': {'bad': 'value'}})
    assert first['id'] == second['id'] and not duplicate and duplicate2
    fields = {'company':'SHOP', 'address':'12 ROAD', 'date':'2024-05-27', 'total':'12.00'}
    updated = store.review(first['id'], 1, fields, 'confirmed', '核对原图')
    assert updated['revision'] == 2 and updated['prediction'] == prediction
    assert updated['history'][0]['note'] == '核对原图'
    with pytest.raises(Conflict):
        store.review(first['id'], 1, fields, 'confirmed', 'stale')


def test_review_cannot_confirm_missing_fields(tmp_path):
    store = Store(tmp_path / 'db.sqlite')
    doc, _ = store.add('b' * 64, 'image.png', {})
    with pytest.raises(ValueError):
        store.review(doc['id'], 1, {}, 'confirmed', 'missing')
    assert store.get(doc['id'])['revision'] == 1


def test_metrics_count_missing_prediction_as_wrong():
    truth = [{'id':'a', 'fields':{'company':'X','address':'ROAD','date':'27/05/2024','total':'12.00'}}]
    report = evaluate(truth, [{'id':'a', 'fields':{'company':'X','address':'ROAD','date':'2024-05-27','total':None}}], mode='synthetic')
    assert report['field_accuracy'] == .75
    assert report['document_accuracy'] == 0
    assert report['coverage'] == .75
    assert report['errors'][0]['field'] == 'total'


def test_metrics_reject_missing_or_duplicate_ids():
    with pytest.raises(ValueError):
        evaluate([{'id':'a','fields':{}}], [], mode='synthetic')
    with pytest.raises(ValueError):
        evaluate([{'id':'a','fields':{}}, {'id':'a','fields':{}}], [], mode='synthetic')
