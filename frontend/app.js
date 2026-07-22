/* Finance Agent Chat — consumes the SSE stream from POST /api/chat.
   Event types: session, token, tool_call, tool_result, done, error. */

const scrollEl = document.getElementById("scroll");
const threadEl = document.getElementById("thread");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const chipsEl = document.getElementById("chips");
const newBtn = document.getElementById("new-conversation");

let sessionId = null;
let busy = false;

const TOOL_LABELS = {
  get_quote: (a) => `Looking up ${a.ticker || ""} quote`.trim(),
  get_price_history: (a) => `Fetching ${a.ticker || ""} price history`.trim(),
  get_fundamentals: (a) => `Reading ${a.ticker || ""} fundamentals`.trim(),
  get_earnings: (a) => `Reading ${a.ticker || ""} earnings`.trim(),
  get_volatility: (a) => `Computing ${a.ticker || ""} volatility`.trim(),
  compare_stocks: (a) => `Comparing ${a.tickers || "stocks"}`,
  compute_portfolio: () => "Analyzing portfolio",
  plot_price_history: (a) => `Charting ${a.ticker || ""} price history`.trim(),
  plot_portfolio_allocation: () => "Charting portfolio allocation",
  add_account: (a) => `Creating account ${a.name || ""}`.trim(),
  log_expense: () => "Logging transaction",
  get_net_worth: () => "Computing net worth",
  get_spending_by_category: () => "Summing spending by category",
  web_search: (a) => `Searching: ${a.query || ""}`.trim(),
  calculate: (a) => `Calculating ${a.expression || ""}`.trim(),
  read_file: (a) => `Reading ${a.filename || "file"}`,
  write_file: (a) => `Writing ${a.filename || "file"}`,
  list_files: () => "Listing files",
  take_notes: () => "Saving a note",
  read_notes: () => "Reading notes",
  current_time: () => "Checking the time",
  execute_python: () => "Running Python",
};

function toolLabel(name, args) {
  const fn = TOOL_LABELS[name];
  return fn ? fn(args || {}) : name;
}

