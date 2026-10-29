const $ = (id) => document.getElementById(id);
const state = {
  books: [], book: null, chapter: null, settings: null,
  dirty: false, saving: false, saveTimer: null,
  action: "write", aiText: "", referenceText: "", generating: false,
  context: {max_chars:50000, chapter_ids:[], entity_ids:null}, plotText: "",
  contextChapterDraft: new Set(), contextEntityDraft: new Set(), contextKind: "character",
  settingsKind: "character", editingEntity: null, aliasValues: [],
};
const actionNames = {start:"帮我开书",outline:"写大纲",character:"设计人物",write:"写本章",plot:"续写情节",continue:"续写正文",review:"审查本章",deslop:"去 AI 味",analyze:"拆解参考书"};
const entityNames = {character:"角色",background:"背景",faction:"势力",location:"地点",item:"物品"};
const entityMeta = {
  character:{label:"角色",icon:"♙",description:"角色档案、性格、背景与人物小传。"},
  background:{label:"背景",icon:"▧",description:"时代、历史、世界观与重要事件。"},
  faction:{label:"势力",icon:"⚑",description:"组织、军团、阵营与权力关系。"},
  location:{label:"地点",icon:"⌖",description:"城市、遗迹、战场与空间规则。"},
  item:{label:"物品",icon:"◇",description:"器物、遗物、武器与特殊道具。"},
};
const apiProviders = {
  platform:{base:"https://api.moonshot.cn/v1", model:"kimi-k3.1-pro", label:"开放平台"},
  code:{base:"https://api.kimi.com/coding/v1", model:"k3.1-pro", label:"Kimi Code"},
};
let toastTimer;
let aiPanelSaveTimer;
const EDITOR_FONT_KEY = "necronStudioEditorFontSize";
const EDITOR_FONT_SIZES = [12, 14, 16, 18, 20, 22];
const TOMB_AUTOSAVE_MS = 5 * 60 * 1000;

function toast(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").classList.add("show");
  toastTimer = setTimeout(() => $("toast").classList.remove("show"), 2800);
}

async function api(path, options = {}) {
  const config = {...options, headers:{"Content-Type":"application/json", ...(options.headers || {})}};
  const response = await fetch(path, config);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "操作没有成功，请再试一次。");
  return payload;
}

function openModal(id) { $(id).showModal(); }
function closeModal(id) { $(id).close(); }
function countWords(text) { return (text || "").replace(/\s/g, "").length; }

function updateWords() {
  const current = state.chapter ? countWords($("chapterEditor").value) : 0;
  $("chapterWords").textContent = `本章 ${current} 字`;
  let total = current;
  if (state.book) {
    for (const volume of state.book.volumes) {
      for (const chapter of volume.chapters) {
        if (!state.chapter || chapter.id !== state.chapter.id) total += chapter.character_count || 0;
      }
    }
  }
  $("totalWords").textContent = `${total} 字`;
}

function setDirty(value) {
  state.dirty = value;
  $("saveStatus").textContent = value ? "有修改，正在等待保存…" : "已保存";
  $("saveStatus").classList.toggle("dirty", value);
}

function applyEditorFontSize(size, persist = true) {
  const chosen = EDITOR_FONT_SIZES.includes(Number(size)) ? Number(size) : 18;
  $("fontSizeLabel").textContent = chosen;
  $("chapterEditor").style.fontSize = chosen + "px";
  if (persist) {
    try {
      localStorage.setItem(EDITOR_FONT_KEY, String(chosen));
    } catch {}
  }
}

async function autosaveToTomb() {
  if (!state.chapter) return;
  try {
    await saveCurrent(false, "每五分钟自动保存", true);
    toast("你的知识正在存入墓穴");
  } catch (error) {
    showError(error);
  }
}

function renderBookOptions() {
  const select = $("bookSelect");
  select.replaceChildren();
  if (!state.books.length) {
    const option = new Option("还没有小说", "");
    select.add(option);
    return;
  }
  for (const book of state.books) select.add(new Option(book.title, book.id));
  if (state.book) select.value = state.book.id;
  $("deleteBookButton").disabled = !state.book;
}

function readWorkspacePosition() {
  try {
    return JSON.parse(localStorage.getItem("necronStudioPosition") || "null") || {};
  } catch {
    return {};
  }
}

function saveWorkspacePosition(bookId, chapterId) {
  try {
    localStorage.setItem("necronStudioPosition", JSON.stringify({book_id:bookId, chapter_id:chapterId}));
  } catch {}
}

async function loadBooks(preferredId = null, openPreferred = true) {
  const payload = await api("/api/books");
  state.books = payload.books;
  renderBookOptions();
  if (openPreferred) {
    const saved = readWorkspacePosition();
    const savedBookExists = state.books.some(book => book.id === Number(saved.book_id));
    const id = preferredId || (state.book && state.book.id) || (savedBookExists ? Number(saved.book_id) : null) || (state.books[0] && state.books[0].id);
    if (id) await loadBook(id, preferredId ? null : saved.chapter_id);
    else showEmpty();
  }
}

function showEmpty() {
  state.book = null;
  state.chapter = null;
  $("currentBookName").textContent = "还没有选择书籍";
  $("chapterList").innerHTML = '<div class="empty-small">新建一本书后，在这里管理章节</div>';
  $("editorEmpty").classList.remove("hidden");
  $("editorContent").classList.add("hidden");
  updateWords();
}

async function loadBook(id, preferredChapterId = null) {
  if (state.book && state.book.id !== Number(id)) {
    saveAiPanelState();
    persistCurrentContext();
  }
  await saveCurrent();
  const payload = await api(`/api/books/${id}`);
  state.book = payload.book;
  state.chapter = null;
  applyStoredContextForBook(state.book.id);
  applyStoredAiPanel(state.book.id);
  $("currentBookName").textContent = state.book.title;
  renderBookOptions();
  renderChapters();
  const chapters = state.book.volumes.flatMap(v => v.chapters);
  const preferred = preferredChapterId ? chapters.find(chapter => chapter.id === Number(preferredChapterId)) : null;
  const target = preferred || chapters[chapters.length - 1];
  if (target) await selectChapter(target.id);
  else {
    $("editorEmpty").classList.remove("hidden");
    $("editorContent").classList.add("hidden");
    $("editorEmpty").querySelector("h1").textContent = "这本书已经准备好了";
    $("editorEmpty").querySelector("p").textContent = "点左侧“＋ 新章节”，开始写第一章。";
    updateWords();
  }
}

