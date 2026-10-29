import ctypes
import os
import socket
import sys
import threading
import traceback
from ctypes import wintypes
from pathlib import Path

from novel_studio.server import NovelStudioServer, make_handler


APP_NAME = "太空死灵作家助手"
MUTEX_NAME = "Local\\NecronScriptoriumDesktop"
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
DEFAULT_DATA = Path.home() / "Documents" / "NovelStudioData"
DESKTOP_PORT = int(os.environ.get("NOVEL_STUDIO_DESKTOP_PORT", "48765"))


def message_box(message, error=True):
    flags = 0x10 if error else 0x40
    ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, flags)


def acquire_single_instance():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise OSError("无法创建程序互斥锁")
    if ctypes.get_last_error() == 183:
        message_box("太空死灵作家助手已经在运行，请不要重复打开。", error=False)
        return None
    return handle


def start_server(data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        server = NovelStudioServer(("127.0.0.1", DESKTOP_PORT), make_handler(ROOT, data_dir))
    except OSError as exc:
        raise RuntimeError(
            f"本地端口 {DESKTOP_PORT} 被其他程序占用了。请关闭占用端口的程序后再打开。"
        ) from exc
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for _ in range(40):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return server, port
        except OSError:
            threading.Event().wait(0.05)
    server.shutdown()
    raise RuntimeError("本地写作服务未能启动")


def run_desktop():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NecronScriptorium.Desktop.1")
    except Exception:
        pass

    mutex = acquire_single_instance()
    if not mutex:
        return

    data_dir = Path(os.environ.get("NOVEL_STUDIO_DATA", DEFAULT_DATA))
    server = None
    try:
        server, port = start_server(data_dir)
        (data_dir / "webview").mkdir(parents=True, exist_ok=True)
        import webview

        webview.create_window(
            APP_NAME,
            f"http://127.0.0.1:{port}",
            width=1320,
            height=860,
            min_size=(980, 680),
            background_color="#040706",
            text_select=True,
            confirm_close=False,
        )
        webview.start(
            gui="edgechromium",
            debug=False,
            private_mode=False,
            storage_path=str(data_dir / "webview"),
        )
    except Exception as exc:
        log = data_dir / "desktop-error.log"
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            log.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        message_box(
            "桌面窗口没有正常启动。\n\n"
            "请确认 Windows 的 Microsoft Edge WebView2 已安装，"
            "然后重新打开程序。\n\n"
            f"错误信息：{exc}\n\n"
            f"详细记录：{log}"
        )
    finally:
        if server:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    run_desktop()
