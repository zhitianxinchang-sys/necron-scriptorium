import re


NUMBER = r"[0-9０-９零〇一二三四五六七八九十百千万两]+"
CHAPTER_LINE = re.compile(
    rf"^[ \t\u3000]*(第[ \t]*{NUMBER}[ \t]*章(?:[ \t:：、.\-]+[^\n]{{0,80}})?)[ \t]*$",
    re.MULTILINE,
)


def split_document(text, fallback_title="导入章节"):
    text = str(text or "").lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(CHAPTER_LINE.finditer(text))
    if len(matches) < 2:
        return []
    chapters = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[start:end].strip("\n \t\u3000")
        title = re.sub(r"[ \t\u3000]+", " ", match.group(1)).strip()
        if content:
            chapters.append((title, content))
    return chapters if len(chapters) >= 2 else []