function renderChapters() {
  const list = $("chapterList");
  list.replaceChildren();
  if (!state.book) return;
  let chapterNumber = 0;
  for (const volume of state.book.volumes) {
    const heading = document.createElement("div");
    heading.className = "volume-title";
    heading.textContent = volume.title;
    list.appendChild(heading);
    for (const chapter of volume.chapters) {
      chapterNumber += 1;
      const button = document.createElement("button");
      button.className = "chapter-item" + (state.chapter && state.chapter.id === chapter.id ? " active" : "");
      const number = document.createElement("span");
      number.className = "chapter-number";
      number.textContent = String(chapterNumber).padStart(2, "0");
      const name = document.createElement("span");
      name.className = "chapter-name";
      name.textContent = chapter.title;
      name.title = chapter.title;
      button.append(number, name);
      button.onclick = () => selectChapter(chapter.id).catch(showError);
      list.appendChild(button);
    }
  }
  if (!chapterNumber) list.innerHTML = '<div class="empty-small">还没有章节<br>点上方“＋ 新章节”</div>';
}

function centerCurrentChapter() {
  requestAnimationFrame(() => {
    const list = $("chapterList");
    const active = list.querySelector(".chapter-item.active");
    if (!active) return;
    const listRect = list.getBoundingClientRect();
    const activeRect = active.getBoundingClientRect();
    const target = activeRect.top - listRect.top - (list.clientHeight - activeRect.height) / 2;
    list.scrollTop = Math.max(0, list.scrollTop + target);
  });
}

async function selectChapter(id) {
  if (state.chapter && state.chapter.id === id) return;
  await saveCurrent();
  const payload = await api(`/api/chapters/${id}`);
  state.chapter = payload.chapter;
  $("chapterTitle").value = state.chapter.title;
  $("chapterEditor").value = state.chapter.content;
  $("editorEmpty").classList.add("hidden");
  $("editorContent").classList.remove("hidden");
  setDirty(false);
  if (state.book) saveWorkspacePosition(state.book.id, state.chapter.id);
  renderChapters();
  centerCurrentChapter();
  updateWords();
  $("chapterEditor").focus();
}

async function saveCurrent(manual = false, reason = "手动保存", force = false) {
  clearTimeout(state.saveTimer);
  if (!state.chapter || (!state.dirty && !manual && !force)) return;
  if (state.saving) {
    await new Promise(resolve => setTimeout(resolve, 250));
    if (state.saving) return;
  }
  const chapterId = state.chapter.id;
  const title = $("chapterTitle").value.trim() || "未命名章节";
  const content = $("chapterEditor").value;
  state.saving = true;
  $("saveStatus").textContent = "正在保存…";
  try {
    const payload = await api(`/api/chapters/${chapterId}`, {
      method:"PUT",
      body:JSON.stringify({title, content, snapshot:manual, reason}),
    });
    if (state.chapter && state.chapter.id === chapterId) {
      state.chapter = payload.chapter;
      if ($("chapterEditor").value === content && $("chapterTitle").value.trim() === title) setDirty(false);
      const entry = state.book.volumes.flatMap(v => v.chapters).find(c => c.id === chapterId);
      if (entry) Object.assign(entry, {title:payload.chapter.title, character_count:content.length, updated_at:payload.chapter.updated_at});
      renderChapters();
      updateWords();
    }
    if (manual) toast("已保存，旧正文也留好了");
  } catch (error) {
    $("saveStatus").textContent = "这次没存上，请再点保存";
    throw error;
  } finally {
    state.saving = false;
  }
}

function showError(error) {
  console.error(error);
  toast(error.message || String(error));
  if (state.generating) setAiStatus(error.message || String(error), "error");
}

async function createBook(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target).entries());
  const payload = await api("/api/books", {method:"POST", body:JSON.stringify(data)});
  event.target.reset();
  event.target.elements.target_words.value = 100000;
  closeModal("newBookModal");
  await loadBooks(payload.book.id);
  toast("小说建好了，接下来可以让 AI 帮你开书");
}

async function createChapter() {
  if (!state.book) return openModal("newBookModal");
  await saveCurrent();
  const number = state.book.volumes.flatMap(v => v.chapters).length + 1;
  const title = prompt("这一章叫什么名字？", `第${number}章 `);
  if (title === null) return;
  const payload = await api(`/api/books/${state.book.id}/chapters`, {method:"POST", body:JSON.stringify({title})});
  const bookPayload = await api(`/api/books/${state.book.id}`);
  state.book = bookPayload.book;
  state.chapter = null;
  renderChapters();
  await selectChapter(payload.chapter.id);
}

function forgetBookUiState(bookId) {
  for (const key of ["necronStudioAiPanels", "necronStudioContexts", "necronStudioSettingsLibraries"]) {
    try {
      const map = JSON.parse(localStorage.getItem(key) || "{}") || {};
      delete map[String(bookId)];
      localStorage.setItem(key, JSON.stringify(map));
    } catch {}
  }
  try {
    const saved = JSON.parse(localStorage.getItem("necronStudioPosition") || "null");
    if (saved && Number(saved.book_id) === Number(bookId)) localStorage.removeItem("necronStudioPosition");
  } catch {}
}

async function deleteBook() {
  if (!state.book) return toast("当前没有可删除的书籍");
  await saveCurrent();
  const book = state.book;
  const chapterCount = book.volumes.reduce((total, volume) => total + volume.chapters.length, 0);
  if (!confirm(`确定删除《${book.title}》吗？\n\n这本书共有 ${chapterCount} 章。删除前会自动导出一份完整 TXT 备份，放在“已删除书籍”文件夹。`)) return;
  const button = $("deleteBookButton");
  button.disabled = true;
  try {
    await api(`/api/books/${book.id}`, {method:"DELETE"});
    forgetBookUiState(book.id);
    state.book = null;
    state.chapter = null;
    await loadBooks();
    toast("书籍已删除，完整备份已保存到“已删除书籍”文件夹");
  } finally {
    button.disabled = !state.book;
  }
}

async function readTextFile(file) {
  const buffer = await file.arrayBuffer();
  try {
    return new TextDecoder("utf-8", {fatal:true}).decode(buffer);
  } catch {
    return new TextDecoder("gb18030").decode(buffer);
  }
}

