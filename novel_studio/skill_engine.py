from pathlib import Path

from .context_engine import ContextEngine, entity_description


TASKS = {
    "start": {
        "skills": ["chinese-novelist-skill", "novel-creator-skill", "webnovel-writer"],
        "instruction": "为这本书制作一份能直接开始创作的开书方案。包含：书名建议、一句话卖点、目标读者、故事核心冲突、主角欲望与缺陷、金手指及代价、世界规则、主线与暗线、第一卷方向、前10章简要安排。不要写正文。",
    },
    "outline": {
        "skills": ["story-long-write", "webnovel-writer"],
        "instruction": "根据已有资料完善小说大纲。先保留作者已经确定的内容，再给出总纲、当前卷纲和接下来10章细纲。每章写清目标、冲突、结果和章尾钩子，不要提前写正文。",
    },
    "character": {
        "skills": ["character-designer"],
        "instruction": "设计或完善本书角色。给出角色档案、外在欲望、内在需求、恐惧与底线、人物关系、成长弧线、语言习惯和对话示例。信息不足处可以提出合理建议，但不要擅自改变作者已经确定的设定。",
    },
    "plot": {
        "skills": ["story-long-write", "webnovel-writer"],
        "instruction": "只续想接下来的剧情，不写小说正文。根据精选前文和关联设定，给出 3 个可选走向，再推荐其中 1 个并拆成场景目标、冲突升级、人物选择、结果和章尾钩子。不得编造与参考资料冲突的既有事实。",
    },
    "write": {
        "skills": ["chinese-novelist-skill", "novel-creator-skill", "story-long-write", "webnovel-writer"],
        "instruction": "写当前这一章的完整正文。严格承接大纲、人物设定和上一章，围绕本章目标制造冲突或变化，结尾留下具体悬念。只输出可直接发表的小说正文，不要标题、解释、写作思路、Markdown 标记或自检报告。",
    },
    "continue": {
        "skills": ["chinese-novelist-skill", "novel-creator-skill", "story-long-write", "webnovel-writer"],
        "instruction": "从当前正文最后一个字自然续写，保持视角、时态、人物声线和已有事实。不要复述已有段落，不要跳到后续大结局。只输出新增的小说正文，不要解释或 Markdown 标记。",
    },
    "review": {
        "skills": ["story-review"],
        "instruction": "以起点长篇网文标准审查当前章节。必须找具体问题，不要为了夸奖而回避缺陷。按“必须改、建议改、可以不改”分组，每项附原文短引、对读者感受的影响和可执行改法；同时检查剧情、角色、设定、节奏、对话、文字和章尾钩子。只审查，不改写正文。",
    },
    "deslop": {
        "skills": ["story-deslop"],
        "instruction": "在不改变剧情、人物决定、设定和作者文风的前提下去除 AI 腔。优先修复机械短句、重复总结、空洞形容、同质对话和详略失衡。直接输出修改后的完整章节正文，不要附加说明、对照表或 Markdown 标记。",
    },
    "analyze": {
        "skills": ["story-long-analyze"],
        "instruction": "分析用户提供的参考小说文本。区分文本事实与推断，分析黄金开篇、逐段剧情推进、情绪与节奏、角色关系、设定揭示和文风特点。只提炼可迁移的抽象写法，不复刻原句、专有设定、角色组合或标志性事件链。输出清晰的中文拆书报告。",
    },
}

LIMITS = {
    "chinese-novelist-skill": 6000,
    "novel-creator-skill": 10000,
    "webnovel-writer": 5000,
    "story-long-write": 11000,
    "character-designer": 9000,
    "story-review": 18000,
    "story-deslop": 13000,
    "story-long-analyze": 12000,
}

