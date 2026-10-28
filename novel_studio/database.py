import json
import sqlite3
from pathlib import Path

from .chapter_splitter import split_document


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    genre TEXT NOT NULL DEFAULT '',
    synopsis TEXT NOT NULL DEFAULT '',
    audience TEXT NOT NULL DEFAULT '',
    style TEXT NOT NULL DEFAULT '',
    forbidden TEXT NOT NULL DEFAULT '',
    target_words INTEGER NOT NULL DEFAULT 100000,
    outline TEXT NOT NULL DEFAULT '',
    characters TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS volumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    volume_id INTEGER NOT NULL REFERENCES volumes(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '手动保存',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('character','background','faction','location','item')),
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    fields_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_entities_book ON entities(book_id,kind,id);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = data_dir
        self.path = data_dir / "studio.db"
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(entities)")}
            if "fields_json" not in columns:
                conn.execute("ALTER TABLE entities ADD COLUMN fields_json TEXT NOT NULL DEFAULT '{}'")

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def row(row):
        return dict(row) if row is not None else None

    def list_books(self):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT b.*, COUNT(c.id) AS chapter_count, "
                "COALESCE(SUM(LENGTH(c.content)), 0) AS character_count "
                "FROM books b LEFT JOIN chapters c ON c.book_id=b.id "
                "GROUP BY b.id ORDER BY b.updated_at DESC, b.id DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def create_book(self, data):
        title = data.get("title", "").strip()
        if not title:
            raise ValueError("请先给小说起个名字。")
        fields = {
            "title": title,
            "genre": data.get("genre", "").strip(),
            "synopsis": data.get("synopsis", "").strip(),
            "audience": data.get("audience", "").strip(),
            "style": data.get("style", "").strip(),
            "forbidden": data.get("forbidden", "").strip(),
            "target_words": max(1000, int(data.get("target_words") or 100000)),
        }
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO books(title,genre,synopsis,audience,style,forbidden,target_words) "
                "VALUES(:title,:genre,:synopsis,:audience,:style,:forbidden,:target_words)", fields
            )
            book_id = cursor.lastrowid
            conn.execute("INSERT INTO volumes(book_id,title,position) VALUES(?,?,1)", (book_id, "第一卷"))
        return self.get_book(book_id)

    def get_book(self, book_id):
        with self.connect() as conn:
            book = conn.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
            if not book:
                raise KeyError("这本书不存在，可能已经被删除。")
            result = dict(book)
            volumes = conn.execute(
                "SELECT * FROM volumes WHERE book_id=? ORDER BY position,id", (book_id,)
            ).fetchall()
            result["volumes"] = []
            for volume in volumes:
                item = dict(volume)
                chapters = conn.execute(
                    "SELECT id,title,position,updated_at,LENGTH(content) AS character_count "
                    "FROM chapters WHERE volume_id=? ORDER BY position,id", (volume["id"],)
                ).fetchall()
                item["chapters"] = [dict(row) for row in chapters]
                result["volumes"].append(item)
            entities = conn.execute(
                "SELECT * FROM entities WHERE book_id=? ORDER BY kind,id", (book_id,)
            ).fetchall()
            result["entities"] = [dict(row) for row in entities]
            return result

    def update_book(self, book_id, data):
        allowed = {"title", "genre", "synopsis", "audience", "style", "forbidden", "outline", "characters"}
        fields = {key: str(data[key]) for key in allowed if key in data}
        if "target_words" in data:
            fields["target_words"] = max(1000, int(data["target_words"]))
        if not fields:
            return self.get_book(book_id)
        assignments = ",".join(f"{key}=?" for key in fields)
        with self.connect() as conn:
            cursor = conn.execute(
                f"UPDATE books SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (*fields.values(), book_id),
            )
            if cursor.rowcount == 0:
                raise KeyError("这本书不存在，可能已经被删除。")
        return self.get_book(book_id)

    def get_entity(self, entity_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
        if not row:
            raise KeyError("这条设定不存在，可能已经被删除。")
        return dict(row)

    def save_entity(self, book_id, data, entity_id=None):
        kind = str(data.get("kind", ""))
        name = str(data.get("name", "")).strip()
        if kind not in {"character", "background", "faction", "location", "item"}:
            raise ValueError("请选择正确的设定分类。")
        if not name:
            raise ValueError("请先填写设定名称。")
        if kind == "character" and len(name) > 10:
            raise ValueError("角色姓名最多 10 个字，长的称号请放进别名。")
        raw_fields = data.get("fields") or {}
        if not isinstance(raw_fields, dict):
            raise ValueError("角色资料格式不正确。")
        fields = {}
        if kind == "character":
            tags = raw_fields.get("tags", [])
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
            fields = {
                "gender": str(raw_fields.get("gender", "未知"))[:10],
                "personality": str(raw_fields.get("personality", ""))[:500],
                "tags": [str(tag)[:20] for tag in tags if str(tag).strip()][:8],
                "background": str(raw_fields.get("background", ""))[:500],
                "biography": str(raw_fields.get("biography", ""))[:6000],
            }
        content = fields.get("background", "") if kind == "character" else str(data.get("content", "")).strip()
        values = (
            kind, name, str(data.get("aliases", "")).strip(), content,
            json.dumps(fields, ensure_ascii=False),
        )
        with self.connect() as conn:
            if entity_id is None:
                cursor = conn.execute(
                    "INSERT INTO entities(book_id,kind,name,aliases,content,fields_json) VALUES(?,?,?,?,?,?)",
                    (book_id, *values),
                )
                entity_id = cursor.lastrowid
            else:
                cursor = conn.execute(
                    "UPDATE entities SET kind=?,name=?,aliases=?,content=?,fields_json=?,updated_at=CURRENT_TIMESTAMP "
                    "WHERE id=? AND book_id=?", (*values, entity_id, book_id),
                )
                if cursor.rowcount == 0:
                    raise KeyError("这条设定不存在，或不属于当前书籍。")
            conn.execute("UPDATE books SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (book_id,))
        return self.get_entity(entity_id)

    def delete_entity(self, entity_id, book_id):
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM entities WHERE id=? AND book_id=?", (entity_id, book_id))
            if cursor.rowcount == 0:
                raise KeyError("这条设定不存在，或不属于当前书籍。")

    def create_chapter(self, book_id, data):
        title = data.get("title", "").strip() or "未命名章节"
        with self.connect() as conn:
            volume = conn.execute(
                "SELECT id FROM volumes WHERE book_id=? ORDER BY position,id LIMIT 1", (book_id,)
            ).fetchone()
            if not volume:
                raise KeyError("请先选择一本书。")
            position = conn.execute(
                "SELECT COALESCE(MAX(position),0)+1 FROM chapters WHERE book_id=?", (book_id,)
            ).fetchone()[0]
            cursor = conn.execute(
                "INSERT INTO chapters(book_id,volume_id,title,position) VALUES(?,?,?,?)",
                (book_id, volume[0], title, position),
            )
            chapter_id = cursor.lastrowid
            conn.execute("UPDATE books SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (book_id,))
        return self.get_chapter(chapter_id)

    def import_chapters(self, book_id, items):
        if not isinstance(items, list) or not items:
            raise ValueError("请先选择要导入的 TXT 或 MD 文件。")
        if len(items) > 200:
            raise ValueError("一次最多导入 200 章，请分批导入。")
        prepared = []
        for index, item in enumerate(items, 1):
            filename = str(item.get("name", "")).strip()
            if not filename.lower().endswith((".txt", ".md")):
                raise ValueError(f"第 {index} 个文件不是 TXT 或 MD：{filename or '未命名文件'}")
            title = filename.rsplit(".", 1)[0].strip() or f"导入章节 {index}"
            content = str(item.get("content", "")).lstrip("\ufeff")
            if not content.strip():
                raise ValueError(f"“{title}”是空文件。请删掉它或补上内容后再导入。")
            if len(content) > 5_000_000:
                raise ValueError(f"“{title}”太大了。单个文件请控制在 500 万字符以内。")
            parts = split_document(content, title)
            prepared.extend(parts or [(title, content)])
        if len(prepared) > 5000:
            raise ValueError("这一批识别出的章节超过 5000 章，请分成多个文件后导入。")
        with self.connect() as conn:
            volume = conn.execute(
                "SELECT id FROM volumes WHERE book_id=? ORDER BY position,id LIMIT 1", (book_id,)
            ).fetchone()
            if not volume:
                raise KeyError("请先选择一本书。")
            position = conn.execute(
                "SELECT COALESCE(MAX(position),0) FROM chapters WHERE book_id=?", (book_id,)
            ).fetchone()[0]
            chapter_ids = []
            for title, content in prepared:
                position += 1
                cursor = conn.execute(
                    "INSERT INTO chapters(book_id,volume_id,title,content,position) VALUES(?,?,?,?,?)",
                    (book_id, volume[0], title, content, position),
                )
                chapter_ids.append(cursor.lastrowid)
            conn.execute("UPDATE books SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (book_id,))
        return {"count": len(chapter_ids), "chapter_ids": chapter_ids, "first_chapter": self.get_chapter(chapter_ids[0])}

    def split_chapter(self, chapter_id):
        chapter = self.get_chapter(chapter_id)
        parts = split_document(chapter["content"], chapter["title"])
        if len(parts) < 2:
            raise ValueError("这一章里没有识别到两个以上“第X章”标题，不能自动分章。")
        offset = len(parts) - 1
        with self.connect() as conn:
            self.snapshot(conn, chapter_id, "自动分章前的整章原文")
            conn.execute(
                "UPDATE chapters SET position=position+? WHERE book_id=? AND position>?",
                (offset, chapter["book_id"], chapter["position"]),
            )
            first_title, first_content = parts[0]
            conn.execute(
                "UPDATE chapters SET title=?,content=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (first_title, first_content, chapter_id),
            )
            for index, (title, content) in enumerate(parts[1:], 1):
                conn.execute(
                    "INSERT INTO chapters(book_id,volume_id,title,content,position) VALUES(?,?,?,?,?)",
                    (chapter["book_id"], chapter["volume_id"], title, content, chapter["position"] + index),
                )
            conn.execute("UPDATE books SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (chapter["book_id"],))
        return {"count": len(parts), "chapter": self.get_chapter(chapter_id)}

    def get_chapter(self, chapter_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone()
        if not row:
            raise KeyError("这一章不存在，可能已经被删除。")
        return dict(row)

    def snapshot(self, conn, chapter_id, reason):
        row = conn.execute("SELECT title,content FROM chapters WHERE id=?", (chapter_id,)).fetchone()
        if row:
            conn.execute(
                "INSERT INTO versions(chapter_id,title,content,reason) VALUES(?,?,?,?)",
                (chapter_id, row["title"], row["content"], reason),
            )

    def update_chapter(self, chapter_id, data, snapshot=False, reason="手动保存"):
        allowed = {"title", "content"}
        fields = {key: str(data[key]) for key in allowed if key in data}
        if not fields:
            return self.get_chapter(chapter_id)
        with self.connect() as conn:
            if snapshot:
                self.snapshot(conn, chapter_id, reason)
            assignments = ",".join(f"{key}=?" for key in fields)
            cursor = conn.execute(
                f"UPDATE chapters SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (*fields.values(), chapter_id),
            )
            if cursor.rowcount == 0:
                raise KeyError("这一章不存在，可能已经被删除。")
            conn.execute(
                "UPDATE books SET updated_at=CURRENT_TIMESTAMP WHERE id=(SELECT book_id FROM chapters WHERE id=?)",
                (chapter_id,),
            )
        return self.get_chapter(chapter_id)

    def delete_chapter(self, chapter_id):
        with self.connect() as conn:
            row = conn.execute("SELECT book_id,title,content FROM chapters WHERE id=?", (chapter_id,)).fetchone()
            if not row:
                raise KeyError("这一章不存在，可能已经被删除。")
            trash_dir = self.data_dir / "已删除章节"
            trash_dir.mkdir(exist_ok=True)
            backup = trash_dir / f"章节_{chapter_id}.txt"
            backup.write_text(row["title"] + "\n\n" + row["content"], encoding="utf-8")
            conn.execute("DELETE FROM chapters WHERE id=?", (chapter_id,))
            conn.execute("UPDATE books SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (row["book_id"],))

    def list_versions(self, chapter_id):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id,title,reason,created_at,LENGTH(content) AS character_count "
                "FROM versions WHERE chapter_id=? ORDER BY id DESC LIMIT 50", (chapter_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_version(self, version_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM versions WHERE id=?", (version_id,)).fetchone()
        if not row:
            raise KeyError("这个旧版本不存在。")
        return dict(row)

    def export_book(self, book_id):
        book = self.get_book(book_id)
        with self.connect() as conn:
            chapters = conn.execute(
                "SELECT title,content FROM chapters WHERE book_id=? ORDER BY position,id", (book_id,)
            ).fetchall()
        parts = [book["title"], "=" * 24]
        if book["synopsis"]:
            parts.extend(["", "内容简介", book["synopsis"]])
        for chapter in chapters:
            parts.extend(["", "", chapter["title"], "", chapter["content"]])
        return book["title"], "\n".join(parts) + "\n"

    def get_settings(self):
        with self.connect() as conn:
            rows = conn.execute("SELECT key,value FROM settings").fetchall()
        settings = {row["key"]: row["value"] for row in rows}
        return {
            "base_url": settings.get("base_url", "https://api.moonshot.cn/v1"),
            "model": settings.get("model", "kimi-k3.1-pro"),
            "has_api_key": bool(settings.get("api_key")),
        }

    def save_settings(self, data):
        allowed = {"base_url", "model", "api_key"}
        with self.connect() as conn:
            for key in allowed:
                if key in data:
                    value = str(data[key]).strip()
                    if key == "api_key":
                        value = "".join(value.split())
                        if value.lower().startswith("bearer"):
                            value = value[6:].strip()
                        value = value.strip("\"'`")
                    if key == "api_key" and not value:
                        continue
                    conn.execute(
                        "INSERT INTO settings(key,value) VALUES(?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value)
                    )
        return self.get_settings()

    def clear_api_key(self):
        with self.connect() as conn:
            conn.execute("DELETE FROM settings WHERE key='api_key'")

    def api_credentials(self):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT key,value FROM settings WHERE key IN ('api_key','base_url','model')"
            ).fetchall()
        values = {row["key"]: row["value"] for row in rows}
        if not values.get("api_key"):
            raise ValueError("还没有填写 API Key。请点右上角的“API 设置”，把 Key 粘贴进去。")
        return {
            "api_key": values["api_key"],
            "base_url": values.get("base_url") or "https://api.moonshot.cn/v1",
            "model": values.get("model") or "kimi-k3.1-pro",
        }