async function importChapters(files) {
  if (!state.book) return openModal("newBookModal");
  if (!files.length) return;
  await saveCurrent();
  const button = $("importChaptersButton");
  button.disabled = true;
  button.textContent = "正在读取…";
  try {
    const selected = Array.from(files);
    const imported = [];
    for (const file of selected) imported.push({name:file.name, content:await readTextFile(file)});
    const preview = imported.slice(0, 5).map(file => file.name).join("\n");
    const more = imported.length > 5 ? `\n……另外 ${imported.length - 5} 个文件` : "";
    if (!confirm(`准备把 ${imported.length} 个文件追加到“${state.book.title}”：\n\n${preview}${more}\n\n软件会自动识别文件里的“第X章”并拆分。原章节不会覆盖，确定导入吗？`)) return;
    button.textContent = "正在导入…";
    const payload = await api(`/api/books/${state.book.id}/import-chapters`, {
      method:"POST", body:JSON.stringify({files:imported}),
    });
    const bookPayload = await api(`/api/books/${state.book.id}`);
    state.book = bookPayload.book;
    state.chapter = null;
    renderChapters();
    await selectChapter(payload.first_chapter.id);
    toast(`成功导入 ${payload.count} 章，已打开第一章`);
  } finally {
    $("batchImportInput").value = "";
    button.disabled = false;
    button.textContent = "批量导入";
  }
}

async function splitChapter() {
  if (!state.chapter) return toast("请先选择需要分章的章节");
  await saveCurrent();
  if (!confirm("按正文里的“第X章”标题自动拆分吗？\n\n整章原文会先存进历史版本，可以恢复。")) return;
  const button = $("splitChapterButton");
  button.disabled = true;
  button.textContent = "正在分章…";
  try {
    const chapterId = state.chapter.id;
    const payload = await api(`/api/chapters/${chapterId}/split`, {method:"POST", body:"{}"});
    const bookPayload = await api(`/api/books/${state.book.id}`);
    state.book = bookPayload.book;
    state.chapter = null;
    renderChapters();
    await selectChapter(chapterId);
    toast(`已拆成 ${payload.count} 章，原整章已保留在历史版本`);
  } finally {
    button.disabled = false;
    button.textContent = "自动分章";
  }
}

async function deleteChapter() {
  if (!state.chapter) return;
  if (!confirm(`确定删除“${state.chapter.title}”吗？\n\n删除前会自动留一个旧版本，但这个版本以后不容易找回。建议先导出本章。`)) return;
  const bookId = state.book.id;
  await api(`/api/chapters/${state.chapter.id}`, {method:"DELETE"});
  state.chapter = null;
  await loadBook(bookId);
  toast("章节已删除");
}

function openBookInfo() {
  if (!state.book) return toast("请先新建或选择一本书");
  const form = $("bookInfoForm");
  for (const key of ["title","genre","synopsis","outline","characters"]) form.elements[key].value = state.book[key] || "";
  openModal("bookInfoModal");
}

function saveSettingsLibraryKind() {
  if (!state.book) return;
  let map = {};
  try {
    map = JSON.parse(localStorage.getItem("necronStudioSettingsLibraries") || "{}") || {};
  } catch {}
  map[String(state.book.id)] = state.settingsKind;
  try {
    localStorage.setItem("necronStudioSettingsLibraries", JSON.stringify(map));
  } catch {}
}

function openSettingsLibrary() {
  if (!state.book) return toast("请先新建或选择一本书");
  let savedKind = "character";
  try {
    const map = JSON.parse(localStorage.getItem("necronStudioSettingsLibraries") || "{}") || {};
    if (entityMeta[map[String(state.book.id)]]) savedKind = map[String(state.book.id)];
  } catch {}
  state.settingsKind = savedKind;
  renderSettingsLibrary();
  openModal("settingsLibraryModal");
}

function renderSettingsLibrary() {
  const nav = $("settingsCategoryNav");
  nav.replaceChildren();
  for (const [kind, meta] of Object.entries(entityMeta)) {
    const entities = (state.book.entities || []).filter(entity => entity.kind === kind);
    const row = document.createElement("div");
    row.className = "settings-category" + (state.settingsKind === kind ? " selected" : "");
    const select = document.createElement("button");
    select.type = "button";
    select.className = "settings-category-select";
    const icon = document.createElement("span");
    icon.className = "settings-icon";
    icon.textContent = meta.icon;
    const label = document.createElement("span");
    label.textContent = meta.label;
    const count = document.createElement("em");
    count.textContent = entities.length;
    const chevron = document.createElement("b");
    chevron.textContent = state.settingsKind === kind ? "⌄" : "›";
    select.append(icon, label, count, chevron);
    select.onclick = () => {
      state.settingsKind = kind;
      saveSettingsLibraryKind();
      renderSettingsLibrary();
    };
    const add = document.createElement("button");
    add.type = "button";
    add.className = "settings-category-add";
    add.textContent = "＋";
    add.title = `新增${meta.label}`;
    add.onclick = () => openEntity(null, kind);
    row.append(select, add);
    nav.appendChild(row);
    if (state.settingsKind === kind) {
      const childList = document.createElement("div");
      childList.className = "settings-child-list";
      if (!entities.length) {
        const empty = document.createElement("span");
        empty.textContent = `暂无${meta.label}`;
        childList.appendChild(empty);
      }
      for (const entity of entities) {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "settings-child";
        item.textContent = entity.name;
        item.onclick = () => openEntity(entity);
        childList.appendChild(item);
      }
      nav.appendChild(childList);
    }
  }
  renderSettingsMain();
}

function renderSettingsMain() {
  const meta = entityMeta[state.settingsKind];
  $("settingsSectionTitle").textContent = meta.label;
  $("settingsSectionDesc").textContent = meta.description;
  $("settingsAddEntityButton").textContent = `＋ 新增${meta.label}`;
  const root = $("settingsEntityList");
  root.replaceChildren();
  const entities = (state.book.entities || []).filter(entity => entity.kind === state.settingsKind);
  if (!entities.length) {
    const empty = document.createElement("div");
    empty.className = "settings-empty";
    empty.innerHTML = `<span>${meta.icon}</span><strong>尚无${meta.label}档案</strong><small>建立档案后，续写时可单独关联。</small>`;
    const button = document.createElement("button");
    button.className = "primary-button small";
    button.textContent = `建立第一份${meta.label}档案`;
    button.onclick = () => openEntity(null, state.settingsKind);
    empty.appendChild(button);
    root.appendChild(empty);
    return;
  }
  for (const entity of entities) {
    let fields = {};
    try { fields = JSON.parse(entity.fields_json || "{}"); } catch { fields = {}; }
    const card = document.createElement("button");
    card.type = "button";
    card.className = "settings-entity-card";
    const glyph = document.createElement("span");
    glyph.className = "entity-card-glyph";
    glyph.textContent = meta.icon;
    const body = document.createElement("span");
    body.className = "entity-card-body";
    const name = document.createElement("strong");
    name.textContent = entity.name;
    const detail = document.createElement("small");
    const bits = [];
    if (entity.aliases) bits.push(`别名 ${entity.aliases}`);
    if (fields.gender) bits.push(fields.gender);
    if (fields.tags && fields.tags.length) bits.push(fields.tags.join("、"));
    detail.textContent = bits.join(" · ") || (meta.label === "角色" ? "尚未填写角色资料" : "尚未填写详细资料");
    body.append(name, detail);
    if (state.settingsKind === "character" && (fields.background || fields.biography)) {
      const preview = document.createElement("p");
      preview.textContent = (fields.biography || fields.background || "").slice(0, 90);
      body.appendChild(preview);
    }
    const arrow = document.createElement("b");
    arrow.textContent = "›";
    card.append(glyph, body, arrow);
    card.onclick = () => openEntity(entity);
    root.appendChild(card);
  }
}