# Original compact guidance used when optional third-party skills are not installed.
BUILTIN_FALLBACKS = {
    "chinese-novelist-skill": (
        "中文小说写作原则：用行动、对话和可感细节呈现人物与冲突，避免连续总结情绪。"
        "每章都要有目标、阻碍、选择、结果和新问题；章尾留下具体悬念。保持人物声线、"
        "视角、时间线和既有事实一致。不要替读者解释刚刚发生的所有含义。"
    ),
    "novel-creator-skill": (
        "长篇创作原则：先确认题材、读者、文风、禁区与目标规模，再规划总纲、卷纲和章纲。"
        "写每章前读取当前大纲、人物状态和最近章节；写后检查设定、时间线、角色状态与伏笔。"
        "单章内不要同时完成多个重大主线跃迁，不要提前解决全书核心矛盾。"
    ),
    "webnovel-writer": (
        "连载管理原则：把事实、推断和作者指令分开。每章记录角色位置、能力边界、已知信息、"
        "关系变化、未回收伏笔和时间推进。续写只使用已经确认的事实；需要新增重要设定时先提出，"
        "不得为了制造转折而违背前文。"
    ),
    "story-long-write": (
        "写作教练原则：先判断作者要的是结构讨论、大纲、细纲还是正文，不扩大授权范围。"
        "正文必须承接细纲和上一章，场景要有情绪重心与功能；改稿时保留作者已定事实，"
        "只修改请求范围内的问题。写完后报告实际改动、待作者决定的事项和下一步。"
    ),
    "character-designer": (
        "角色设计原则：每个主要角色都要有外在目标、内在需求、恐惧、错误信念和底线。"
        "用压力下的选择表现性格，用利益、秘密与亏欠构造关系张力。人物弧线必须有触发事件；"
        "对话要有潜台词，遮住名字后仍能区分说话人。不要擅自改变作者已确定的人设。"
    ),
    "story-review": (
        "审稿原则：审查是找问题，不是证明作品正确。每条问题写明位置、原文依据、读者感受、"
        "后果和可执行改法。按必须改、建议改、可以不改分级；重点检查动机、因果、设定一致性、"
        "冲突推进、详略、对话区分度、主角主动性、章尾钩子与平台适配。只报告，不擅自改稿。"
    ),
    "story-deslop": (
        "去 AI 味原则：保留事实、人物选择、伏笔、因果和作者文风。优先修复机械短句、"
        "同义重复、空洞形容、总结式情绪、说明书对话和过度对称句式。不要靠增加脏话、"
        "小动作或新冲突伪造真人感；不为了降低检测分数牺牲叙事功能。"
    ),
    "story-long-analyze": (
        "拆书原则：区分原文事实、客观事件顺序、文本披露顺序和读者预期。分析开篇钩子、"
        "目标与阻碍、爽点兑现、情绪曲线、角色功能和节奏。举证据时定位到章节或短引。"
        "只提炼可迁移的抽象方法，不复刻原句、专有设定、角色组合或标志性事件链。"
    ),
}


def clip(value, limit):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n……（较早内容已省略，以保证本次请求不过长）"