function scrollDown() {
  requestAnimationFrame(() => {
    scrollEl.scrollTop = scrollEl.scrollHeight;
  });
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/* ---------- markdown-lite rendering (bold, lists, code, paragraphs) ---------- */

function inlineRich(target, text) {
  const parts = String(text).split(/(\*\*.+?\*\*|`[^`]+`)/g);
  for (const p of parts) {
    if (!p) continue;
    if (p.startsWith("**") && p.endsWith("**"))
      target.appendChild(el("strong", null, p.slice(2, -2)));
    else if (p.startsWith("`") && p.endsWith("`"))
      target.appendChild(el("code", null, p.slice(1, -1)));
    else target.appendChild(document.createTextNode(p));
  }
}

function renderText(container, text, streaming) {
  container.textContent = "";
  const chunks = String(text)
    .split(/\n{2,}/)
    .filter((c) => c.trim().length);
  for (const chunk of chunks) {
    const lines = chunk.split("\n");
    if (/^\s*-{3,}\s*$/.test(chunk)) {
      container.appendChild(el("hr", "md-hr"));
    } else if (lines.length === 1 && /^#{1,6}\s/.test(chunk.trim())) {
      const h = el("div", "md-heading");
      inlineRich(h, chunk.trim().replace(/^#{1,6}\s*/, ""));
      container.appendChild(h);
    } else if (lines.every((l) => /^\s*(\d+\.|[-*])\s/.test(l) || !l.trim())) {
      const ordered = /^\s*\d+\./.test(lines[0]);
      const list = el(ordered ? "ol" : "ul");
      for (const l of lines) {
        if (!l.trim()) continue;
        const li = el("li");
        inlineRich(li, l.replace(/^\s*(\d+\.|[-*])\s*/, ""));
        list.appendChild(li);
      }
      container.appendChild(list);
    } else if (
      lines.length >= 2 &&
      lines.every((l) => /^\s*\|.*\|\s*$/.test(l) || !l.trim())
    ) {
      // markdown table
      const rows = lines
        .filter((l) => l.trim() && !/^\s*\|[\s\-:|]+\|\s*$/.test(l))
        .map((l) =>
          l
            .trim()
            .replace(/^\||\|$/g, "")
            .split("|")
            .map((c) => c.trim()),
        );
      const table = el("table", "md-table");
      rows.forEach((cells, i) => {
        const tr = el("tr");
        for (const cell of cells) {
          const td = el(i === 0 ? "th" : "td");
          inlineRich(td, cell);
          tr.appendChild(td);
        }
        table.appendChild(tr);
      });
      const wrap = el("div", "table-wrap");
      wrap.appendChild(table);
      container.appendChild(wrap);
    } else if (/^ {4}|\t/.test(lines[0]) || /  +\S+  +/.test(chunk)) {
      // fixed-width block (e.g. compare_stocks table)
      const pre = el("pre");
      pre.appendChild(el("code", null, chunk));
      container.appendChild(pre);
    } else {
      const p = el("p");
      inlineRich(p, chunk);
      container.appendChild(p);
    }
  }
  if (streaming) {
    const last = container.lastElementChild || container.appendChild(el("p"));
    last.appendChild(el("span", "cursor"));
  }
}

/* ---------- message / block construction ---------- */

function addUserMessage(text) {
  threadEl.appendChild(el("div", "msg-user", text));
  scrollDown();
}

function newAssistantMessage() {
  const msg = el("div", "msg-assistant");
  const head = el("div", "agent-head");
  head.appendChild(el("div", "agent-avatar", "V"));
  head.appendChild(el("span", "agent-label", "Finance agent"));
  msg.appendChild(head);
  const blocks = el("div", "blocks");
  msg.appendChild(blocks);
  threadEl.appendChild(msg);
  scrollDown();
  return blocks;
}

function addTyping() {
  const t = el("div", "typing");
  t.id = "typing";
  t.appendChild(el("div", "agent-avatar", "V"));
  const dots = el("div", "typing-dots");
  for (let i = 0; i < 3; i++) dots.appendChild(el("span"));
  t.appendChild(dots);
  threadEl.appendChild(t);
  scrollDown();
}

function removeTyping() {
  document.getElementById("typing")?.remove();
}

const CHECK_SVG =
  '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex:none"><path d="M20 6L9 17l-5-5"></path></svg>';
const SPIN_SVG =
  '<svg class="spin" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-gold-on-light)" stroke-width="2.5" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.2-8.56"></path></svg>';
const CHEV_SVG =
  '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"></path></svg>';

class Turn {
  constructor() {
    this.blocks = null; // created lazily on first block
    this.textBlock = null; // current streaming text block
    this.textContent = "";
    this.toolsBlock = null; // current tools block {root, list, header, items}
  }

  ensureBlocks() {
    if (!this.blocks) this.blocks = newAssistantMessage();
    return this.blocks;
  }

  appendToken(text) {
    removeTyping();
    if (!this.textBlock) {
      this.textBlock = el("div", "block-text");
      this.ensureBlocks().appendChild(this.textBlock);
      this.textContent = "";
      this.toolsBlock = null;
    }
    this.textContent += text;
    renderText(this.textBlock, this.textContent, true);
    scrollDown();
  }

  finishText() {
    if (this.textBlock) {
      renderText(this.textBlock, this.textContent, false);
      this.textBlock = null;
      this.textContent = "";
    }
  }

  toolCall(ev) {
    removeTyping();
    this.finishText();
    if (!this.toolsBlock) {
      const root = el("div", "block-tools");
      const header = el("button", "tools-header open");
      header.style.display = "none";
      const list = el("div", "tools-list");
      root.appendChild(header);
      root.appendChild(list);
      this.ensureBlocks().appendChild(root);
      const tb = { root, header, list, items: new Map(), collapsed: false };
      header.addEventListener("click", () => {
        tb.collapsed = !tb.collapsed;
        list.style.display = tb.collapsed ? "none" : "";
        header.classList.toggle("open", !tb.collapsed);
      });
      this.toolsBlock = tb;
    }
    const item = el("div", "tool-item");
    const icon = el("span");
    icon.innerHTML = SPIN_SVG;
    item.appendChild(icon);
    item.appendChild(el("span", null, toolLabel(ev.name, ev.args)));
    this.toolsBlock.list.appendChild(item);
    this.toolsBlock.items.set(ev.id, { item, icon });
    scrollDown();
  }

  toolResult(ev) {
    const tb = this.toolsBlock;
    const entry = tb?.items.get(ev.id);
    if (entry) {
      entry.icon.innerHTML = CHECK_SVG;
      const snippet = (ev.result || "").split("\n")[0].slice(0, 64);
      if (snippet && !ev.image_base64) {
        entry.item.appendChild(el("span", "result", "· " + snippet));
      }
      const allDone = tb.list.querySelectorAll(".spin").length === 0;
      if (allDone && tb.items.size > 1) {
        tb.header.style.display = "";
        tb.header.innerHTML =
          CHEV_SVG + `<span>${tb.items.size} tool calls</span>`;
        tb.header.classList.toggle("open", !tb.collapsed);
      }
    }
    if (ev.image_base64) {
      const fig = el("figure", "block-chart");
      fig.appendChild(
        el(
          "div",
          "kicker",
          toolLabel(ev.name, {}).replace(/^Charting\s*/i, "") || "Chart",
        ),
      );
      const img = document.createElement("img");
      img.src = "data:image/png;base64," + ev.image_base64;
      img.alt = ev.result || "Chart";
      fig.appendChild(img);
      const cap = el("figcaption", null, ev.result || "");
      fig.appendChild(cap);
      this.ensureBlocks().appendChild(fig);
      this.toolsBlock = null;
      this.textBlock = null;
    }
    scrollDown();
  }

  error(message) {
    removeTyping();
    this.finishText();
    const err = el("div", "block-error", message);
    this.ensureBlocks().appendChild(err);
    scrollDown();
  }

  done() {
    removeTyping();
    this.finishText();
  }
}

/* ---------- SSE over fetch ---------- */

async function streamChat(message) {
  const turn = new Turn();
  addTyping();
  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed (${resp.status})`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line; servers may use \n or \r\n
      let match;
      while ((match = /\r?\n\r?\n/.exec(buffer)) !== null) {
        const raw = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        let eventType = "message";
        let data = "";
        for (const line of raw.split(/\r?\n/)) {
          if (line.startsWith(":")) continue; // ping/comment
          if (line.startsWith("event:")) eventType = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;
        handleEvent(turn, eventType, JSON.parse(data));
      }
    }
    turn.done();
  } catch (e) {
    turn.error(e.message || "Something went wrong.");
  }
}

function handleEvent(turn, type, ev) {
  switch (type) {
    case "session":
      sessionId = ev.session_id;
      break;
    case "token":
      turn.appendToken(ev.text);
      break;
    case "tool_call":
      turn.toolCall(ev);
      break;
    case "tool_result":
      turn.toolResult(ev);
      break;
    case "done":
      turn.done();
      break;
    case "error":
      turn.error(ev.message);
      break;
  }
}

/* ---------- composer ---------- */

function setBusy(b) {
  busy = b;
  sendBtn.disabled = b || !inputEl.value.trim();
}

async function send(text) {
  const message = (text ?? inputEl.value).trim();
  if (!message || busy) return;
  chipsEl.style.display = "none";
  inputEl.value = "";
  inputEl.style.height = "auto";
  addUserMessage(message);
  setBusy(true);
  await streamChat(message);
  setBusy(false);
  inputEl.focus();
}

inputEl.addEventListener("input", () => {
  sendBtn.disabled = busy || !inputEl.value.trim();
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + "px";
});
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});
sendBtn.addEventListener("click", () => send());
chipsEl.addEventListener("click", (e) => {
  if (e.target.classList.contains("chip")) send(e.target.textContent);
});

newBtn.addEventListener("click", () => {
  if (sessionId)
    fetch("/api/sessions/" + sessionId, { method: "DELETE" }).catch(() => {});
  sessionId = null;
  busy = false;
  threadEl.textContent = "";
  chipsEl.style.display = "";
  greet();
  inputEl.focus();
});

function greet() {
  const blocks = newAssistantMessage();
  const text = el("div", "block-text");
  renderText(
    text,
    "Good afternoon. I can check prices, review how your portfolio is performing, or compare investments side by side. What would you like to look at?",
    false,
  );
  blocks.appendChild(text);
}

greet();
inputEl.focus();