function parseAliases(value) {
  return String(value || "").split(/[,，、]/).map(item => item.trim()).filter(Boolean);
}

function renderAliasChips() {
  const root = $("aliasChips");
  root.replaceChildren();
  state.aliasValues.forEach((alias, index) => {
    const chip = document.createElement("span");
    chip.textContent = alias;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.onclick = () => {state.aliasValues.splice(index, 1);renderAliasChips();};
    chip.appendChild(remove);
    root.appendChild(chip);
  });
}

function addAlias() {
  const input = $("aliasInput");
  const values = parseAliases(input.value);
  for (const value of values) {
    if (state.aliasValues.length >= 12) break;
    if (!state.aliasValues.includes(value)) state.aliasValues.push(value);
  }
  input.value = "";
  renderAliasChips();
}

function updateEntityCounters() {
  $("charNameCount").textContent = `${$("characterName").value.length} / 10`;
  $("personalityCount").textContent = `${$("characterPersonality").value.length} / 500`;
  $("backgroundCount").textContent = `${$("characterBackground").value.length} / 500`;
  $("biographyCount").textContent = `${$("characterBiography").value.length} / 6000`;
}

function openEntity(entity = null, kind = state.settingsKind) {
  const meta = entityMeta[kind];
  state.editingEntity = entity;
  state.aliasValues = parseAliases(entity ? entity.aliases : "");
  const isCharacter = kind === "character";
  $("entityForm").reset();
  $("entityKind").value = kind;
  $("entityModalTitle").textContent = entity ? `编辑${meta.label} · ${entity.name}` : `新建${meta.label}`;
  $("entityModalHelp").textContent = isCharacter ? "人物小传会根据以上资料扩写，不改变既定事实。" : meta.description;
  $("characterFields").classList.toggle("hidden", !isCharacter);
  $("genericFields").classList.toggle("hidden", isCharacter);
  $("deleteEntityButton").classList.toggle("hidden", !entity);
  if (isCharacter) {
    let fields = {};
    try { fields = JSON.parse(entity && entity.fields_json || "{}"); } catch { fields = {}; }
    $("characterName").value = entity ? entity.name : "";
    $("characterPersonality").value = fields.personality || "";
    $("characterBackground").value = fields.background || (entity && entity.content) || "";
    $("characterBiography").value = fields.biography || "";
    $("characterTag").value = fields.tags && fields.tags.length ? fields.tags[0] : "";
    const gender = fields.gender || "未知";
    const radio = document.querySelector(`#entityForm input[name="gender"][value="${gender}"]`);
    if (radio) radio.checked = true;
    renderAliasChips();
  } else {
    $("genericName").value = entity ? entity.name : "";
    $("genericAliases").value = entity ? entity.aliases : "";
    $("genericContent").value = entity ? entity.content : "";
  }
  updateEntityCounters();
  openModal("entityModal");
}

async function persistEntity(closeAfter = true, quiet = false) {
  const kind = $("entityKind").value;
  const isCharacter = kind === "character";
  let name = (isCharacter ? $("characterName").value : $("genericName").value).trim();
  if (!name) throw new Error(isCharacter ? "请先填写角色名称。" : "请先填写名称。");
  const data = {kind, name};
  if (isCharacter) {
    addAlias();
    data.aliases = state.aliasValues.join(",");
    data.fields = {
      gender: (document.querySelector('#entityForm input[name="gender"]:checked') || {}).value || "未知",
      personality: $("characterPersonality").value,
      tags: $("characterTag").value ? [$("characterTag").value] : [],
      background: $("characterBackground").value,
      biography: $("characterBiography").value,
    };
  } else {
    data.aliases = $("genericAliases").value;
    data.content = $("genericContent").value;
  }
  const id = state.editingEntity ? state.editingEntity.id : "";
  const path = id ? `/api/books/${state.book.id}/entities/${id}` : `/api/books/${state.book.id}/entities`;
  const payload = await api(path, {method:id ? "PUT" : "POST", body:JSON.stringify(data)});
  const index = state.book.entities.findIndex(entity => entity.id === payload.entity.id);
  if (index >= 0) state.book.entities[index] = payload.entity;
  else state.book.entities.push(payload.entity);
  state.editingEntity = payload.entity;
  if (!quiet) toast("档案已保存");
  if (closeAfter) {
    closeModal("entityModal");
    renderSettingsLibrary();
  }
  return payload.entity;
}

async function saveEntity(event) {
  event.preventDefault();
  await persistEntity(true);
}

async function deleteEntity() {
  const id = state.editingEntity && state.editingEntity.id;
  if (!id || !confirm("确定删除这份档案吗？正文和旧版本不受影响。")) return;
  await api(`/api/books/${state.book.id}/entities/${id}`, {method:"DELETE"});
  state.book.entities = state.book.entities.filter(entity => entity.id !== id);
  state.editingEntity = null;
  closeModal("entityModal");
  renderSettingsLibrary();
  toast("档案已删除");
}

async function generateBiography() {
  const button = $("generateBiographyButton");
  if (!$("characterName").value.trim()) return toast("请先填写角色名称");
  button.disabled = true;
  const oldText = button.textContent;
  button.textContent = "正在从墓库提取记忆…";
  try {
    const entity = await persistEntity(false, true);
    const payload = await api(`/api/entities/${entity.id}/biography`, {method:"POST", body:"{}"});
    $("characterBiography").value = payload.biography;
    updateEntityCounters();
    await persistEntity(false, true);
    toast("人物小传已生成并保存，可以继续修改");
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
}

async function saveBookInfo(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target).entries());
  const payload = await api(`/api/books/${state.book.id}`, {method:"PUT", body:JSON.stringify(data)});
  state.book = payload.book;
  $("currentBookName").textContent = state.book.title;
  closeModal("bookInfoModal");
  await loadBooks(state.book.id, false);
  toast("作品资料已保存");
}

