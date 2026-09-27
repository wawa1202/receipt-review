"""模块之间共享的稳定结构；OCR 分数不是字段正确概率。"""
from dataclasses import asdict, dataclass
from math import isfinite

FIELD_NAMES = ('company', 'address', 'date', 'total')
EXTRACTOR_VERSION = 'rules-v1'


@dataclass(frozen=True)
class OCRLine:
    id: int
    text: str
    bbox: tuple[float, float, float, float]
    score: float

    def __post_init__(self):
        if type(self.id) is not int or self.id < 0 or not self.text.strip():
            raise ValueError('OCR 行需要非负 ID 和非空文本')
        if len(self.bbox) != 4 or not all(isfinite(x) and x >= 0 for x in self.bbox):
            raise ValueError('OCR 坐标非法')
        x1, y1, x2, y2 = self.bbox
        if x2 <= x1 or y2 <= y1 or not isfinite(self.score) or not 0 <= self.score <= 1:
            raise ValueError('OCR 边框或分数非法')


@dataclass(frozen=True)
class Field:
    value: str | None
    evidence: tuple[int, ...] = ()
    ocr_score: float | None = None
    method: str = 'missing'
    warnings: tuple[str, ...] = ()

    def to_dict(self):
        return asdict(self)
