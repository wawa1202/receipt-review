import json

import pytest

from receipt_review.data import load_sroie


def test_sroie_preserves_commas_and_pairs_ids(tmp_path):
    boxes, labels = tmp_path / 'box', tmp_path / 'entities'
    boxes.mkdir()
    labels.mkdir()
    (boxes / 'one.txt').write_text('0,0,200,0,200,30,0,30,SHOP, LTD\n', encoding='utf-8')
    (labels / 'one.txt').write_text(json.dumps({'company': 'SHOP, LTD', 'address': '12 ROAD', 'date': '27/05/2024', 'total': '12.00'}), encoding='utf-8')
    rows = load_sroie(boxes, labels)
    assert rows[0]['lines'][0].text == 'SHOP, LTD'
    assert len(rows[0]['annotation_sha256']) == 64
    (labels / 'two.txt').write_text('{}')
    with pytest.raises(ValueError, match='ID'):
        load_sroie(boxes, labels)


def test_sroie_invalid_geometry_rejected(tmp_path):
    boxes, labels = tmp_path / 'box', tmp_path / 'entities'
    boxes.mkdir()
    labels.mkdir()
    (boxes / 'one.txt').write_text('bad,line\n', encoding='utf-8')
    (labels / 'one.txt').write_text('{}')
    with pytest.raises(ValueError):
        load_sroie(boxes, labels)
