// The Chat page: ask, stream the answer, stack the turns, pick books and a model.
//
// The answer streams from POST /api/chat/stream as server-sent events. HTMX's
// SSE support only covers GET, so this script reads the stream with fetch.
(() => {
  "use strict";

  const MODEL_KEY = "librag.chat.model";
  const LABELS = {
    synthesis: "Synthesis",
    general: "General knowledge, not from your library",
  };

  const head = document.querySelector(".chat-head");
  const intro = document.querySelector(".chat-intro");
  const conversation = document.querySelector(".conversation");
  const form = document.querySelector("form.ask");
  const input = form.querySelector(".ask__input");
  const askButton = form.querySelector(".ask__bar button");
  const modelSelect = form.querySelector("select[name=model]");
  const toggle = form.querySelector(".picker__toggle");
  const panel = form.querySelector(".picker__panel");
  const allBox = panel.querySelector("input[data-all]");
  const bookBoxes = [...panel.querySelectorAll("input[name=book_ids]")];

  let turnCount = 0;
  let streaming = null;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // The model: remembered in the browser; a model no longer configured is ignored.

  const remembered = localStorage.getItem(MODEL_KEY);
  if (remembered && [...modelSelect.options].some((o) => o.value === remembered)) {
    modelSelect.value = remembered;
  }
  modelSelect.addEventListener("change", () => {
    localStorage.setItem(MODEL_KEY, modelSelect.value);
  });

  // The book picker.

  function groupOf(box) {
    return box.closest(".picker__group");
  }

  function syncPicker() {
    for (const group of panel.querySelectorAll(".picker__group")) {
      const books = [...group.querySelectorAll("input[name=book_ids]")];
      const author = group.querySelector("input[data-author]");
      const ticked = books.filter((b) => b.checked).length;
      author.checked = ticked === books.length;
      author.indeterminate = ticked > 0 && ticked < books.length;
    }
    const ticked = bookBoxes.filter((b) => b.checked).length;
    allBox.checked = ticked === bookBoxes.length;
    allBox.indeterminate = false;
    let label = "All indexed books";
    if (ticked === 0) label = "none";
    else if (ticked < bookBoxes.length) label = ticked === 1 ? "1 book" : `${ticked} books`;
    toggle.textContent = `Books: ${label} ▾`;
    updateAsk();
  }

  panel.addEventListener("change", (event) => {
    const box = event.target;
    if (box === allBox) {
      for (const b of bookBoxes) b.checked = box.checked;
    } else if (box.matches("input[data-author]")) {
      for (const b of groupOf(box).querySelectorAll("input[name=book_ids]")) {
        b.checked = box.checked;
      }
    }
    syncPicker();
  });

  function openPicker(open) {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
  }

  toggle.addEventListener("click", () => openPicker(panel.hidden));
  document.addEventListener("click", (event) => {
    if (!panel.hidden && !event.target.closest(".picker")) openPicker(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      openPicker(false);
      toggle.focus();
    }
  });

  // The ticked books to send as `book_ids`: [] for all of them, which is no
  // filter, so a book indexed later is searched too; null for none.
  function bookIds() {
    const ticked = bookBoxes.filter((b) => b.checked);
    if (!ticked.length) return null;
    return ticked.length === bookBoxes.length ? [] : ticked.map((b) => b.value);
  }

  // The ask bar: disabled while an answer streams, or with no book ticked.

  function updateAsk() {
    const busy = streaming !== null;
    const noBooks = bookIds() === null;
    input.disabled = busy;
    askButton.disabled = busy || noBooks;
    form.classList.toggle("ask--disabled", busy);
    for (const retry of conversation.querySelectorAll(".turn-error button")) {
      retry.disabled = busy || noBooks;
    }
  }

  function showConversation(started) {
    head.hidden = !started;
    intro.hidden = started;
  }

  // A turn: the question, the progress lines, the answer and its cited passages.

  function newTurn(question) {
    turnCount += 1;
    const section = element("section", "turn");
    section.dataset.turn = String(turnCount);
    section.append(element("p", "question", question));
    const status = element("ol", "stream-status");
    status.setAttribute("aria-live", "polite");
    status.append(element("li", "stream-status__step stream-status__step--active", "Searching your books…"));
    const answer = element("article", "answer");
    const sources = element("section", "sources");
    sources.setAttribute("aria-label", "Cited passages");
    sources.append(element("h3", "section-label", "Cited passages"));
    sources.hidden = true;
    section.append(status, answer, sources);
    return { question, section, status, answer, sources, parts: [], bookParagraph: null };
  }

  function showWriting(turn, passages) {
    const found = passages === 1 ? "1 passage found" : `${passages} passages found`;
    turn.status.replaceChildren(
      element("li", "stream-status__step stream-status__step--done", `Searched your books · ${found}`),
      element("li", "stream-status__step stream-status__step--active", "Writing the answer…"),
    );
  }

  function sourceId(turn, n) {
    return `turn-${turn.section.dataset.turn}-source-${n}`;
  }

  function addSource(turn, source) {
    const id = sourceId(turn, source.n);
    if (document.getElementById(id)) return;
    const details = element("details", "source");
    details.id = id;
    const summary = element("summary");
    const label = element("span");
    label.append(element("strong", "", `${source.n} · ${source.title}`));
    const place = [source.chapter, source.section].filter(Boolean).join(", ");
    if (place) label.append(`, ${place}`);
    summary.append(label);
    details.append(summary, element("span", "source__excerpt", `“${source.text}”`));
    turn.sources.append(details);
    turn.sources.hidden = false;
  }

  function addPart(turn, part) {
    turn.parts.push(part);
    let paragraph;
    if (part.kind === "book") {
      // Book claims run on in one paragraph, as in the gallery.
      if (!turn.bookParagraph) {
        turn.bookParagraph = element("p");
        turn.answer.append(turn.bookParagraph);
      } else {
        turn.bookParagraph.append(" ");
      }
      paragraph = turn.bookParagraph;
      paragraph.append(part.text);
    } else {
      paragraph = element("p", "answer-part");
      const label = element("span", "answer-part__label", LABELS[part.kind]);
      if (part.kind === "synthesis") label.classList.add("answer-part__label--synthesis");
      paragraph.append(label, part.text);
      turn.answer.append(paragraph);
    }
    for (const n of part.citations) {
      const sup = element("sup");
      const link = element("a", "cite", String(n));
      link.href = `#${sourceId(turn, n)}`;
      sup.append(link);
      paragraph.append(sup);
    }
    for (const source of part.sources) addSource(turn, source);
  }

  function finishTurn(turn) {
    turn.status.remove();
    const diagnostics = element("details", "diagnostics");
    diagnostics.append(element("summary", "", "How this answer was found"));
    turn.sources.append(diagnostics);
    turn.sources.hidden = false;
    turn.section.answered = {
      question: turn.question,
      answer: turn.parts.map((p) => p.text).join(" "),
    };
  }

  function failTurn(turn, message) {
    turn.status.remove();
    const notice = element("div", "notice turn-error");
    notice.setAttribute("role", "alert");
    notice.append(element("span", "notice__text", `The model didn't answer: ${message}`));
    const retry = element("button", "button-quiet", "Try again");
    retry.type = "button";
    retry.addEventListener("click", () => {
      if (streaming || bookIds() === null) return;
      ask(turn.question, turn.section);
    });
    notice.append(retry);
    turn.section.append(notice);
  }

  // The stream.

  function parseEvent(block) {
    let name = "message";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) name = line.slice(7);
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    return { name, data: data ? JSON.parse(data) : {} };
  }

  function handle(turn, event) {
    switch (event.name) {
      case "status":
        if (event.data.step === "writing") showWriting(turn, event.data.passages);
        return false;
      case "part":
        addPart(turn, event.data);
        return false;
      case "done":
        finishTurn(turn);
        return true;
      case "error":
        failTurn(turn, event.data.message);
        return true;
      default:
        return false;
    }
  }

  async function readStream(turn, response, signal) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (signal.aborted) return;
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      let end;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        if (block.trim() && handle(turn, parseEvent(block))) return;
      }
      if (done) break;
    }
    failTurn(turn, "the answer stopped before it was complete.");
  }

  // The answered turns before `section`: the conversation that its question follows.
  function turnsBefore(section) {
    const earlier = [];
    for (const node of conversation.children) {
      if (node === section) break;
      if (node.answered) earlier.push(node.answered);
    }
    return earlier;
  }

  // Ask `question` in a new turn at the bottom, or in place of the turn `replacing`.
  async function ask(question, replacing = null) {
    const ids = bookIds();
    if (ids === null) return;
    showConversation(true);
    const turn = newTurn(question);
    if (replacing) {
      replacing.replaceWith(turn.section);
    } else {
      conversation.append(turn.section);
    }
    const controller = new AbortController();
    streaming = controller;
    updateAsk();
    turn.section.scrollIntoView({ block: "start" });
    const body = { question, turns: turnsBefore(turn.section), model: modelSelect.value };
    if (ids.length) body.book_ids = ids;
    try {
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) {
        const refused = await response.json().catch(() => ({}));
        failTurn(turn, refused.error || `the server answered ${response.status}.`);
      } else {
        await readStream(turn, response, controller.signal);
      }
    } catch (error) {
      if (!controller.signal.aborted) failTurn(turn, error.message);
    } finally {
      if (streaming === controller) {
        streaming = null;
        updateAsk();
        if (document.activeElement === document.body) input.focus();
      }
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question || streaming) return;
    openPicker(false);
    input.value = "";
    ask(question);
  });

  head.querySelector("[data-new-conversation]").addEventListener("click", () => {
    if (streaming) streaming.abort();
    streaming = null;
    conversation.replaceChildren();
    showConversation(false);
    updateAsk();
    input.focus();
  });

  syncPicker();
})();
