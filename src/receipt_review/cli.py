"""命令入口：浏览器服务、自制数据冒烟验证、公开标注评估。"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
from tempfile import TemporaryDirectory
from time import perf_counter

from receipt_review.data import indexed, load_sroie
from receipt_review.demo import DEMO_FIELDS, receipt_image
from receipt_review.evaluation import evaluate
from receipt_review.extraction import extract
from receipt_review.ocr import LocalOCR, prepare_image
from receipt_review.pipeline import Pipeline
from receipt_review.schemas import EXTRACTOR_VERSION


def write_report(path, result):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Report: {target.resolve()}')


def metadata():
    return {'created_at': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
            'extractor': EXTRACTOR_VERSION,
            'packages': {name: version(name) for name in ('rapidocr-onnxruntime', 'onnxruntime', 'pillow')}}


def smoke(output):
    # 独立临时数据库，每次确实重跑 OCR，不把去重缓存当推理耗时。
    with TemporaryDirectory(prefix='receipt-smoke-') as directory:
        pipeline = Pipeline(directory)
        content = receipt_image()
        first = pipeline.process(content)
        document = first['document']
        predicted = {name: value['value'] for name, value in document['prediction']['fields'].items()}
        report = evaluate([{'id': 'demo', 'fields': DEMO_FIELDS}], [{'id': 'demo', 'fields': predicted}], mode='synthetic')
        duplicate = pipeline.process(content)['duplicate']
        revised = pipeline.store.review(document['id'], 1, DEMO_FIELDS, 'confirmed', '自制样本验证：按已知绘制内容核对')
        assert duplicate and revised['revision'] == 2 and len(revised['history']) == 1
        assert revised['prediction'] == document['prediction']
        report.update(metadata())
        report.update({'scope': 'one synthetic image; not a public benchmark', 'real_ocr_used': True,
                       'ocr_seconds_including_initialization': document['prediction']['elapsed_seconds'],
                       'dedup_verified': duplicate, 'review_history_verified': True,
                       'prediction': document['prediction']})
        write_report(output, report)
        print(f'Synthetic field accuracy: {report["field_accuracy"]:.3f}; document accuracy: {report["document_accuracy"]:.3f}')


def sroie(args):
    documents = load_sroie(args.boxes, args.labels)
    engine = LocalOCR() if args.mode == 'real_ocr' else None
    images = indexed(args.images, {'.png', '.jpg', '.jpeg'}) if args.images else {}
    if engine and images.keys() != {doc['id'] for doc in documents}:
        raise ValueError('图片 ID 与标注 ID 集合不一致')
    predictions, manifest, timings = [], [], []
    for document in documents:
        start = perf_counter()
        identity = document['id']
        entry = {key: document[key] for key in ('id', 'annotation_sha256', 'label_sha256')}
        if engine:
            content = images[identity].read_bytes()
            png, _ = prepare_image(content)
            lines = engine(png)
            entry['image_sha256'] = sha256(content).hexdigest()
        else:
            lines = document['lines']
        fields = extract(lines)  # 标签只进入评分函数，不进入抽取。
        predictions.append({'id': identity, 'fields': {name: item.value for name, item in fields.items()}})
        timings.append(perf_counter() - start)
        manifest.append(entry)
    truth = [{'id': doc['id'], 'fields': doc['fields']} for doc in documents]
    report = evaluate(truth, predictions, mode=args.mode)
    report.update(metadata())
    report.update({'source': args.source, 'revision': args.revision, 'partition': args.partition,
                   'manifest': manifest, 'predictions': predictions,
                   'seconds_total': sum(timings), 'seconds_per_document': timings,
                   'caveat': 'Custom field-value metrics, not official competition scoring. Partition is user-declared.'})
    write_report(args.output, report)


def main():
    parser = argparse.ArgumentParser(description='票据识别与人工复核')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve', help='启动本地审核页面')
    serve.add_argument('--port', type=int, default=8782)
    serve.add_argument('--runtime', default='runtime')
    smoke_parser = sub.add_parser('smoke', help='运行真实 OCR 自制样本验证')
    smoke_parser.add_argument('--output', default='reports/smoke.json')
    sample = sub.add_parser('demo-image', help='生成自制收据图片')
    sample.add_argument('--output', default='runtime/demo.png')
    dataset = sub.add_parser('evaluate-sroie', help='评估本地 SROIE 数据分区')
    dataset.add_argument('--boxes', required=True)
    dataset.add_argument('--labels', required=True)
    dataset.add_argument('--images')
    dataset.add_argument('--mode', required=True, choices=['annotation_text', 'real_ocr'])
    dataset.add_argument('--source', required=True, help='来源 URL')
    dataset.add_argument('--revision', required=True, help='提交哈希或数据快照版本')
    dataset.add_argument('--partition', required=True, choices=['development', 'held_out'])
    dataset.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'serve':
            import uvicorn
            from receipt_review.api import create_app
            uvicorn.run(create_app(args.runtime), host='127.0.0.1', port=args.port, workers=1)
        elif args.command == 'smoke':
            smoke(args.output)
        elif args.command == 'demo-image':
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(receipt_image())
            print(target.resolve())
        else:
            if args.mode == 'real_ocr' and not args.images:
                parser.error('real_ocr 模式必须提供 --images')
            sroie(args)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f'错误：{exc}\n')


if __name__ == '__main__':
    main()
