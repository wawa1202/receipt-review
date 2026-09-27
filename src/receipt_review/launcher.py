"""双击启动：已有本项目服务则复用，否则启动并等待健康检查。"""
import json
from pathlib import Path
import socket
import threading
import time
from urllib.request import urlopen
import webbrowser

PORT = 8782
URL = f'http://127.0.0.1:{PORT}'


def running():
    try:
        with urlopen(URL + '/health', timeout=1) as response:
            return json.load(response).get('service') == 'receipt-review'
    except (OSError, ValueError):
        return False


def main():
    if running():
        webbrowser.open(URL)
        return
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', PORT))
        except OSError:
            raise SystemExit(f'Port {PORT} is occupied by another service. Close it or use the CLI --port option.')
    def open_when_ready():
        for _ in range(100):
            if running():
                webbrowser.open(URL)
                return
            time.sleep(.2)
    threading.Thread(target=open_when_ready, daemon=True).start()
    import uvicorn
    from receipt_review.api import create_app
    root = Path(__file__).resolve().parents[2]
    print(f'Open {URL} | Close this window or press Ctrl+C to stop.')
    uvicorn.run(create_app(root / 'runtime'), host='127.0.0.1', port=PORT, workers=1)


if __name__ == '__main__':
    main()