function applyApiProvider() {
  const preset = apiProviders[$("apiProvider").value];
  if (!preset) return;
  $("baseUrl").value = preset.base;
  $("modelName").value = preset.model;
}

function openSettings() {
  if (state.settings) {
    $("baseUrl").value = state.settings.base_url;
    $("modelName").value = state.settings.model;
    const base = state.settings.base_url || "";
    $("apiProvider").value = base.includes("moonshot") ? "platform" : base.includes("kimi.com/coding") ? "code" : "custom";
    $("keySavedLabel").textContent = state.settings.has_api_key ? "（已保存，留空就不变）" : "";
  }
  $("connectionResult").textContent = "";
  openModal("settingsModal");
}

async function saveSettings(close = true) {
  const payload = await api("/api/settings", {method:"POST", body:JSON.stringify({
    api_key:$("apiKey").value, base_url:$("baseUrl").value, model:$("modelName").value,
  })});
  state.settings = payload;
  $("apiKey").value = "";
  $("modelLabel").textContent = payload.model;
  $("apiDot").classList.toggle("ready", payload.has_api_key);
  if (close) closeModal("settingsModal");
  return payload;
}

async function testApi() {
  const button = $("testApiButton");
  button.disabled = true;
  $("connectionResult").textContent = "正在连接，请稍等……";
  try {
    await saveSettings(false);
    const payload = await api("/api/ai/test", {method:"POST", body:"{}"});
    $("connectionResult").textContent = "✓ " + payload.message;
    $("connectionResult").style.color = "#3a936b";
  } catch (error) {
    $("connectionResult").textContent = error.message;
    $("connectionResult").style.color = "#b7574d";
  } finally {
    button.disabled = false;
  }
}

async function clearKey() {
  if (!confirm("要清除保存在这台电脑上的 API Key 吗？清除后 AI 功能会暂停，书稿不受影响。")) return;
  await api("/api/settings/clear-key", {method:"POST", body:"{}"});
  state.settings = await api("/api/settings");
  $("keySavedLabel").textContent = "";
  $("apiDot").classList.remove("ready");
  toast("本机 Key 已清除");
}

function previousChapters() {
  return state.book.volumes.flatMap(volume => volume.chapters)
    .filter(chapter => chapter.position < state.chapter.position)
    .sort((a, b) => b.position - a.position);
}

function storedContexts() {
  try {
    return JSON.parse(localStorage.getItem("necronStudioContexts") || "{}") || {};
  } catch {
    return {};
  }
}

function applyStoredContextForBook(bookId) {
  const saved = storedContexts()[String(bookId)];
  const validChapters = new Set(state.book.volumes.flatMap(volume => volume.chapters).map(chapter => chapter.id));
  const validEntities = new Set((state.book.entities || []).map(entity => entity.id));
  const chapterIds = saved && Array.isArray(saved.chapter_ids)
    ? saved.chapter_ids.map(Number).filter(id => validChapters.has(id))
    : [];
  const entityIds = saved && Array.isArray(saved.entity_ids)
    ? saved.entity_ids.map(Number).filter(id => validEntities.has(id))
    : null;
  state.context = {
    max_chars: Number(saved && saved.max_chars) || 50000,
    chapter_ids: chapterIds,
    entity_ids: entityIds,
  };
  updateContextSummary();
}

function persistCurrentContext() {
  if (!state.book) return;
  const map = storedContexts();
  map[String(state.book.id)] = {
    max_chars: state.context.max_chars,
    chapter_ids: state.context.chapter_ids,
    entity_ids: state.context.entity_ids,
  };
  try {
    localStorage.setItem("necronStudioContexts", JSON.stringify(map));
  } catch {}
  updateContextSummary();
}

function updateContextSummary() {
  const chapters = state.context.chapter_ids.length;
  const entities = state.context.entity_ids ? state.context.entity_ids.length : 0;
  const chapterLabel = chapters ? `${chapters} 章指定` : "章节自动精选";
  const entityLabel = entities ? `${entities} 条设定` : "设定自动精选";
  $("contextSummary").textContent = `${chapterLabel} · ${entityLabel} · 最多 ${state.context.max_chars / 10000} 万字`;
}

function commitContextDraft() {
  state.context.max_chars = Number($("contextBudget").value);
  state.context.chapter_ids = Array.from(state.contextChapterDraft);
  state.context.entity_ids = state.contextEntityDraft.size ? Array.from(state.contextEntityDraft) : null;
  persistCurrentContext();
}

function renderContextChapters() {
  const root = $("contextChapterList");
  root.replaceChildren();
  const chapters = previousChapters();
  $("contextChapterCount").textContent = `${state.contextChapterDraft.size} / ${chapters.length}`;
  if (!chapters.length) {
    root.innerHTML = '<div class="context-empty">当前章之前还没有正文。</div>';
    return;
  }
  chapters.forEach((chapter, index) => {
    const label = document.createElement("label");
    label.className = "context-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = chapter.id;
    checkbox.checked = state.contextChapterDraft.has(chapter.id);
    checkbox.onchange = () => {
      if (checkbox.checked) state.contextChapterDraft.add(chapter.id);
      else state.contextChapterDraft.delete(chapter.id);
      $("contextChapterCount").textContent = `${state.contextChapterDraft.size} / ${chapters.length}`;
      commitContextDraft();
    };
    const body = document.createElement("span");
    body.className = "context-option-body";
    const title = document.createElement("strong");
    title.textContent = chapter.title;
    if (index < 2) {
      const badge = document.createElement("em");
      badge.textContent = index === 0 ? "最新章" : "最近章";
      title.appendChild(badge);
    }
    const detail = document.createElement("small");
    detail.textContent = `${chapter.character_count || 0} 字符`;
    body.append(title, detail);
    label.append(checkbox, body);
    root.appendChild(label);
  });
}

