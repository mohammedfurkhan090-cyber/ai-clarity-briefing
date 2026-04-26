// DOM Elements
const headlineBullets = document.getElementById("headlineBullets");
const themeBullets = document.getElementById("themeBullets");
const sourceBullets = document.getElementById("sourceBullets");
const feedHealth = document.getElementById("feedHealth");
const updatesList = document.getElementById("updatesList");
const updateTemplate = document.getElementById("updateTemplate");
const themeChipTemplate = document.getElementById("themeChipTemplate");
const refreshBtn = document.getElementById("refreshBtn");
const lastUpdated = document.getElementById("lastUpdated");
const searchInput = document.getElementById("searchInput");
const clearFiltersBtn = document.getElementById("clearFilters");
const sortBtn = document.getElementById("sortBtn");
const sortMenu = document.getElementById("sortMenu");
const filterUnread = document.getElementById("filterUnread");
const filterBookmarked = document.getElementById("filterBookmarked");
const themeChips = document.getElementById("themeChips");
const emptyState = document.getElementById("emptyState");
const itemsCount = document.getElementById("itemsCount");
const toast = document.getElementById("toast");
const actionModal = document.getElementById("actionModal");
const closeModal = document.getElementById("closeModal");
const closeModalBtn = document.getElementById("closeModalBtn");
const actionTitle = document.getElementById("actionTitle");
const actionTheme = document.getElementById("actionTheme");
const actionsList = document.getElementById("actionsList");
const themeToggle = document.getElementById("themeToggle");

// Theme Initialization
function initTheme() {
  const isDarkMode = localStorage.getItem("theme") !== "light";
  applyTheme(isDarkMode);
}

function applyTheme(isDark) {
  if (isDark) {
    document.body.classList.remove("light-mode");
    localStorage.setItem("theme", "dark");
    if (themeToggle) themeToggle.textContent = "🌙";
  } else {
    document.body.classList.add("light-mode");
    localStorage.setItem("theme", "light");
    if (themeToggle) themeToggle.textContent = "☀️";
  }
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const isDarkMode = document.body.classList.contains("light-mode");
    applyTheme(isDarkMode);
    showToast(isDarkMode ? "Switched to dark mode" : "Switched to light mode");
  });
}

// State
let allUpdates = [];
let filteredUpdates = [];
let state = {
  searchQuery: "",
  selectedThemes: new Set(),
  selectedSources: new Set(),
  showUnread: false,
  showBookmarked: false,
  sortBy: "newest",
  bookmarks: new Set(JSON.parse(localStorage.getItem("bookmarks") || "[]")),
  readItems: new Set(JSON.parse(localStorage.getItem("readItems") || "[]")),
};

// Utility Functions
function showToast(message, type = "success") {
  toast.textContent = message;
  toast.className = `toast active ${type}`;
  setTimeout(() => {
    toast.classList.remove("active");
  }, 3000);
}

