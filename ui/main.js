const PROMPTS = [
  "What is the minimum attendance for semester exams?",
  "Can I get medical leave for a missed mid-sem?",
  "Last date for B.Tech admission this year?",
  "Am I eligible for campus placement? My ID is S1-001",
  "Am I eligible for campus placement? My ID is S1-004",
  "What is my attendance? Student ID S1-001",
];

const API_URL = import.meta.env.VITE_API_URL || "/chat";
const STUDENT_ID_KEY = "campusassist_student_id";
const STUDENT_ID_RE = /\b(S1-\d{3})\b/i;

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

function getRememberedStudentId() {
  return sessionStorage.getItem(STUDENT_ID_KEY) || "";
}

function setRememberedStudentId(id) {
  if (!id) return;
  sessionStorage.setItem(STUDENT_ID_KEY, id.toUpperCase());
  renderStudentHint();
}

function clearRememberedStudentId() {
  sessionStorage.removeItem(STUDENT_ID_KEY);
  renderStudentHint();
}

function extractStudentId(text) {
  const m = String(text || "").match(STUDENT_ID_RE);
  return m ? m[1].toUpperCase() : "";
}

function needsStudentContext(text) {
  const lower = String(text || "").toLowerCase();
  return (
    lower.includes("eligible") ||
    lower.includes("my attendance") ||
    lower.includes("my result") ||
    lower.includes("my cgpa") ||
    lower.includes("student record") ||
    lower.includes("my marks")
  );
}

function withStudentId(message) {
  const found = extractStudentId(message);
  if (found) {
    setRememberedStudentId(found);
    return message;
  }
  const remembered = getRememberedStudentId();
  if (remembered && needsStudentContext(message)) {
    return `${message}\n[studentId=${remembered}]`;
  }
  return message;
}

function renderStudentHint() {
  let hint = document.getElementById("student-id-hint");
  if (!hint) {
    hint = document.createElement("div");
    hint.id = "student-id-hint";
    hint.className = "student-id-hint";
    formEl.insertAdjacentElement("beforebegin", hint);
  }
  const id = getRememberedStudentId();
  if (!id) {
    hint.hidden = true;
    hint.innerHTML = "";
    return;
  }
  hint.hidden = false;
  hint.innerHTML = "";
  const span = document.createElement("span");
  span.textContent = `Using student ID ${id}`;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "linkish";
  btn.textContent = "Clear";
  btn.addEventListener("click", clearRememberedStudentId);
  hint.appendChild(span);
  hint.appendChild(document.createTextNode(" · "));
  hint.appendChild(btn);
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
  const t = line.trim();
  // Accept |---|---|, | --- | --- |, :---:|:---:, and rows without leading/trailing pipe.
  return /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$/.test(t);
}

function looksLikeTableRow(line) {
  const t = line.trim();
  if (!t.includes("|")) return false;
  if (isTableSeparatorRow(t)) return false;
  // At least two cells: "a | b" or "| a | b |"
  return (t.match(/\|/g) || []).length >= 1 && /\|/.test(t.slice(1));
}

function parseTableRow(line) {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((cell) => cell.trim());
}

function renderMarkdown(raw) {
  // Normalize odd model output: lone CR, and packed "| --- |" separators.
  const lines = escapeHtml(raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n")).split("\n");
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

    if (
      looksLikeTableRow(trimmed) &&
      i + 1 < lines.length &&
      isTableSeparatorRow(lines[i + 1])
    ) {
      const headerCells = parseTableRow(trimmed);
      i += 2;
      const bodyRows = [];
      while (i < lines.length && looksLikeTableRow(lines[i])) {
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
      !(
        looksLikeTableRow(lines[i]) &&
        i + 1 < lines.length &&
        isTableSeparatorRow(lines[i + 1])
      )
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
      const cite = document.createElement("details");
      cite.className = "citation";
      const summary = document.createElement("summary");
      summary.textContent = c.title || "Source";
      const snippet = document.createElement("div");
      snippet.className = "citation-snippet";
      snippet.textContent = c.snippet || "";
      cite.appendChild(summary);
      cite.appendChild(snippet);
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
    check_student_record: "Checked student record",
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
  const display = (text ?? inputEl.value).trim();
  if (!display) return;

  const message = withStudentId(display);
  inputEl.value = "";
  addBubble("user", display);
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
renderStudentHint();
addBubble(
  "system",
  "Ask a campus question or tap a suggested prompt. Demo student IDs: S1-001 … S1-006."
);
