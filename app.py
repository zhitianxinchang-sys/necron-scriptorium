import os
import socket
import threading
import webbrowser
from pathlib import Path

from novel_studio.server import run_server

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = Path.home() / "Documents" / "NovelStudioData"


def main():
    data_dir = Path(os.environ.get("NOVEL_STUDIO_DATA", DEFAULT_DATA))
    data_dir.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("NOVEL_STUDIO_PORT", "8765"))
    url = f"http://127.0.0.1:{port}"

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            already_running = True
    except OSError:
        already_running = False
    if already_running:
        if os.environ.get("NOVEL_STUDIO_NO_BROWSER") != "1":
            webbrowser.open(url)
        return

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            if os.environ.get("NOVEL_STUDIO_NO_BROWSER") != "1":
                webbrowser.open(url)
            return

    if os.environ.get("NOVEL_STUDIO_NO_BROWSER") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"太空死灵作家助手已启动：{url}")
    print(f"书稿保存在：{data_dir}")
    print("关闭这个黑色窗口就会退出太空死灵作家助手。")
    run_server(ROOT, data_dir, port)


if __name__ == "__main__":
    main()
