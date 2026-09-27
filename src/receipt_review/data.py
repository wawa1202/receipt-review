"""读取 SROIE 文本框和实体标注，严格按文件名配对；不下载、不拆分数据。"""
from hashlib import sha256
import json
from pathlib import Path

from receipt_review.normalize import canonical
from receipt_review.schemas import FIELD_NAMES, OCRLine


def indexed(directory, suffixes):
    result = {}
    for path in sorted(Path(directory).iterdir()):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if path.stem in result:
            raise ValueError(f'重复文件 ID：{path.stem}')
        result[path.stem] = path
    return result


def load_sroie(boxes, labels):
    box_files = indexed(boxes, {'.txt'})
    label_files = indexed(labels, {'.txt', '.json'})
    if not box_files or box_files.keys() != label_files.keys():
        raise ValueError('文本框与实体标签的 ID 集合必须相同且非空；请传入同一分区')
    documents = []
    for identity, path in box_files.items():
        lines = []
        for number, row in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            if not row.strip():
                continue
            pieces = row.split(',', 8)  # 文字自身可能含逗号。
            if len(pieces) != 9:
                raise ValueError(f'{identity} 第 {number} 行不是八坐标加文字')
            coords = [float(value) for value in pieces[:8]]
            xs, ys = coords[::2], coords[1::2]
            lines.append(OCRLine(len(lines), pieces[8], (min(xs), min(ys), max(xs), max(ys)), 1.0))
        label_path = label_files[identity]
        fields = json.loads(label_path.read_text(encoding='utf-8-sig'))
        if not isinstance(fields, dict) or set(fields) != set(FIELD_NAMES):
            raise ValueError(f'{identity} 实体标签必须恰好包含四个字段')
        for name, value in fields.items():
            if not isinstance(value, str) or canonical(name, value) is None:
                raise ValueError(f'{identity} 标签值不合法：{name}')
        documents.append({'id': identity, 'fields': fields, 'lines': lines,
                          'annotation_sha256': sha256(path.read_bytes()).hexdigest(),
                          'label_sha256': sha256(label_path.read_bytes()).hexdigest()})
    return documents
