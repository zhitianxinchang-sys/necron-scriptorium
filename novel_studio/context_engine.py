import json
import re


ENTITY_LABELS = {
    "character": "角色",
    "background": "背景",
    "faction": "势力",
    "location": "地点",
    "item": "物品",
}


def integer_ids(values):
    result = set()
    for value in values or []:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result


def entity_description(entity):
    try:
        fields = json.loads(entity.get("fields_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        fields = {}
    parts = []
    if entity["kind"] == "character":
        if fields.get("gender"):
            parts.append("性别：" + fields["gender"])
        if fields.get("personality"):
            parts.append("性格：" + fields["personality"])
        if fields.get("tags"):
            parts.append("标签：" + "、".join(fields["tags"]))
        if fields.get("background"):
            parts.append("背景：" + fields["background"])
        if fields.get("biography"):
            parts.append("人物小传：" + fields["biography"])
    content = entity.get("content", "")
    if content and content != fields.get("background"):
        parts.append(content)
    return "\n".join(parts) or "暂无详细资料"


def query_terms(text):
    terms = set(re.findall(r"[A-Za-z0-9_]{2,}", text))
    for chunk in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(chunk) < 2:
            continue
        for size in (2, 3, 4):
            for index in range(0, max(0, len(chunk) - size + 1)):
                terms.add(chunk[index:index + size])
                if len(terms) >= 800:
                    return terms
    return terms


class ContextEngine:
    def build(self, db, book, chapter, data):
        config = data.get("context") or {}
        budget = int(config.get("max_chars") or 50000)
        budget = max(10000, min(80000, budget))
        instruction = str(data.get("instruction") or "")
        current_text = chapter["content"][-6000:]
        selected_entity_ids = integer_ids(config.get("entity_ids"))
        manual_entities = "entity_ids" in config
        candidates = []
        for entity in book.get("entities", []):
            names = [entity["name"], *re.split(r"[,，、\s]+", entity["aliases"])]
            names = [name.strip() for name in names if name.strip()]
            score = sum(min(current_text.count(name), 5) + min(instruction.count(name) * 3, 15) for name in names)
            candidates.append((entity, names, score))
        if manual_entities:
            chosen = [item for item in candidates if item[0]["id"] in selected_entity_ids]
        else:
            chosen = sorted(candidates, key=lambda item: (-item[2], item[0]["id"]))[:8]
            if chosen and not any(item[2] for item in chosen):
                chosen = chosen[:5]

        entity_parts = []
        for entity, names, _ in chosen:
            content = entity_description(entity)
            if len(content) > 4000:
                content = content[:4000] + "\n……（这条设定已截断）"
            entity_parts.append(
                f"【{ENTITY_LABELS[entity['kind']]}：{entity['name']}】\n别名：{entity['aliases'] or '无'}\n{content}"
            )
        entity_text = "\n\n".join(entity_parts)
        if len(entity_text) > 12000:
            entity_text = entity_text[:12000] + "\n……（更多设定未发送）"

        with db.connect() as conn:
            rows = conn.execute(
                "SELECT id,title,content,position FROM chapters WHERE book_id=? AND position<? ORDER BY position",
                (book["id"], chapter["position"]),
            ).fetchall()
        chapters = [dict(row) for row in rows if row["content"].strip()]
        forced_ids = integer_ids(config.get("chapter_ids"))
        latest_ids = {row["id"] for row in chapters[-2:]}
        priority_ids = latest_ids | forced_ids
        priority = [row for row in chapters if row["id"] in priority_ids]
        remaining = [row for row in chapters if row["id"] not in priority_ids]
        terms = query_terms(instruction + "\n" + current_text + "\n" + "\n".join(
            name for _, names, _ in chosen for name in names
        ))

        def relevance(row):
            content = row["content"]
            score = 0
            for term in terms:
                if term in content:
                    score += min(content.count(term), 3)
            entity_score = sum(
                min(content.count(name), 5) * 8
                for _, names, _ in chosen for name in names if len(name) >= 2
            )
            return score + entity_score + row["position"] / 10000

        remaining.sort(key=lambda row: (-relevance(row), -row["position"]))
        ordered_candidates = priority + remaining
        selected = []
        used = 0
        for row in ordered_candidates:
            size = len(row["content"])
            if used + size <= budget:
                selected.append(row)
                used += size
        selected.sort(key=lambda row: row["position"])
        reference_text = "\n\n".join(
            f"【参考章节：{row['title']}】\n{row['content']}" for row in selected
        )
        meta = {
            "chapter_count": len(selected),
            "character_count": used,
            "entity_count": len(chosen),
            "max_chars": budget,
            "chapter_ids": [row["id"] for row in selected],
            "entity_ids": [item[0]["id"] for item in chosen],
        }
        return reference_text, entity_text, meta
