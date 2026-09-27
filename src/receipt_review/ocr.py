"""图片入口和 CPU OCR 适配器；业务模块不依赖 OCR SDK 的返回格式。"""
from io import BytesIO
from importlib.metadata import version
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from receipt_review.schemas import OCRLine

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 12_000_000


def prepare_image(content: bytes):
    """校验实际文件内容，统一方向和坐标系，返回规范 PNG 与尺寸。"""
    if not content or len(content) > MAX_BYTES:
        raise ValueError('请选择不超过 8 MiB 的 PNG/JPEG 图片')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as original:
                if original.format not in {'PNG', 'JPEG'} or getattr(original, 'n_frames', 1) != 1:
                    raise ValueError('只支持单帧 PNG/JPEG')
                if original.width * original.height > MAX_PIXELS or min(original.size) < 32:
                    raise ValueError('图片须至少 32×32，且不超过 1200 万像素')
                original.load()
                oriented = ImageOps.exif_transpose(original)
                if oriented.mode in {'RGBA', 'LA'} or 'transparency' in oriented.info:
                    rgba = oriented.convert('RGBA')
                    background = Image.new('RGBA', rgba.size, 'white')
                    image = Image.alpha_composite(background, rgba).convert('RGB')
                else:
                    image = oriented.convert('RGB')
                stream = BytesIO()
                image.save(stream, format='PNG')
                return stream.getvalue(), image.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('图片损坏或尺寸过大，无法识别') from exc


class LocalOCR:
    """首次请求才加载模型；版本固定以便复现实验。"""
    def __init__(self):
        self.name = f'rapidocr-onnxruntime/{version("rapidocr-onnxruntime")};CPU'
        self._engine = None

    def __call__(self, content: bytes) -> list[OCRLine]:
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
        rows, _ = self._engine(content)
        lines = []
        for box, text, score in rows or []:
            if not text.strip():
                continue
            xs, ys = [float(p[0]) for p in box], [float(p[1]) for p in box]
            lines.append(OCRLine(len(lines), text.strip(),
                                 (max(0., min(xs)), max(0., min(ys)), max(xs), max(ys)), float(score)))
        return lines
