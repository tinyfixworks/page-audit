const $ = id => document.getElementById(id);

let all = [];
let aiFindings = [];

const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
}[c]));

const nice = v => v ? v[0].toUpperCase() + v.slice(1) : "—";

const textOr = (v, fallback = "Няма данни.") => {
  if (v === null || v === undefined || v === "") return fallback;
  if (Array.isArray(v)) return v.length ? v.join(" · ") : fallback;
  if (typeof v === "object") return JSON.stringify(v, null, 2);
  return String(v);
};

const icons = {
  SEO: "⌕",
  Content: "✎",
  Links: "↗",
  Accessibility: "◉",
  Technical: "⌘",
  Performance: "◷",
  Images: "▧",
  Code: "‹›"
};

async function load() {
  try {
    const r = await fetch("results.json?t=" + Date.now(), {
      cache: "no-store"
    });

    if (!r.ok) {
      throw Error("Няма доклад. Стартирай workflow-а в GitHub Actions.");
    }

    render(await r.json());
  } catch (e) {
    $("findings").innerHTML = `
      <div class="empty card">
        <b>Няма зареден доклад</b>
        <p>${esc(e.message)}</p>
      </div>`;

    $("ai-findings").innerHTML = `
      <div class="empty card">
        AI констатациите ще се покажат след зареждане на доклад.
      </div>`;

    $("ai-diagnostic").textContent = e.message;
  }
}

function render(r) {
  const p = r.page || {};
  const ai = r.ai_analysis || {};

  all = Array.isArray(r.findings) ? r.findings : [];

  aiFindings = all.filter(x =>
    String(x.source || "").toLowerCase().includes("gemini") ||
    String(x.source || "").toLowerCase() === "ai" ||
    x.ai_generated === true
  );

  const declaredAiCount = Number.isFinite(ai.finding_count)
    ? ai.finding_count
    : aiFindings.length;

  $("page-url").textContent =
    p.final_url || p.requested_url || "Неизвестен URL";

  $("page-url").href =
    p.final_url || p.requested_url || "#";

  $("report-date").textContent = r.generated_at
    ? new Date(r.generated_at).toLocaleString("bg-BG")
    : "";

  const count = s => all.filter(
    x => String(x.severity || "").toLowerCase() === s
  ).length;

  $("total-count").textContent = all.length;
  $("critical-count").textContent = count("critical");
  $("high-only-count").textContent = count("high");
  $("medium-count").textContent = count("medium");
  $("low-count").textContent = count("low");
  $("ok-count").textContent = "—";

  $("load-time").textContent = p.load_ms == null
    ? "—"
    : (p.load_ms / 1000).toFixed(1) + " s";

  $("request-count").textContent = p.request_count ?? "—";

  $("resource-size").textContent = p.resources?.length
    ? (
        p.resources.reduce(
          (s, x) => s + (x.transferSize || 0),
          0
        ) / 1048576
      ).toFixed(1) + " MB"
    : "—";

  $("http-status").textContent = p.status
    ? "HTTP " + p.status
    : "HTTP неизвестен";

  $("title-value").textContent = p.title || "Не е открит";
  $("description-value").textContent =
    p.meta_description || "Не е открит";

  $("h1-value").textContent = p.h1?.length
    ? p.h1.join(" · ")
    : "Няма H1";

  $("canonical-value").textContent =
    p.canonical || "Не е открит";

  renderAI(ai, declaredAiCount);
  renderContext(ai, p, r);

  $("report-notes").textContent = ai.enabled
    ? "AI анализ: " + textOr(ai.status, "Статусът не е записан.")
    : "AI анализът не е активиран в този доклад.";

  const cats = [
    ...new Set(all.map(x => x.category).filter(Boolean))
  ].sort();

  $("category-filter").innerHTML =
    '<option value="">Всички категории</option>' +
    cats.map(x =>
      `<option value="${esc(x)}">${esc(x)}</option>`
    ).join("");

  renderCategories();
  renderChecklist(p);

  const score = Math.max(
    0,
    100 -
      count("critical") * 18 -
      count("high") * 12 -
      count("medium") * 5 -
      count("low") * 2
  );

  $("score-value").innerHTML = score + "<small>/100</small>";

  $("score-description").textContent =
    count("critical") + count("high")
      ? "Има проблеми с висок приоритет за преглед."
      : "Няма критични или високоприоритетни проблеми по текущите правила.";

  filter();
  renderAIFindings();
}

