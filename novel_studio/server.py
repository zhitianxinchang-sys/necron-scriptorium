import json
import logging
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .database import Database
from .kimi_api import APIError, KimiAPI
from .skill_engine import SkillEngine


class NovelStudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def make_handler(root, data_dir):
    db = Database(data_dir)
    skills = SkillEngine(root)
    logger = logging.getLogger("novel_studio")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(data_dir / "app.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            logger.info("%s %s", self.client_address[0], fmt % args)

        def send_json(self, payload, status=200):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def read_json(self):
            length = int(self.headers.get("Content-Length", "0"))
            if length > 52 * 1024 * 1024:
                raise ValueError("这一批文件太大了。请减少一些文件，分批导入。")
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ValueError("软件没有读懂这次操作，请刷新页面后再试。") from None

        def handle_errors(self, callback):
            try:
                callback()
            except (ValueError, KeyError) as exc:
                message = exc.args[0] if exc.args else str(exc)
                self.send_json({"error": str(message)}, 400)
            except APIError as exc:
                self.send_json({"error": str(exc)}, 502)
            except BrokenPipeError:
                pass
            except Exception:
                logger.exception("Unhandled request error: %s", self.path)
                self.send_json({"error": "软件刚才卡了一下。你的原稿仍在，请再试一次；反复出现请把 app.log 发给维护人员。"}, 500)

        def do_GET(self):
            self.handle_errors(self.route_get)

        def do_POST(self):
            self.handle_errors(self.route_post)

        def do_PUT(self):
            self.handle_errors(self.route_put)

        def do_DELETE(self):
            self.handle_errors(self.route_delete)

        def route_get(self):
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/books":
                return self.send_json({"books": db.list_books()})
            match = re.fullmatch(r"/api/books/(\d+)", path)
            if match:
                return self.send_json({"book": db.get_book(int(match[1]))})
            match = re.fullmatch(r"/api/chapters/(\d+)", path)
            if match:
                return self.send_json({"chapter": db.get_chapter(int(match[1]))})
            match = re.fullmatch(r"/api/chapters/(\d+)/versions", path)
            if match:
                return self.send_json({"versions": db.list_versions(int(match[1]))})
            match = re.fullmatch(r"/api/versions/(\d+)", path)
            if match:
                return self.send_json({"version": db.get_version(int(match[1]))})
            if path == "/api/settings":
                return self.send_json(db.get_settings())
            match = re.fullmatch(r"/api/books/(\d+)/export", path)
            if match:
                title, text = db.export_book(int(match[1]))
                return self.send_download(title + ".txt", text)
            match = re.fullmatch(r"/api/chapters/(\d+)/export", path)
            if match:
                chapter = db.get_chapter(int(match[1]))
                text = chapter["title"] + "\n\n" + chapter["content"]
                return self.send_download(chapter["title"] + ".txt", text)
            return self.serve_static(path)

        def route_post(self):
            path = urllib.parse.urlparse(self.path).path
            data = self.read_json()
            if path == "/api/books":
                return self.send_json({"book": db.create_book(data)}, 201)
            match = re.fullmatch(r"/api/books/(\d+)/chapters", path)
            if match:
                return self.send_json({"chapter": db.create_chapter(int(match[1]), data)}, 201)
            match = re.fullmatch(r"/api/books/(\d+)/import-chapters", path)
            if match:
                result = db.import_chapters(int(match[1]), data.get("files"))
                return self.send_json(result, 201)
            match = re.fullmatch(r"/api/chapters/(\d+)/split", path)
            if match:
                return self.send_json(db.split_chapter(int(match[1])))
            match = re.fullmatch(r"/api/books/(\d+)/entities", path)
            if match:
                entity = db.save_entity(int(match[1]), data)
                return self.send_json({"entity": entity}, 201)
            match = re.fullmatch(r"/api/entities/(\d+)/biography", path)
            if match:
                messages = skills.biography_messages(db, int(match[1]))
                text = KimiAPI(db.api_credentials()).complete(messages, max_tokens=4096)
                return self.send_json({"biography": text})
            if path == "/api/settings":
                base_url = str(data.get("base_url", "")).strip()
                if base_url and not base_url.startswith(("http://", "https://")):
                    raise ValueError("API 地址要以 http:// 或 https:// 开头。")
                return self.send_json(db.save_settings(data))
            if path == "/api/settings/clear-key":
                db.clear_api_key()
                return self.send_json({"ok": True})
            if path == "/api/ai/test":
                result = KimiAPI(db.api_credentials()).test()
                return self.send_json({"message": result})
            if path == "/api/ai/generate":
                return self.stream_ai(data)
            match = re.fullmatch(r"/api/versions/(\d+)/restore", path)
            if match:
                version = db.get_version(int(match[1]))
                chapter = db.update_chapter(
                    version["chapter_id"],
                    {"title": version["title"], "content": version["content"]},
                    snapshot=True,
                    reason="恢复旧版本前的正文",
                )
                return self.send_json({"chapter": chapter})
            self.send_json({"error": "没有找到这个功能。"}, 404)

        def route_put(self):
            path = urllib.parse.urlparse(self.path).path
            data = self.read_json()
            match = re.fullmatch(r"/api/books/(\d+)", path)
            if match:
                return self.send_json({"book": db.update_book(int(match[1]), data)})
            match = re.fullmatch(r"/api/chapters/(\d+)", path)
            if match:
                snapshot = bool(data.pop("snapshot", False))
                reason = str(data.pop("reason", "手动保存"))
                chapter = db.update_chapter(int(match[1]), data, snapshot, reason)
                return self.send_json({"chapter": chapter})
            match = re.fullmatch(r"/api/books/(\d+)/entities/(\d+)", path)
            if match:
                entity = db.save_entity(int(match[1]), data, int(match[2]))
                return self.send_json({"entity": entity})
            self.send_json({"error": "没有找到这个功能。"}, 404)

        def route_delete(self):
            path = urllib.parse.urlparse(self.path).path
            match = re.fullmatch(r"/api/chapters/(\d+)", path)
            if match:
                db.delete_chapter(int(match[1]))
                return self.send_json({"ok": True})
            match = re.fullmatch(r"/api/books/(\d+)", path)
            if match:
                backup = db.delete_book(int(match[1]))
                return self.send_json({"ok": True, "backup": str(backup)})
            match = re.fullmatch(r"/api/books/(\d+)/entities/(\d+)", path)
            if match:
                db.delete_entity(int(match[2]), int(match[1]))
                return self.send_json({"ok": True})
            self.send_json({"error": "没有找到这个功能。"}, 404)

        def stream_ai(self, data):
            messages, context_meta = skills.build_messages(db, data)
            api = KimiAPI(db.api_credentials())
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                meta_event = json.dumps({"type": "meta", "context": context_meta}, ensure_ascii=False) + "\n"
                self.wfile.write(meta_event.encode("utf-8"))
                self.wfile.flush()
                for event in api.stream(messages):
                    self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.wfile.flush()
            except APIError as exc:
                self.wfile.write((json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
            except BrokenPipeError:
                logger.info("AI stream cancelled by browser")

        def send_download(self, filename, text):
            body = text.encode("utf-8-sig")
            quoted = urllib.parse.quote(filename)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def serve_static(self, path):
            files = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/index.html": ("index.html", "text/html; charset=utf-8"),
                "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                "/app.js": ("app.js", "application/javascript; charset=utf-8"),
            }
            if path not in files:
                return self.send_json({"error": "页面不存在。"}, 404)
            filename, content_type = files[path]
            body = (root / "static" / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def run_server(root: Path, data_dir: Path, port: int):
    server = NovelStudioServer(("127.0.0.1", port), make_handler(root, data_dir))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