function renderContextEntityTabs() {
  const tabRoot = $("contextEntityTabs");
  tabRoot.replaceChildren();
  const entities = state.book.entities || [];
  for (const [kind, meta] of Object.entries(entityMeta)) {
    const all = entities.filter(entity => entity.kind === kind);
    const selected = all.filter(entity => state.contextEntityDraft.has(entity.id)).length;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "context-category-tab" + (state.contextKind === kind ? " active" : "");
    button.innerHTML = `<span>${meta.icon}</span><b>${meta.label}</b><em>${selected}/${all.length}</em>`;
    button.onclick = () => {
      state.contextKind = kind;
      renderContextEntityTabs();
      renderContextEntities();
    };
    tabRoot.appendChild(button);
  }
  $("contextEntityTotal").textContent = `${state.contextEntityDraft.size} 条已选`;
}

function renderContextEntities() {
  const root = $("contextEntityList");
  root.replaceChildren();
  const all = (state.book.entities || []).filter(entity => entity.kind === state.contextKind);
  const selected = all.filter(entity => state.contextEntityDraft.has(entity.id)).length;
  const meta = entityMeta[state.contextKind];
  $("contextEntityKindInfo").textContent = `${meta.label}已选 ${selected} / ${all.length} 条`;
  if (!all.length) {
    root.innerHTML = `<div class="context-empty">还没有${meta.label}档案。可以在“设定库”中创建。</div>`;
    renderContextEntityTabs();
    return;
  }
  all.forEach(entity => {
    const label = document.createElement("label");
    label.className = "context-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = entity.id;
    checkbox.checked = state.contextEntityDraft.has(entity.id);
    checkbox.onchange = () => {
      if (checkbox.checked) state.contextEntityDraft.add(entity.id);
      else state.contextEntityDraft.delete(entity.id);
      renderContextEntityTabs();
      $("contextEntityKindInfo").textContent = `${meta.label}已选 ${all.filter(item => state.contextEntityDraft.has(item.id)).length} / ${all.length} 条`;
      commitContextDraft();
    };
    const body = document.createElement("span");
    body.className = "context-option-body";
    const title = document.createElement("strong");
    title.textContent = entity.name;
    const detail = document.createElement("small");
    detail.textContent = entity.aliases ? `别名：${entity.aliases}` : meta.description;
    body.append(title, detail);
    label.append(checkbox, body);
    root.appendChild(label);
  });
  renderContextEntityTabs();
}

function openContext() {
  if (!state.book || !state.chapter) return toast("请先选择要续写的章节");
  $("contextBudget").value = state.context.max_chars;
  const chapters = previousChapters();
  const validChapterIds = new Set(chapters.map(chapter => chapter.id));
  state.contextChapterDraft = new Set(state.context.chapter_ids.map(Number).filter(id => validChapterIds.has(id)));
  if (!state.contextChapterDraft.size) {
    chapters.slice(0, 2).forEach(chapter => state.contextChapterDraft.add(chapter.id));
  }
  state.contextEntityDraft = new Set((state.context.entity_ids || []).map(Number));
  state.contextKind = "character";
  renderContextChapters();
  renderContextEntityTabs();
  renderContextEntities();
  openModal("contextModal");
}

function saveContext() {
  commitContextDraft();
  closeModal("contextModal");
}

function clearContext() {
  state.contextChapterDraft.clear();
  state.contextEntityDraft.clear();
  renderContextChapters();
  renderContextEntityTabs();
  renderContextEntities();
  commitContextDraft();
}

function selectLatestChapters() {
  state.contextChapterDraft.clear();
  previousChapters().slice(0, 2).forEach(chapter => state.contextChapterDraft.add(chapter.id));
  renderContextChapters();
  commitContextDraft();
}

function clearContextChapters() {
  state.contextChapterDraft.clear();
  renderContextChapters();
  commitContextDraft();
}

function selectAllEntitiesOfKind() {
  for (const entity of state.book.entities || []) {
    if (entity.kind === state.contextKind) state.contextEntityDraft.add(entity.id);
  }
  renderContextEntities();
  commitContextDraft();
}

function clearEntitiesOfKind() {
  for (const entity of state.book.entities || []) {
    if (entity.kind === state.contextKind) state.contextEntityDraft.delete(entity.id);
  }
  renderContextEntities();
  commitContextDraft();
}

function storedAiPanels() {
  try {
    return JSON.parse(localStorage.getItem("necronStudioAiPanels") || "{}") || {};
  } catch {
    return {};
  }
}

function saveAiPanelState() {
  if (!state.book) return;
  const map = storedAiPanels();
  map[String(state.book.id)] = {
    action: state.action,
    workflow: $("workflowPreset").value,
    instruction: $("aiInstruction").value,
    instruction_height: $("aiInstruction").style.height,
    output: state.aiText,
    output_scroll: $("aiOutput").scrollTop,
    status: $("aiStatus").textContent,
    status_type: $("aiStatus").classList.contains("error") ? "error" : $("aiStatus").classList.contains("success") ? "success" : "",
    scroll_top: document.querySelector(".ai-panel").scrollTop,
  };
  try {
    localStorage.setItem("necronStudioAiPanels", JSON.stringify(map));
  } catch {}
}

function applyStoredAiPanel(bookId) {
  const saved = storedAiPanels()[String(bookId)] || {};
  const action = actionNames[saved.action] ? saved.action : "write";
  selectAction(action, false);
  $("workflowPreset").value = saved.workflow || "";
  $("aiInstruction").value = saved.instruction || "";
  $("aiInstruction").style.height = saved.instruction_height || "";
  state.aiText = saved.output || "";
  $("aiOutput").textContent = state.aiText || "AI 写好的内容会显示在这里。";
  setAiStatus(
    saved.status || "选择功能，再点生成。结果不会自动覆盖正文。",
    saved.status_type || ""
  );
  updateAiButtons();
  requestAnimationFrame(() => {
    document.querySelector(".ai-panel").scrollTop = Number(saved.scroll_top) || 0;
    $("aiOutput").scrollTop = Number(saved.output_scroll) || 0;
  });
}

function selectAction(action, persist = true) {
  state.action = action;
  document.querySelectorAll("#actionGrid button").forEach(button => button.classList.toggle("selected", button.dataset.action === action));
  $("generateButton").textContent = `✦ 让 Kimi ${actionNames[action]}`;
  $("referenceRow").classList.toggle("hidden", action !== "analyze");
  const placeholders = {
    start:"补充你的想法，例如：轻松热血，不要后宫。", outline:"例如：先规划第一卷，大约 30 章。", character:"例如：设计一个嘴硬心软的师父。", write:"例如：本章 2500 字，主角第一次进城，结尾遇到追杀。", plot:"例如：提供三个走向，重点升级主角与守护者的矛盾。", continue:"例如：接着写 1500 字，不要换场景。", review:"可以留空，让 AI 全面审查。", deslop:"例如：保留对话，重点改叙述。", analyze:"可选择分析重点，例如：重点看黄金三章。",
  };
  $("aiInstruction").placeholder = placeholders[action];
  if (persist) saveAiPanelState();
}

