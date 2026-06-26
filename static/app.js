const topSummary = document.getElementById("topSummary");
const lastUpdated = document.getElementById("lastUpdated");
const cacheStatus = document.getElementById("cacheStatus");
const modelBadge = document.getElementById("modelBadge");
const aiStatus = document.getElementById("aiStatus");
const feedCount = document.getElementById("feedCount");
const activeCount = document.getElementById("activeCount");
const itemCount = document.getElementById("itemCount");
const searchStatus = document.getElementById("searchStatus");
const failedSources = document.getElementById("failedSources");
const trendCards = document.getElementById("trendCards");
const storyCards = document.getElementById("storyCards");
const categoryFilters = document.getElementById("categoryFilters");
const trendTemplate = document.getElementById("trendTemplate");
const storyTemplate = document.getElementById("storyTemplate");
const refreshBtn = document.getElementById("refreshBtn");
const impactToggle = document.getElementById("impactToggle");

let briefingData = null;
let activeCategory = "All";
let highImpactOnly = false;

function formatDate(isoString) {
  const dt = new Date(isoString);
  if (Number.isNaN(dt.getTime())) {
    return isoString || "Unknown date";
  }
  return dt.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function clearNode(node) {
  node.replaceChildren();
}

function setPriorityClass(node, priority) {
  node.textContent = priority || "Medium";
  node.dataset.priority = (priority || "Medium").toLowerCase();
}

function aiStatusLabel(health) {
  if (health.ai_status === "ok") {
    return health.ai_mode === "feeds_only" ? "AI organized (feeds)" : "AI organized";
  }
  if (health.api_key_configured === false) {
    return "Key missing";
  }
  const error = (health.gemini_error || "").toLowerCase();
  if (error.includes("429") || error.includes("quota") || error.includes("too_many_requests")) {
    return "Quota limit";
  }
  return "Fallback";
}

function renderHealth(data) {
  const health = data.source_health || {};
  modelBadge.textContent = data.model || "Gemini";
  aiStatus.textContent = aiStatusLabel(health);
  aiStatus.dataset.status = health.ai_status || "fallback";
  feedCount.textContent = health.configured_sources ?? "--";
  activeCount.textContent = health.active_sources ?? "--";
  itemCount.textContent = health.feed_items ?? "--";
  searchStatus.textContent = health.search_status || "--";

  const failed = health.failed_sources || [];
  const geminiError = health.gemini_error || "";
  const notes = [];
  if (geminiError) {
    notes.push(`Gemini: ${geminiError}`);
  }
  if (failed.length) {
    notes.push(`Unavailable feeds: ${failed.join(", ")}`);
  }
  failedSources.textContent = notes.length
    ? notes.join(" | ")
    : "All reachable feeds responded in this refresh.";

  const cache = data.cache || {};
  cacheStatus.textContent =
    cache.status === "hit"
      ? `Cached ${cache.age_seconds}s ago`
      : `Fresh refresh, ${cache.ttl_seconds}s cache`;
}

function renderFilters(categories) {
  const currentCategories = ["All", ...(categories || [])];
  clearNode(categoryFilters);

  for (const category of currentCategories) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "filter-btn";
    button.textContent = category;
    button.dataset.active = category === activeCategory ? "true" : "false";
    button.addEventListener("click", () => {
      activeCategory = category;
      renderFilters(briefingData.categories);
      renderStories(briefingData.story_cards || []);
    });
    categoryFilters.appendChild(button);
  }
}

function renderTrends(items) {
  clearNode(trendCards);
  for (const item of items || []) {
    const node = trendTemplate.content.firstElementChild.cloneNode(true);
    node.querySelector(".category-chip").textContent = item.category || "Trend";
    setPriorityClass(node.querySelector(".priority-pill"), item.priority);
    node.querySelector("h3").textContent = item.title;
    node.querySelector("p").textContent = item.summary;
    node.querySelector(".signal").textContent = `${item.signal_count || 1} signals`;
    trendCards.appendChild(node);
  }
}

function storyIsVisible(item) {
  const categoryMatch = activeCategory === "All" || item.category === activeCategory;
  const priorityMatch = !highImpactOnly || item.priority === "High";
  return categoryMatch && priorityMatch;
}

function renderStories(items) {
  clearNode(storyCards);
  const visibleItems = (items || []).filter(storyIsVisible);

  if (!visibleItems.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No briefing cards match the current filters.";
    storyCards.appendChild(empty);
    return;
  }

  for (const item of visibleItems) {
    const node = storyTemplate.content.firstElementChild.cloneNode(true);
    const title = node.querySelector(".story-title");
    const meta = node.querySelector(".story-meta");
    const summary = node.querySelector(".story-summary");
    const why = node.querySelector(".matter-block p");
    const affected = node.querySelector(".affected-row");
    const citations = node.querySelector(".citation-row");

    node.querySelector(".category-chip").textContent = item.category || "AI";
    setPriorityClass(node.querySelector(".priority-pill"), item.priority);

    title.textContent = item.title;
    title.href = item.url || "#";
    meta.textContent = `${item.source || "Unknown source"} | ${formatDate(item.published_at)} | ${item.confidence || "Medium"} confidence`;
    summary.textContent = item.summary || "No summary available.";
    why.textContent = item.why_it_matters || "No impact note available.";

    for (const group of item.affected_groups || []) {
      const chip = document.createElement("span");
      chip.textContent = group;
      affected.appendChild(chip);
    }

    for (const citation of item.citations || []) {
      const link = document.createElement("a");
      link.href = citation.url || item.url || "#";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = citation.title || "Source";
      citations.appendChild(link);
    }

    storyCards.appendChild(node);
  }
}

function renderBriefing(data) {
  briefingData = data;
  topSummary.textContent = data.top_summary || "No briefing summary available.";
  lastUpdated.textContent = `Generated: ${formatDate(data.generated_at)}`;
  renderHealth(data);
  renderFilters(data.categories || []);
  renderTrends(data.trend_cards || []);
  renderStories(data.story_cards || []);
}

async function loadBriefing(force = false) {
  refreshBtn.disabled = true;
  refreshBtn.textContent = force ? "Forcing refresh..." : "Refreshing...";

  try {
    const response = await fetch(`/api/briefing${force ? "?force=1" : ""}`);
    if (!response.ok) {
      throw new Error(`API error ${response.status}`);
    }
    renderBriefing(await response.json());
  } catch (err) {
    topSummary.textContent = "Unable to load briefing right now.";
    failedSources.textContent = String(err);
    clearNode(trendCards);
    clearNode(storyCards);
    cacheStatus.textContent = "Refresh failed";
  } finally {
    refreshBtn.disabled = false;
    refreshBtn.textContent = "Refresh Briefing";
  }
}

impactToggle.addEventListener("click", () => {
  highImpactOnly = !highImpactOnly;
  impactToggle.setAttribute("aria-pressed", String(highImpactOnly));
  impactToggle.dataset.active = String(highImpactOnly);
  if (briefingData) {
    renderStories(briefingData.story_cards || []);
  }
});

refreshBtn.addEventListener("click", () => loadBriefing(true));
loadBriefing(false);