function formatDate(isoString) {
  const dt = new Date(isoString);
  return dt.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderBulletList(target, items) {
  target.innerHTML = "";
  if (!items || !items.length) {
    const li = document.createElement("li");
    li.textContent = "No data available right now.";
    target.appendChild(li);
    return;
  }

  for (const text of items) {
    const li = document.createElement("li");
    li.textContent = text;
    target.appendChild(li);
  }
}

function saveBookmarks() {
  localStorage.setItem("bookmarks", JSON.stringify([...state.bookmarks]));
}

function saveReadItems() {
  localStorage.setItem("readItems", JSON.stringify([...state.readItems]));
}

function toggleBookmark(id) {
  if (state.bookmarks.has(id)) {
    state.bookmarks.delete(id);
    showToast("Removed from bookmarks");
  } else {
    state.bookmarks.add(id);
    showToast("Added to bookmarks ⭐");
  }
  saveBookmarks();
  applyFilters();
}

function markAsRead(id) {
  state.readItems.add(id);
  saveReadItems();
}

// Filter & Search Logic
function applyFilters() {
  let filtered = allUpdates;

  // Search filter
  if (state.searchQuery) {
    const q = state.searchQuery.toLowerCase();
    filtered = filtered.filter(
      (item) =>
        item.title.toLowerCase().includes(q) ||
        item.summary.toLowerCase().includes(q)
    );
  }

  // Theme filter
  if (state.selectedThemes.size > 0) {
    filtered = filtered.filter((item) => state.selectedThemes.has(item.theme));
  }

  // Source filter
  if (state.selectedSources.size > 0) {
    filtered = filtered.filter((item) => state.selectedSources.has(item.source));
  }

  // Unread filter
  if (state.showUnread) {
    filtered = filtered.filter((item) => !state.readItems.has(item.id));
  }

  // Bookmarked filter
  if (state.showBookmarked) {
    filtered = filtered.filter((item) => state.bookmarks.has(item.id));
  }

  // Sort
  if (state.sortBy === "oldest") {
    filtered.sort(
      (a, b) => new Date(a.published_at) - new Date(b.published_at)
    );
  } else {
    // newest (default)
    filtered.sort(
      (a, b) => new Date(b.published_at) - new Date(a.published_at)
    );
  }

  filteredUpdates = filtered;
  renderUpdates(filtered);
  updateItemsCount();
}

function updateItemsCount() {
  const count = filteredUpdates.length;
  itemsCount.textContent = `${count} article${count !== 1 ? "s" : ""}`;
  emptyState.style.display = count === 0 ? "block" : "none";
}

// Render Functions
function renderThemeChips() {
  themeChips.innerHTML = "";
  const themes = new Map();

  allUpdates.forEach((item) => {
    themes.set(item.theme, (themes.get(item.theme) || 0) + 1);
  });

  Array.from(themes.entries())
    .sort((a, b) => b[1] - a[1])
    .forEach(([theme, count]) => {
      const chip = themeChipTemplate.content.cloneNode(true);
      const btn = chip.querySelector(".theme-chip");
      const name = chip.querySelector(".chip-name");
      const badge = chip.querySelector(".chip-count");

      btn.dataset.theme = theme;
      name.textContent = theme;
      badge.textContent = count;

      if (state.selectedThemes.has(theme)) {
        btn.classList.add("active");
      }

      btn.addEventListener("click", () => {
        if (state.selectedThemes.has(theme)) {
          state.selectedThemes.delete(theme);
        } else {
          state.selectedThemes.add(theme);
        }
        renderThemeChips();
        applyFilters();
      });

      themeChips.appendChild(chip);
    });
}

function renderUpdates(items) {
  updatesList.innerHTML = "";

  for (const item of items) {
    const node = updateTemplate.content.cloneNode(true);
    const titleLink = node.querySelector(".update-title");
    const meta = node.querySelector(".update-meta");
    const summary = node.querySelector(".update-summary");
    const themeBadge = node.querySelector(".theme-badge");
    const readMoreLink = node.querySelector(".update-link");
    const bookmarkBtn = node.querySelector(".bookmark-btn");
    const actionsBtn = node.querySelector(".actions-btn");

    titleLink.textContent = item.title;
    titleLink.href = item.link || "#";
    meta.textContent = `${item.source} • ${formatDate(item.published_at)}`;
    summary.textContent = item.summary || "No summary available.";
    themeBadge.textContent = item.theme || "General";
    readMoreLink.href = item.link || "#";

    // Mark as read when clicked
    titleLink.addEventListener("click", () => {
      markAsRead(item.id);
    });
    readMoreLink.addEventListener("click", () => {
      markAsRead(item.id);
    });

    // Bookmark button
    if (state.bookmarks.has(item.id)) {
      bookmarkBtn.classList.add("bookmarked");
      bookmarkBtn.textContent = "⭐";
    }

    bookmarkBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleBookmark(item.id);
      if (state.bookmarks.has(item.id)) {
        bookmarkBtn.classList.add("bookmarked");
      } else {
        bookmarkBtn.classList.remove("bookmarked");
      }
    });

    // Actions button
    actionsBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      showActionModal(item);
    });

    updatesList.appendChild(node);
  }
}

// Action Generation Modal
async function showActionModal(item) {
  actionTitle.textContent = item.title;
  actionTheme.textContent = `Theme: ${item.theme || "General"}`;
  actionsList.innerHTML = '<div style="text-align: center; color: var(--muted);">Loading actions...</div>';

  actionModal.style.display = "flex";

  try {
    const response = await fetch("/api/generate-actions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        theme: item.theme,
        title: item.title,
      }),
    });

    if (!response.ok) throw new Error("Failed to generate actions");

    const data = await response.json();
    actionsList.innerHTML = "";

    data.actions.forEach((action, index) => {
      const actionDiv = document.createElement("div");
      actionDiv.setAttribute("data-index", index + 1);
      const span = document.createElement("span");
      span.textContent = action;
      actionDiv.appendChild(span);
      actionsList.appendChild(actionDiv);
    });

    showToast("✨ Next steps generated!");
  } catch (err) {
    actionsList.innerHTML = '<div style="color: var(--bad);">Error loading actions. Please try again.</div>';
    showToast("Error generating actions", "error");
  }
}

