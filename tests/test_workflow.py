from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from receipt_review.api import create_app
from receipt_review.ocr import prepare_image
from receipt_review.pipeline import Pipeline
from receipt_review.schemas import OCRLine


def picture():
    stream = BytesIO()
    Image.new('RGB', (600, 700), 'white').save(stream, format='PNG')
    return stream.getvalue()


class FakeOCR:
    name = 'fake-for-tests'
    calls = 0

    def __call__(self, content):
        self.calls += 1
        return [OCRLine(i, text, (10, 10 + 40*i, 500, 40 + 40*i), .99)
                for i, text in enumerate(['DEMO MART', '12 JALAN MAJU', '27/05/2024', 'TOTAL 12.00', 'CASH 20.00'])]


def test_invalid_images():
    with pytest.raises(ValueError):
        prepare_image(b'not an image')
    with pytest.raises(ValueError):
        prepare_image(b'x' * (8 * 1024 * 1024 + 1))
    stream = BytesIO()
    Image.new('RGB', (4000, 3100)).save(stream, format='PNG')
    with pytest.raises(ValueError):
        prepare_image(stream.getvalue())


def test_transparent_png_is_composited_on_white():
    stream = BytesIO()
    image = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
    image.putpixel((10, 10), (0, 0, 0, 255))
    image.save(stream, format='PNG')
    normalized, _ = prepare_image(stream.getvalue())
    with Image.open(BytesIO(normalized)).convert('RGB') as checked:
        assert checked.getpixel((10, 10)) == (0, 0, 0)
        assert checked.getpixel((0, 0)) == (255, 255, 255)


def test_pipeline_duplicate_and_empty(tmp_path):
    engine = FakeOCR()
    pipeline = Pipeline(tmp_path, engine=engine)
    first = pipeline.process(picture())
    second = pipeline.process(picture())
    assert first['document']['status'] == 'pending'
    assert second['duplicate'] and engine.calls == 1
    assert first['document']['id'] == second['document']['id']
    assert first['document']['prediction']['fields']['total']['value'] == '12.00'
    empty = Pipeline(tmp_path / 'empty', engine=lambda _: []).process(picture())
    assert len(empty['document']['prediction']['issues']) == 4


def test_engine_failure_does_not_create_document(tmp_path):
    def fail(_):
        raise RuntimeError('engine down')
    pipeline = Pipeline(tmp_path, engine=fail)
    with pytest.raises(RuntimeError):
        pipeline.process(picture())
    assert pipeline.store.list() == []


def test_api_full_review_and_origin_guard(tmp_path):
    client = TestClient(create_app(tmp_path, engine=FakeOCR()))
    headers = {'X-Receipt-Client': 'local'}
    upload = {'file': ('receipt.png', picture(), 'image/png')}
    assert client.post('/api/documents', files=upload).status_code == 403
    assert client.post('/api/documents', files=upload, headers={**headers, 'Origin': 'https://evil.example'}).status_code == 403
    result = client.post('/api/documents', files=upload, headers=headers)
    assert result.status_code == 200
    document = result.json()['document']
    identity = document['id']
    assert client.get('/health').json()['service'] == 'receipt-review'
    assert client.get('/').status_code == 200
    assert client.get(f'/api/documents/{identity}/image').headers['content-type'] == 'image/png'
    assert len(client.get('/api/documents').json()) == 1
    body = {'revision': 1, 'fields': document['current_fields'], 'status': 'confirmed', 'note': '核对原图'}
    saved = client.post(f'/api/documents/{identity}/review', json=body, headers=headers)
    assert saved.status_code == 200
    assert saved.json()['revision'] == 2
    assert saved.json()['prediction'] == document['prediction']
    assert client.post(f'/api/documents/{identity}/review', json=body, headers=headers).status_code == 409
    assert client.get('/api/documents/nonexistent').status_code == 404
    assert client.post('/api/documents', files={'file': ('bad.png', b'bad')}, headers=headers).status_code == 400