function renderAI(ai, count) {
  const status = textOr(
    ai.status,
    ai.enabled === false
      ? "Не е активиран"
      : "Няма записан статус."
  );

  const model = textOr(ai.model, "Не е записан");
  const statusLower = String(status).toLowerCase();

  const failed = /fail|error|timeout|неусп|греш/.test(statusLower);
  const completed = /completed|завърш|success/.test(statusLower);
  const usedFallback = /fallback|резерв/.test(statusLower);

  $("ai-status").textContent = status;
  $("ai-model").textContent = model;
  $("ai-finding-count").textContent = count;

  $("ai-fallback").textContent = usedFallback
    ? "Да"
    : ai.fallback_model
      ? textOr(ai.fallback_model)
      : "Не е посочено";

  const badge = $("ai-status-badge");

  badge.textContent = failed
    ? "Проблем"
    : completed
      ? "Завършен"
      : ai.enabled === false
        ? "Изключен"
        : "Няма данни";

  badge.className = "status-badge " + (
    failed
      ? "status-error"
      : completed
        ? "status-success"
        : "status-neutral"
  );

  const diagnostic = [
    ai.error,
    ai.error_message,
    ai.primary_error,
    ai.failure_reason,
    ai.diagnostic,
    ai.details
  ].filter(Boolean);

  if (!diagnostic.length && usedFallback) {
    diagnostic.push(
      "Основният модел не е завършил успешно; резервният модел е използван. " +
      "Конкретната причина не е записана в results.json."
    );
  }

  if (!diagnostic.length && failed) {
    diagnostic.push(status);
  }

  if (!diagnostic.length) {
    diagnostic.push(
      "Няма записана грешка или допълнителна диагностична информация."
    );
  }

  $("ai-diagnostic").textContent = diagnostic
    .map(x => textOr(x, ""))
    .join("\n");
}

function renderContext(ai, p, r) {
  const context = ai.context ||
    ai.page_context ||
    r.context_analysis ||
    {};

  $("page-purpose").textContent = textOr(
    context.page_purpose || context.purpose || ai.page_purpose
  );

  $("context-conflicts").textContent = textOr(
    context.conflicts ||
    context.potential_conflicts ||
    ai.conflicts ||
    ai.potential_conflicts
  );

  $("image-text-analysis").textContent = textOr(
    context.image_text ||
    context.image_text_analysis ||
    ai.image_text ||
    ai.image_text_analysis
  );

  $("ai-summary").textContent = textOr(
    ai.summary || ai.overview || context.summary
  );
}

function renderCategories() {
  const g = {};

  all.forEach(x => {
    const category = x.category || "Друга";
    g[category] = (g[category] || 0) + 1;
  });

  const entries = Object.entries(g).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(x => x[1]));

  const colors = [
    "#e65a69",
    "#ef873b",
    "#3478f6",
    "#e4ad20",
    "#8865df",
    "#20ae76"
  ];

  $("category-summary").innerHTML = entries.length
    ? entries.map(([name, count], i) => `
        <div class="category-row">
          <span class="cat-icon"
            style="color:${colors[i % 6]};background:${colors[i % 6]}18">
            ${icons[name] || "•"}
          </span>
          <span>${esc(name)}</span>
          <span class="cat-count">${count}</span>
          <div class="cat-track">
            <div class="cat-fill"
              style="width:${count / max * 100}%;background:${colors[i % 6]}">
            </div>
          </div>
        </div>
      `).join("")
    : '<p class="subtle">Няма констатации.</p>';
}

function renderChecklist(p) {
  const checks = [
    ["Метаданни", !!p.title && !!p.meta_description],
    ["Заглавия (H1–H6)", !!p.headings?.length],
    ["Линкове", !!p.links?.length],
    ["Изображения", !!p.images?.length],
    ["Ресурси", !!p.resources?.length]
  ];

  $("checklist").innerHTML = checks.map(([name, ok]) => `
    <div class="check-row">
      <span class="check-icon ${ok ? "" : "warn"}">
        ${ok ? "✓" : "!"}
      </span>
      <span>${name}</span>
      <span class="check-status ${ok ? "" : "warn"}">
        ${ok ? "OK" : "Провери"}
      </span>
    </div>
  `).join("");
}

