"""用例编排：去重 → OCR → 抽取 → 提示 → 保存，不承担字段规则。"""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from threading import Lock
from time import perf_counter

from receipt_review.extraction import extract
from receipt_review.ocr import LocalOCR, prepare_image
from receipt_review.review import inspect
from receipt_review.schemas import EXTRACTOR_VERSION
from receipt_review.store import Store


class Busy(Exception):
    pass


class Pipeline:
    def __init__(self, runtime, *, engine=None):
        self.runtime = Path(runtime)
        self.images = self.runtime / 'images'
        self.images.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.runtime / 'receipts.sqlite3')
        self.engine = engine if engine is not None else LocalOCR()
        self.lock = Lock()

    def process(self, content):
        # 单进程单模型串行推理，避免笔记本被并发 OCR 请求耗尽内存。
        if not self.lock.acquire(blocking=False):
            raise Busy('正在识别另一张票据，请稍后重试')
        try:
            start = perf_counter()
            png, (width, height) = prepare_image(content)
            digest = sha256(png).hexdigest()
            previous = self.store.by_digest(digest)
            if previous:
                return {'document': previous, 'duplicate': True}
            lines = self.engine(png)
            fields = extract(lines)
            prediction = {
                'fields': {name: field.to_dict() for name, field in fields.items()},
                'lines': [asdict(line) for line in lines],
                'issues': inspect(fields, lines),
                'image': {'width': width, 'height': height},
                'extractor': EXTRACTOR_VERSION,
                'ocr': getattr(self.engine, 'name', 'injected-engine'),
                'elapsed_seconds': round(perf_counter() - start, 4),
            }
            image_name = f'{digest}.png'
            (self.images / image_name).write_bytes(png)
            document, duplicate = self.store.add(digest, image_name, prediction)
            return {'document': document, 'duplicate': duplicate}
        finally:
            self.lock.release()
