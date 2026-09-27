"""本机审核服务。默认无用户系统，不允许当成公网服务部署。"""
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from receipt_review import __version__
from receipt_review.demo import receipt_image
from receipt_review.ocr import MAX_BYTES
from receipt_review.pipeline import Busy, Pipeline
from receipt_review.store import Conflict


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: int = Field(ge=1)
    fields: dict[str, str | None]
    status: str
    note: str = Field(min_length=1, max_length=1000)


def create_app(runtime='runtime', *, engine=None):
    app = FastAPI(title='Receipt Review', version=__version__)
    pipeline = Pipeline(runtime, engine=engine)
    app.state.pipeline = pipeline

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        from fastapi.responses import JSONResponse
        # Host 防 DNS rebinding；Origin + 非简单请求头避免外站盲写本机。
        if request.url.hostname not in {'localhost', '127.0.0.1', 'testserver'}:
            return JSONResponse({'detail': '仅支持本机访问'}, status_code=403)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('origin')
            if request.headers.get('x-receipt-client') != 'local' or (origin and origin.rstrip('/') != str(request.base_url).rstrip('/')):
                return JSONResponse({'detail': '请求来源不允许'}, status_code=403)
            length = request.headers.get('content-length')
            if length and (not length.isdigit() or int(length) > MAX_BYTES + 65536):
                return JSONResponse({'detail': '请求超过大小限制'}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    def document(identity):
        try:
            return pipeline.store.get(identity)
        except KeyError:
            raise HTTPException(404, '记录不存在') from None

    def process(content):
        try:
            return pipeline.process(content)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Busy as exc:
            raise HTTPException(429, str(exc)) from exc

    @app.get('/', response_class=HTMLResponse)
    def index():
        return (Path(__file__).parent / 'static' / 'index.html').read_text(encoding='utf-8')

    @app.get('/health')
    def health():
        return {'service': 'receipt-review', 'version': __version__}

    @app.get('/api/documents')
    def documents():
        return pipeline.store.list()

    @app.get('/api/documents/{identity}')
    def detail(identity: str):
        return document(identity)

    @app.get('/api/documents/{identity}/image')
    def image(identity: str):
        return FileResponse(pipeline.images / document(identity)['image_name'], media_type='image/png')

    @app.post('/api/documents')
    def upload(file: UploadFile = File(...)):
        try:
            return process(file.file.read(MAX_BYTES + 1))
        finally:
            file.file.close()

    @app.post('/api/demo')
    def demo():
        return process(receipt_image())

    @app.post('/api/documents/{identity}/review')
    def review(identity: str, body: ReviewInput):
        try:
            return pipeline.store.review(identity, body.revision, body.fields, body.status, body.note)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError:
            raise HTTPException(404, '记录不存在') from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return app