function setAiStatus(message, type = "") {
  $("aiStatus").textContent = message;
  $("aiStatus").className = "ai-status" + (type ? " " + type : "");
}

function updateAiButtons() {
  const hasText = !!state.aiText;
  $("aiResultActions").classList.toggle("hidden", !hasText);
  const chapterAction = ["write","continue","deslop"].includes(state.action);
  $("insertAiButton").classList.toggle("hidden", !chapterAction);
  $("replaceAiButton").classList.toggle("hidden", !chapterAction);
  $("saveAiButton").classList.toggle("hidden", !["start","outline","character"].includes(state.action));
  $("saveAiButton").textContent = state.action === "character" ? "追加到角色资料" : "保存为大纲";
  $("plotToProseButton").classList.toggle("hidden", state.action !== "plot" || !hasText);
}

async function plotToProse() {
  state.plotText = state.aiText;
  selectAction("continue");
  await generateAi();
}

async function generateAi() {
  if (state.generating) return;
  if (!state.book) {
    openModal("newBookModal");
    return toast("先建一本书，AI 才知道你在写什么");
  }
  if (state.action === "analyze" && !state.referenceText) return toast("请先选择要拆解的 TXT 文件");
  await saveCurrent();
  state.generating = true;
  state.aiText = "";
  $("aiOutput").textContent = "";
  $("generateButton").disabled = true;
  $("outputLoading").classList.remove("hidden");
  updateAiButtons();
  setAiStatus("正在精选前文和关联设定……");
  let contextNote = "";
  const preset = $("workflowPreset").value;
  const instruction = [$("aiInstruction").value, preset].filter(Boolean).join("\n工作流要求：");
  try {
    const response = await fetch("/api/ai/generate", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
      action:state.action, book_id:state.book.id, chapter_id:state.chapter && state.chapter.id,
      instruction, reference_text:state.referenceText, context:state.context,
      plot_text:state.action === "continue" ? state.plotText : "",
    })});
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.error || "这次没有生成成功，请再试一次。");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream:true});
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "meta") {
          const meta = event.context;
          contextNote = meta.max_chars ? `参考 ${meta.chapter_count} 章 ${meta.character_count} 字 · ${meta.entity_count} 条设定` : "";
          if (contextNote) setAiStatus(contextNote);
        } else if (event.type === "delta") {
          state.aiText += event.content;
          $("aiOutput").textContent = state.aiText;
          $("aiOutput").scrollTop = $("aiOutput").scrollHeight;
          setAiStatus(`${contextNote}${contextNote ? " · " : ""}已生成 ${countWords(state.aiText)} 字`);
        } else if (event.type === "status") setAiStatus(event.message);
        else if (event.type === "error") throw new Error(event.message);
      }
    }
    if (!state.aiText) throw new Error("没有收到文字，请再试一次。");
    setAiStatus(`${contextNote}${contextNote ? " · " : ""}生成完成，正文尚未覆盖`, "success");
    updateAiButtons();
  } catch (error) {
    setAiStatus(error.message, "error");
    if (!state.aiText) $("aiOutput").textContent = "这次没有生成内容。你的正文没有被改动。";
  } finally {
    state.generating = false;
    $("generateButton").disabled = false;
    $("outputLoading").classList.add("hidden");
    saveAiPanelState();
  }
}

async function insertAi() {
  if (!state.chapter || !state.aiText) return toast("请先选择一个章节");
  const editor = $("chapterEditor");
  const start = editor.selectionStart;
  editor.setRangeText(state.aiText, start, editor.selectionEnd, "end");
  setDirty(true);
  await saveCurrent(true, "AI 插入前的正文");
  toast("已插入正文，插入前的版本已保留");
}

async function replaceAi() {
  if (!state.chapter || !state.aiText) return toast("请先选择一个章节");
  if (!confirm("用 AI 结果替换这一章吗？\n\n现在的正文会自动存进历史版本，可以恢复。")) return;
  $("chapterEditor").value = state.aiText;
  setDirty(true);
  await saveCurrent(true, "AI 替换前的正文");
}

async function saveAiToBook() {
  if (!state.aiText) return;
  if (state.action === "character") {
    const characters = (state.book.characters ? state.book.characters + "\n\n---\n\n" : "") + state.aiText;
    await api(`/api/books/${state.book.id}`, {method:"PUT", body:JSON.stringify({characters})});
    state.book.characters = characters;
  } else {
    if (state.book.outline && !confirm("这会替换原来的故事大纲。原大纲建议先复制备份，确定继续吗？")) return;
    await api(`/api/books/${state.book.id}`, {method:"PUT", body:JSON.stringify({outline:state.aiText})});
    state.book.outline = state.aiText;
  }
  toast("已存入作品资料");
}

async function copyAi() {
  if (!state.aiText) return;
  await navigator.clipboard.writeText(state.aiText);
  toast("已复制");
}

async function readReference(file) {
  state.referenceText = "";
  $("referenceFileName").textContent = file ? file.name : "只分析你提供的文本";
  if (!file) return;
  state.referenceText = await readTextFile(file);
  $("referenceFileName").textContent = `${file.name} · 约 ${countWords(state.referenceText)} 字`;
}

async function showVersions() {
  if (!state.chapter) return;
  const payload = await api(`/api/chapters/${state.chapter.id}/versions`);
  const list = $("versionsList");
  list.replaceChildren();
  if (!payload.versions.length) list.innerHTML = '<div class="empty-small">还没有旧版本。点“保存并留一个旧版本”后，就能在这里看到。</div>';
  for (const version of payload.versions) {
    const item = document.createElement("div");
    item.className = "version-item";
    const info = document.createElement("div");
    info.className = "version-info";
    const title = document.createElement("strong");
    title.textContent = version.title;
    const detail = document.createElement("small");
    detail.textContent = `${version.created_at} · ${version.reason} · ${version.character_count} 字符`;
    info.append(title, detail);
    const view = document.createElement("button");
    view.textContent = "查看";
    view.onclick = async () => {
      const data = await api(`/api/versions/${version.id}`);
      const preview = document.createElement("pre");
      preview.style.whiteSpace = "pre-wrap";
      preview.style.maxHeight = "300px";
      preview.style.overflow = "auto";
      preview.textContent = data.version.content || "（空章节）";
      item.after(preview);
      view.disabled = true;
    };
    const restore = document.createElement("button");
    restore.textContent = "恢复";
    restore.onclick = async () => {
      if (!confirm("恢复这个版本吗？现在的正文会先自动备份。")) return;
      await api(`/api/versions/${version.id}/restore`, {method:"POST", body:"{}"});
      closeModal("versionsModal");
      const currentId = state.chapter.id;
      state.chapter = null;
      await selectChapter(currentId);
      toast("旧版本已恢复");
    };
    item.append(info, view, restore);
    list.appendChild(item);
  }
  openModal("versionsModal");
}

