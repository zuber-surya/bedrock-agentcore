const PROMPTS = [
  "What is the minimum attendance for semester exams?",
  "Can I get medical leave for a missed mid-sem?",
  "Last date for B.Tech admission this year?",
  "What documents are required for admission?",
  "Raise a support ticket for fee clarification",
];

const API_URL = import.meta.env.VITE_API_URL || "/chat";

const chipsEl = document.getElementById("chips");
const threadEl = document.getElementById("thread");
const formEl = document.getElementById("composer");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");

function getSessionId() {
  const key = "campusassist_session";
  let id = sessionStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(key, id);
  }
  return id;
}

function renderChips() {
  chipsEl.innerHTML = "";
  for (const text of PROMPTS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip";
    btn.textContent = text;
    btn.addEventListener("click", () => sendMessage(text));
    chipsEl.appendChild(btn);
  }
}

function inlineMarkdown(escapedText) {
  return escapedText.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function isTableSeparatorRow(line) {
  return /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$/.test(line.trim());
}

function parseTableRow(line) {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((cell) => cell.trim());
}

function renderMarkdown(raw) {
  const lines = escapeHtml(raw).split("\n");
  const html = [];
  let i = 0;

  while (i < lines.length) {
    const trimmed = lines[i].trim();

    if (trimmed === "") {
      i++;
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      const level = Math.min(headingMatch[1].length + 2, 6);
      html.push(`<h${level}>${inlineMarkdown(headingMatch[2])}</h${level}>`);
      i++;
      continue;
    }

    if (trimmed.startsWith("|") && i + 1 < lines.length && isTableSeparatorRow(lines[i + 1])) {
      const headerCells = parseTableRow(trimmed);
      i += 2;
      const bodyRows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        bodyRows.push(parseTableRow(lines[i]));
        i++;
      }
      const thead = `<thead><tr>${headerCells
        .map((c) => `<th>${inlineMarkdown(c)}</th>`)
        .join("")}</tr></thead>`;
      const tbody = `<tbody>${bodyRows
        .map((row) => `<tr>${row.map((c) => `<td>${inlineMarkdown(c)}</td>`).join("")}</tr>`)
        .join("")}</tbody>`;
      html.push(`<div class="table-wrap"><table>${thead}${tbody}</table></div>`);
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(`<li>${inlineMarkdown(lines[i].trim().replace(/^[-*]\s+/, ""))}</li>`);
        i++;
      }
      html.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    const paraLines = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^#{1,6}\s+/.test(lines[i].trim()) &&
      !/^[-*]\s+/.test(lines[i].trim()) &&
      !(lines[i].trim().startsWith("|") && i + 1 < lines.length && isTableSeparatorRow(lines[i + 1]))
    ) {
      paraLines.push(inlineMarkdown(lines[i].trim()));
      i++;
    }
    html.push(`<p>${paraLines.join("<br>")}</p>`);
  }

  return html.join("");
}

function addBubble(role, text, extras = {}) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  if (role === "bot") {
    div.innerHTML = renderMarkdown(text);
  } else {
    div.textContent = text;
  }

  if (role === "bot" && (extras.citations?.length || extras.toolsUsed?.length)) {
    const meta = document.createElement("div");
    meta.className = "meta";

    if (extras.toolsUsed?.length) {
      const badges = document.createElement("div");
      badges.className = "badges";
      for (const tool of extras.toolsUsed) {
        const b = document.createElement("span");
        b.className = "badge";
        b.textContent = toolLabel(tool);
        badges.appendChild(b);
      }
      meta.appendChild(badges);
    }

    for (const c of extras.citations || []) {
      const cite = document.createElement("div");
      cite.className = "citation";
      cite.innerHTML = `<strong>📄 ${escapeHtml(c.title || "Source")}</strong>${escapeHtml(
        c.snippet || ""
      )}`;
      meta.appendChild(cite);
    }

    div.appendChild(meta);
  }

  threadEl.appendChild(div);
  threadEl.scrollTop = threadEl.scrollHeight;
  return div;
}

function toolLabel(name) {
  const map = {
    get_admission_deadline: "Checked admission deadline",
    get_exam_schedule: "Checked exam schedule",
    create_ticket: "Created support ticket",
  };
  return map[name] || name;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function sendMessage(text) {
  const message = (text ?? inputEl.value).trim();
  if (!message) return;

  inputEl.value = "";
  addBubble("user", message);
  const loading = addBubble("system", "Thinking…");
  loading.classList.add("loading");
  sendBtn.disabled = true;

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, sessionId: getSessionId() }),
    });
    const data = await res.json().catch(() => ({}));
    loading.remove();
    if (!res.ok) {
      addBubble("error", data.error || `Request failed (${res.status})`);
      return;
    }
    addBubble("bot", data.reply || "(empty reply)", {
      citations: data.citations || [],
      toolsUsed: data.toolsUsed || [],
    });
  } catch (err) {
    loading.remove();
    addBubble("error", `Network error: ${err.message}`);
  } finally {
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage();
});

renderChips();
addBubble(
  "system",
  "Ask a campus question or tap a suggested prompt to begin."
);