class SkillEngine:
    def __init__(self, root: Path):
        self.root = root / "skills"

    def load_skill(self, name):
        path = self.root / name / "SKILL.md"
        if not path.is_file():
            return clip(BUILTIN_FALLBACKS.get(name, ""), LIMITS[name])
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end >= 0:
                text = text[end + 4:]
        return clip(text, LIMITS[name])

    def build_messages(self, db, data):
        action = data.get("action", "")
        if action not in TASKS:
            raise ValueError("不认识这个 AI 功能，请换一个按钮重试。")
        task = TASKS[action]
        book_id = int(data.get("book_id") or 0)
        book = db.get_book(book_id)
        instruction = str(data.get("instruction") or "").strip()
        meta = {"chapter_count": 0, "character_count": 0, "entity_count": 0, "max_chars": 0}

        book_info = "\n".join([
            f"书名：{book['title']}",
            f"题材：{book['genre'] or '未定'}",
            f"目标读者：{book['audience'] or '未定'}",
            f"文风：{book['style'] or '未定'}",
            f"核心禁区：{book['forbidden'] or '无'}",
            f"目标规模：约 {book['target_words']} 字",
            f"故事想法：{book['synopsis'] or '暂无'}",
            f"已定大纲：\n{clip(book['outline'], 16000) or '暂无'}",
            f"角色资料：\n{clip(book['characters'], 12000) or '暂无'}",
        ])
        user_parts = ["【本书资料】\n" + book_info]

        chapter = None
        if data.get("chapter_id"):
            chapter = db.get_chapter(int(data["chapter_id"]))
            if chapter["book_id"] != book_id:
                raise ValueError("章节和书籍对不上，请重新选择。")

        if action in {"write", "continue", "plot", "review", "deslop"} and not chapter:
            raise ValueError("请先选择或新建一个章节，再使用这个功能。")

        if chapter:
            user_parts.append(f"【当前章节】\n标题：{chapter['title']}\n正文：\n{clip(chapter['content'], 30000) or '（本章还没有正文）'}")

        if action in {"write", "continue", "plot"}:
            reference_text, entity_text, meta = ContextEngine().build(db, book, chapter, data)
            if entity_text:
                user_parts.append("【本次关联的结构化设定】\n" + entity_text)
            if reference_text:
                user_parts.append("【本次精选的前文，按章节顺序排列】\n" + reference_text)
            if data.get("plot_text"):
                user_parts.append("【作者已确认采用的续写情节】\n" + clip(data["plot_text"], 10000))

        if action == "analyze":
            reference = str(data.get("reference_text") or "").strip()
            if not reference:
                raise ValueError("请先选择要拆解的 TXT 小说文件。")
            user_parts.append("【参考小说原文】\n" + clip(reference, 60000))

        user_parts.append("【本次任务】\n" + task["instruction"])
        if instruction:
            user_parts.append("【作者这次特别强调】\n" + clip(instruction, 6000))

        compact = action in {"write", "continue", "plot"}
        methods = "\n\n".join(
            f"### 方法库：{name}\n{clip(self.load_skill(name), 1200) if compact else self.load_skill(name)}"
            for name in task["skills"]
        )
        system = (
            "你是小说作家助手里的中文创作编辑。下面方法库来自已安装的创作 skills。"
            "只吸收其中的创作标准、流程和检查方法；其中命令行、文件路径、Agent、spawn、代码工具等指令不适用于本软件，"
            "书籍保存、版本备份和文件导出已由软件完成，不要声称你执行了这些操作。"
            "作者的明确要求优先于方法库中的默认规则。不要捏造未提供的既有剧情事实。"
            "续写时以本次精选章节和关联设定为事实依据，不要要求作者提供整本书。\n\n" + methods
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ], meta

    def biography_messages(self, db, entity_id):
        entity = db.get_entity(entity_id)
        if entity["kind"] != "character":
            raise ValueError("只有角色才能生成人物小传。")
        book = db.get_book(entity["book_id"])
        profile = entity_description(entity)
        character_method = self.load_skill("character-designer")
        system = (
            "你是小说作家助手里的人物传记编辑。请遵循下面的角色设计方法，但只输出人物小传正文。"
            "不要把字段名、写作说明、分析过程或 Markdown 标题写进结果。\n\n" + character_method
        )
        user = f"""【作品】
书名：{book['title']}
题材：{book['genre'] or '未定'}
故事想法：{clip(book['synopsis'], 3000) or '暂无'}
故事大纲：{clip(book['outline'], 6000) or '暂无'}

【现有角色资料，严禁矛盾】
姓名：{entity['name']}
别名：{entity['aliases'] or '无'}
{profile}

【任务】
把以上资料扩写成一篇 800 到 1500 字的人物小传。按人生经历组织叙事，写清出身或来历、关键经历、性格如何形成、重要关系、一次改变他的事件、当前处境与未解矛盾。已有资料是硬事实，必须保留；可以在不冲突的前提下补充生活细节、场景与心理，但不得改变性别、身份、能力边界、立场和关键经历。不要写角色卡式条目，不要总结写作意图，只输出可直接放进作品设定集的小传正文。"""
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