function bindEvents() {
  document.querySelectorAll("[data-close]").forEach(button => button.onclick = () => closeModal(button.dataset.close));
  $("newBookButton").onclick = () => openModal("newBookModal");
  $("emptyNewBook").onclick = () => state.book ? createChapter().catch(showError) : openModal("newBookModal");
  $("newBookForm").onsubmit = event => createBook(event).catch(showError);
  $("deleteBookButton").onclick = () => deleteBook().catch(showError);
  $("bookSelect").onchange = event => loadBook(Number(event.target.value)).catch(showError);
  $("newChapterButton").onclick = () => createChapter().catch(showError);
  $("importChaptersButton").onclick = () => state.book ? $("batchImportInput").click() : openModal("newBookModal");
  $("batchImportInput").onchange = event => importChapters(event.target.files).catch(showError);
  $("chapterEditor").oninput = () => {setDirty(true);updateWords();clearTimeout(state.saveTimer);state.saveTimer=setTimeout(()=>saveCurrent().catch(showError),1400);};
  $("chapterTitle").oninput = $("chapterEditor").oninput;
  $("saveButton").onclick = () => saveCurrent(true).catch(showError);
  $("splitChapterButton").onclick = () => splitChapter().catch(showError);
  $("deleteChapterButton").onclick = () => deleteChapter().catch(showError);
  $("bookInfoButton").onclick = openBookInfo;
  $("bookInfoForm").onsubmit = event => saveBookInfo(event).catch(showError);
  $("settingsLibraryButton").onclick = openSettingsLibrary;
  $("newEntityButton").onclick = () => openEntity(null);
  $("settingsAddEntityButton").onclick = () => openEntity(null, state.settingsKind);
  $("entityForm").onsubmit = event => saveEntity(event).catch(showError);
  $("deleteEntityButton").onclick = () => deleteEntity().catch(showError);
  $("generateBiographyButton").onclick = () => generateBiography().catch(showError);
  $("aliasInput").onkeydown = event => {if(event.key === "Enter" || event.key === "，" || event.key === ",") {event.preventDefault();addAlias();}};
  $("aliasInput").onblur = addAlias;
  for (const id of ["characterName","characterPersonality","characterBackground","characterBiography"]) $(id).oninput = updateEntityCounters;
  $("contextButton").onclick = openContext;
  $("contextBudget").onchange = commitContextDraft;
  $("saveContextButton").onclick = saveContext;
  $("clearContextButton").onclick = clearContext;
  $("contextLatestButton").onclick = selectLatestChapters;
  $("contextClearChapters").onclick = clearContextChapters;
  $("contextSelectAllEntities").onclick = selectAllEntitiesOfKind;
  $("contextClearEntities").onclick = clearEntitiesOfKind;
  $("plotToProseButton").onclick = () => plotToProse().catch(showError);
  $("settingsButton").onclick = openSettings;
  $("apiProvider").onchange = applyApiProvider;
  $("settingsForm").onsubmit = async event => {event.preventDefault();await saveSettings();toast("API 设置已保存");};
  $("testApiButton").onclick = testApi;
  $("clearKeyButton").onclick = () => clearKey().catch(showError);
  $("helpButton").onclick = () => openModal("helpModal");
  $("exportButton").onclick = () => {if(state.book) location.href=`/api/books/${state.book.id}/export`;else toast("请先选择一本书");};
  $("exportChapterButton").onclick = async () => {await saveCurrent();location.href=`/api/chapters/${state.chapter.id}/export`;};
  $("versionsButton").onclick = () => showVersions().catch(showError);
  $("fontButton").onclick = () => {
    const current = Number($("fontSizeLabel").textContent);
    const index = EDITOR_FONT_SIZES.indexOf(current);
    applyEditorFontSize(EDITOR_FONT_SIZES[(index + 1) % EDITOR_FONT_SIZES.length]);
  };
  $("actionGrid").onclick = event => {if(event.target.dataset.action) selectAction(event.target.dataset.action);};
  $("workflowPreset").onchange = saveAiPanelState;
  $("aiInstruction").oninput = saveAiPanelState;
  document.querySelector(".ai-panel").addEventListener("scroll", () => {
    clearTimeout(aiPanelSaveTimer);
    aiPanelSaveTimer = setTimeout(saveAiPanelState, 180);
  });
  if (window.ResizeObserver) {
    new ResizeObserver(() => {
      clearTimeout(aiPanelSaveTimer);
      aiPanelSaveTimer = setTimeout(saveAiPanelState, 220);
    }).observe($("aiInstruction"));
  }
  $("generateButton").onclick = () => generateAi().catch(showError);
  $("insertAiButton").onclick = () => insertAi().catch(showError);
  $("replaceAiButton").onclick = () => replaceAi().catch(showError);
  $("saveAiButton").onclick = () => saveAiToBook().catch(showError);
  $("copyAiButton").onclick = () => copyAi().catch(showError);
  $("referenceFile").onchange = event => readReference(event.target.files[0]).catch(showError);
  window.addEventListener("beforeunload", event => {if(state.dirty){event.preventDefault();event.returnValue="";}});
}

async function init() {
  bindEvents();
  let savedFontSize = 18;
  try {
    savedFontSize = Number(localStorage.getItem(EDITOR_FONT_KEY)) || 18;
  } catch {}
  applyEditorFontSize(savedFontSize, false);
  setInterval(autosaveToTomb, TOMB_AUTOSAVE_MS);
  selectAction("write");
  try {
    state.settings = await api("/api/settings");
    $("modelLabel").textContent = state.settings.model;
    $("apiDot").classList.toggle("ready", state.settings.has_api_key);
    await loadBooks();
    if (!state.books.length) openModal("helpModal");
  } catch (error) {
    showError(error);
    setAiStatus("软件没有正常加载，请关闭启动窗口后重新打开。", "error");
  }
}

init();
