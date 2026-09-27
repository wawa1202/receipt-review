"""字段值评估：严格按文档 ID 配对，缺失预测计错，拒绝以训练数据冒充测试。"""
from receipt_review.normalize import canonical
from receipt_review.schemas import FIELD_NAMES


def evaluate(truth, predictions, *, mode):
    if mode not in {'synthetic', 'annotation_text', 'real_ocr'}:
        raise ValueError('必须标明 synthetic / annotation_text / real_ocr')
    def keyed(rows):
        result = {}
        for row in rows:
            key = row['id']
            if not key or key in result:
                raise ValueError('空文档 ID 或重复 ID')
            result[key] = row['fields']
        return result
    gold, pred = keyed(truth), keyed(predictions)
    if not gold or set(gold) != set(pred):
        raise ValueError('预测和标签必须包含相同且非空的文档集合')
    correct = {name: 0 for name in FIELD_NAMES}
    covered = 0
    documents_correct = 0
    errors = []
    for identity, target in gold.items():
        all_ok = True
        for name in FIELD_NAMES:
            expected = canonical(name, target.get(name))
            if expected is None:
                raise ValueError('评估标签缺失字段')
            raw = pred[identity].get(name)
            covered += bool(raw is not None and str(raw).strip())
            try:
                actual = canonical(name, raw)
            except ValueError:
                actual = None
            if actual == expected:
                correct[name] += 1
            else:
                all_ok = False
                errors.append({'id': identity, 'field': name, 'expected': target[name], 'predicted': raw})
        documents_correct += all_ok
    denominator = len(gold) * len(FIELD_NAMES)
    return {'mode': mode, 'documents': len(gold), 'normalization': 'casefold-whitespace; decimal-2dp; date-DD/MM/YYYY-v1',
            'field_accuracy': sum(correct.values()) / denominator,
            'document_accuracy': documents_correct / len(gold), 'coverage': covered / denominator,
            'per_field': {name: value / len(gold) for name, value in correct.items()}, 'errors': errors}