// Event Listeners - Modal
closeModal.addEventListener("click", () => {
  actionModal.style.display = "none";
});

closeModalBtn.addEventListener("click", () => {
  actionModal.style.display = "none";
});

document.querySelector(".modal-overlay").addEventListener("click", () => {
  actionModal.style.display = "none";
});

// Event Listeners - Filters & Search
searchInput.addEventListener("input", (e) => {
  state.searchQuery = e.target.value;
  applyFilters();
});

clearFiltersBtn.addEventListener("click", () => {
  state.searchQuery = "";
  state.selectedThemes.clear();
  state.selectedSources.clear();
  state.showUnread = false;
  state.showBookmarked = false;
  state.sortBy = "newest";
  searchInput.value = "";
  filterUnread.classList.remove("active");
  filterBookmarked.classList.remove("active");
  sortBtn.textContent = "↕️ Sort: Newest";
  sortMenu.classList.remove("active");
  renderThemeChips();
  applyFilters();
  showToast("Filters cleared");
});

filterUnread.addEventListener("click", () => {
  state.showUnread = !state.showUnread;
  filterUnread.classList.toggle("active");
  applyFilters();
  showToast(state.showUnread ? "Showing unread only" : "Showing all articles");
});

filterBookmarked.addEventListener("click", () => {
  state.showBookmarked = !state.showBookmarked;
  filterBookmarked.classList.toggle("active");
  applyFilters();
  showToast(state.showBookmarked ? "Showing bookmarked only" : "Showing all articles");
});

// Sort Dropdown
sortBtn.addEventListener("click", () => {
  sortMenu.classList.toggle("active");
});

document.querySelectorAll(".dropdown-item").forEach((item) => {
  item.addEventListener("click", (e) => {
    const sortValue = e.target.dataset.sort;
    state.sortBy = sortValue;
    sortBtn.textContent =
      sortValue === "oldest" ? "↕️ Sort: Oldest" : "↕️ Sort: Newest";
    sortMenu.classList.remove("active");
    applyFilters();
  });
});

// Close dropdown when clicking outside
document.addEventListener("click", (e) => {
  if (!e.target.closest(".dropdown")) {
    sortMenu.classList.remove("active");
  }
});

// Refresh Button
refreshBtn.addEventListener("click", loadBriefing);

// Main Load Function
async function loadBriefing() {
  refreshBtn.disabled = true;
  refreshBtn.textContent = "Refreshing...";

  try {
    const response = await fetch("/api/briefing");
    if (!response.ok) {
      throw new Error(`API error ${response.status}`);
    }

    const data = await response.json();

    // Update digest
    renderBulletList(headlineBullets, data.digest.headline_bullets);
    renderBulletList(themeBullets, data.digest.theme_bullets);
    renderBulletList(sourceBullets, data.digest.source_bullets);

    // Update feed health
    const healthItems = data.failures.length
      ? data.failures.map((name) => `${name} is currently unreachable.`)
      : ["All feeds responded in this refresh."];
    if (data.sources?.length) {
      healthItems.push(`Configured sources: ${data.sources.length}`);
    }
    renderBulletList(feedHealth, healthItems);

    // Update articles
    allUpdates = data.updates || [];
    renderThemeChips();
    applyFilters();

    lastUpdated.textContent = `Last updated: ${formatDate(data.digest.generated_at)}`;
    showToast("✓ Briefing refreshed");
  } catch (err) {
    renderBulletList(headlineBullets, ["Unable to load briefing right now."]);
    renderBulletList(themeBullets, ["Please refresh in a few seconds."]);
    renderBulletList(sourceBullets, [String(err)]);
    renderBulletList(feedHealth, ["Some feeds may be blocked or unavailable."]);
    updatesList.innerHTML = "";
    lastUpdated.textContent = "Last updated: failed";
    showToast("Failed to load briefing", "error");
  } finally {
    refreshBtn.disabled = false;
    refreshBtn.textContent = "Refresh Briefing";
  }
}

// Initial Load
initTheme();
loadBriefing();