function findingCard(x) {
  const severity = String(x.severity || "low").toLowerCase();

  return `
    <button class="finding card" data-id="${esc(x.id)}">
      <div class="finding-top">
        <span class="severity severity-${esc(severity)}">
          ${esc(nice(severity))}
        </span>
        <span class="finding-id">${esc(x.id || "")}</span>
        <span class="category-tag">${esc(x.category || "Друга")}</span>
      </div>
      <span class="finding-title">${esc(x.title || "Без заглавие")}</span>
      <span class="finding-evidence">
        ${esc(x.evidence || "Няма записани доказателства.")}
      </span>
      <div class="finding-bottom">
        <span>${esc(x.context || "Контекстът не е заснет")}</span>
        <span class="view-detail">Детайли ↗</span>
      </div>
    </button>
  `;
}

function filter() {
  const q = $("search").value.trim().toLowerCase();
  const category = $("category-filter").value;
  const severity = $("severity-filter").value;

  const items = all.filter(x =>
    (
      !q ||
      [
        x.id,
        x.title,
        x.category,
        x.evidence,
        x.context,
        x.impact
      ].join(" ").toLowerCase().includes(q)
    ) &&
    (!category || x.category === category) &&
    (!severity || x.severity === severity)
  );

  $("visible-count").textContent = items.length;

  $("findings").innerHTML = items.length
    ? items.map(findingCard).join("")
    : '<div class="empty card">Няма констатации, отговарящи на филтрите.</div>';

  bindFindingButtons($("findings"));
}

function renderAIFindings() {
  $("ai-visible-count").textContent = aiFindings.length;

  $("ai-findings").innerHTML = aiFindings.length
    ? aiFindings.map(findingCard).join("")
    : `
      <div class="empty card">
        <b>Няма отделно маркирани AI констатации.</b>
        <p>
          Това не доказва, че страницата няма проблеми. Провери статуса
          на анализа и дали findings в results.json съдържа
          source: "ai" или source: "gemini".
        </p>
      </div>
    `;

  bindFindingButtons($("ai-findings"));
}

function bindFindingButtons(root) {
  root.querySelectorAll(".finding").forEach(button => {
    button.onclick = () => {
      detail(all.find(x => x.id === button.dataset.id));
    };
  });
}

function detail(x) {
  if (!x) return;

  $("detail-category").textContent =
    (x.category || "Констатация") + " · " + (x.id || "");

  $("detail-title").textContent = x.title || "Без заглавие";

  const severity = String(x.severity || "low").toLowerCase();

  $("detail-severity").innerHTML = `
    <span class="sev sev-${esc(severity)}">
      ${esc(nice(severity))} приоритет
    </span>
  `;

  $("detail-evidence").textContent =
    x.evidence || "Няма записани доказателства.";

  $("detail-context").textContent =
    x.context || "Няма записан контекст.";

  $("detail-impact").textContent =
    x.impact || "Въздействието не е оценено.";

  $("detail-confidence").textContent =
    "Увереност: " + nice(x.confidence);

  $("detail-source").textContent =
    "Източник: " + (x.source || "rules");

  $("detail-id").textContent = x.id || "";

  $("detail-dialog").showModal();
}

["search", "category-filter", "severity-filter"].forEach(id => {
  $(id).addEventListener(
    id === "search" ? "input" : "change",
    filter
  );
});

$("close-dialog").onclick = () => $("detail-dialog").close();

$("detail-dialog").addEventListener("click", e => {
  if (e.target === $("detail-dialog")) {
    $("detail-dialog").close();
  }
});

$("audit-form").addEventListener("submit", e => {
  e.preventDefault();

  let u;

  try {
    u = new URL($("audit-url").value.trim());
  } catch {
    $("form-message").textContent = "Въведи валиден URL.";
    return;
  }

  if (
    u.protocol !== "https:" ||
    u.hostname.toLowerCase() !== "www.yettel.bg" ||
    u.username ||
    u.password
  ) {
    $("form-message").textContent =
      "Разрешени са само HTTPS адреси от точно www.yettel.bg.";
    return;
  }

  $("form-message").textContent =
    "URL е валидиран: " + u.href +
    ". GitHub Pages не може да стартира workflow директно. " +
    "Отвори Actions → Audit public page → Run workflow и постави адреса.";

  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(u.href).catch(() => {});
  }
});

load();
