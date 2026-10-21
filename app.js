
const $ = id => document.getElementById(id);

let all = [];

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

  if (Array.isArray(v)) {
    return v.length ? v.map(item => textOr(item, "")).filter(Boolean).join(" · ") : fallback;
  }

  if (typeof v === "object") {
    return Object.entries(v)
      .map(([key, value]) => `${key}: ${textOr(value, "")}`)
      .filter(Boolean)
      .join("\n");
  }

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
  }
}

function render(r) {
  const p = r.page || {};
  const ai = r.ai_analysis || {};

  all = Array.isArray(r.findings) ? r.findings : [];

  $("page-url").textContent =
    p.final_url || p.requested_url || "Неизвестен URL";

  $("page-url").href =
    p.final_url || p.requested_url || "#";

  $("report-date").textContent = r.generated_at
    ? new Date(r.generated_at).toLocaleString("bg-BG")
    : "";

  const count = severity => all.filter(
    x => String(x.severity || "").toLowerCase() === severity
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
          (sum, resource) => sum + (resource.transferSize || 0),
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

  renderContext(ai, p, r);

  const categories = [
    ...new Set(all.map(x => x.category).filter(Boolean))
  ].sort();

  $("category-filter").innerHTML =
    '<option value="">Всички категории</option>' +
    categories.map(category =>
      `<option value="${esc(category)}">${esc(category)}</option>`
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
}

function renderContext(ai, p, r) {
  const context = ai.context ||
    ai.page_context ||
    r.context_analysis ||
    {};

  $("page-purpose").textContent = textOr(
    context.page_purpose ||
    context.purpose ||
    ai.page_purpose
  );

  const imageText = context.image_text ||
    context.image_text_analysis ||
    ai.image_text ||
    ai.image_text_analysis;

  $("image-text-analysis").textContent = formatImageText(imageText);

  $("ai-summary").textContent = textOr(
    ai.summary ||
    ai.overview ||
    context.summary
  );
}

function formatImageText(value) {
  if (!Array.isArray(value)) {
    return textOr(value);
  }

  if (!value.length) {
    return "Няма данни.";
  }

  return value.map(item => {
    if (!item || typeof item !== "object") {
      return textOr(item, "");
    }

    return [
      item.text ? "Текст: " + item.text : "",
      item.description ? "Описание: " + item.description : "",
      item.confidence != null ? "Увереност: " + item.confidence : ""
    ].filter(Boolean).join("\n");
  }).filter(Boolean).join("\n\n");
}

function renderCategories() {
  const groups = {};

  all.forEach(item => {
    const category = item.category || "Друга";
    groups[category] = (groups[category] || 0) + 1;
  });

  const entries = Object.entries(groups)
    .sort((a, b) => b[1] - a[1]);

  const max = Math.max(1, ...entries.map(item => item[1]));

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
            style="color:${colors[i % colors.length]};background:${colors[i % colors.length]}18">
            ${icons[name] || "•"}
          </span>
          <span>${esc(name)}</span>
          <span class="cat-count">${count}</span>
          <div class="cat-track">
            <div class="cat-fill"
              style="width:${count / max * 100}%;background:${colors[i % colors.length]}">
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

function findingCard(item) {
  const severity = String(item.severity || "low").toLowerCase();

  return `
    <button class="finding card" data-id="${esc(item.id)}">
      <div class="finding-top">
        <span class="severity severity-${esc(severity)}">
          ${esc(nice(severity))}
        </span>
        <span class="finding-id">${esc(item.id || "")}</span>
        <span class="category-tag">${esc(item.category || "Друга")}</span>
      </div>

      <span class="finding-title">
        ${esc(item.title || "Без заглавие")}
      </span>

      <span class="finding-evidence">
        ${esc(item.evidence || "Няма записани доказателства.")}
      </span>

      <div class="finding-bottom">
        <span>${esc(item.context || "Контекстът не е заснет")}</span>
        <span class="view-detail">Детайли ↗</span>
      </div>
    </button>
  `;
}

function filter() {
  const query = $("search").value.trim().toLowerCase();
  const category = $("category-filter").value;
  const severity = $("severity-filter").value;

  const items = all.filter(item => {
    const searchable = [
      item.id,
      item.title,
      item.category,
      item.evidence,
      item.context,
      item.impact,
      item.recommendation,
      item.source
    ].map(value => textOr(value, "")).join(" ").toLowerCase();

    return (
      (!query || searchable.includes(query)) &&
      (!category || item.category === category) &&
      (!severity || String(item.severity || "").toLowerCase() === severity)
    );
  });

  $("visible-count").textContent = items.length;

  $("findings").innerHTML = items.length
    ? items.map(findingCard).join("")
    : '<div class="empty card">Няма констатации, отговарящи на филтрите.</div>';

  bindFindingButtons($("findings"));
}

function bindFindingButtons(root) {
  root.querySelectorAll(".finding").forEach(button => {
    button.onclick = () => {
      detail(all.find(item => item.id === button.dataset.id));
    };
  });
}

function detail(item) {
  if (!item) return;

  $("detail-category").textContent =
    (item.category || "Констатация") + " · " + (item.id || "");

  $("detail-title").textContent =
    item.title || "Без заглавие";

  const severity = String(item.severity || "low").toLowerCase();

  $("detail-severity").innerHTML = `
    <span class="sev sev-${esc(severity)}">
      ${esc(nice(severity))} приоритет
    </span>
  `;

  $("detail-evidence").textContent =
    item.evidence || "Няма записани доказателства.";

  $("detail-context").textContent =
    item.context || "Няма записан контекст.";

  $("detail-impact").textContent =
    item.impact || "Въздействието не е оценено.";

  const recommendation = $("detail-recommendation");

  if (recommendation) {
    recommendation.textContent =
      item.recommendation || "Няма конкретна препоръка за тази констатация.";

    const section = recommendation.closest("section");

    if (section) {
      section.hidden = !item.recommendation;
    }
  }

  $("detail-confidence").textContent =
    "Увереност: " + nice(item.confidence);

  $("detail-source").textContent =
    "Източник: " + (item.source || "rules");

  $("detail-id").textContent = item.id || "";

  $("detail-dialog").showModal();
}

["search", "category-filter", "severity-filter"].forEach(id => {
  $(id).addEventListener(
    id === "search" ? "input" : "change",
    filter
  );
});

$("close-dialog").onclick = () => $("detail-dialog").close();

$("detail-dialog").addEventListener("click", event => {
  if (event.target === $("detail-dialog")) {
    $("detail-dialog").close();
  }
});

$("audit-form").addEventListener("submit", event => {
  event.preventDefault();

  let url;

  try {
    url = new URL($("audit-url").value.trim());
  } catch {
    $("form-message").textContent = "Въведи валиден URL.";
    return;
  }

  if (
    url.protocol !== "https:" ||
    url.hostname.toLowerCase() !== "www.yettel.bg" ||
    url.username ||
    url.password
  ) {
    $("form-message").textContent =
      "Разрешени са само HTTPS адреси от точно www.yettel.bg.";
    return;
  }

  $("form-message").textContent =
    "URL е валидиран: " + url.href +
    ". GitHub Pages не може да стартира workflow директно. " +
    "Отвори Actions → Audit public page → Run workflow и постави адреса.";

  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(url.href).catch(() => {});
  }
});

load();
