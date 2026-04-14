const headlineBullets = document.getElementById("headlineBullets");
const themeBullets = document.getElementById("themeBullets");
const sourceBullets = document.getElementById("sourceBullets");
const feedHealth = document.getElementById("feedHealth");
const updatesList = document.getElementById("updatesList");
const updateTemplate = document.getElementById("updateTemplate");
const refreshBtn = document.getElementById("refreshBtn");
const lastUpdated = document.getElementById("lastUpdated");

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

function renderUpdates(items) {
  updatesList.innerHTML = "";

  for (const item of items) {
    const node = updateTemplate.content.firstElementChild.cloneNode(true);
    const title = node.querySelector(".update-title");
    const meta = node.querySelector(".update-meta");
    const summary = node.querySelector(".update-summary");

    title.textContent = item.title;
    title.href = item.link || "#";
    meta.textContent = `${item.source} • ${formatDate(item.published_at)}`;
    summary.textContent = item.summary || "No summary available.";

    updatesList.appendChild(node);
  }
}

async function loadBriefing() {
  refreshBtn.disabled = true;
  refreshBtn.textContent = "Refreshing...";

  try {
    const response = await fetch("/api/briefing");
    if (!response.ok) {
      throw new Error(`API error ${response.status}`);
    }

    const data = await response.json();
    renderBulletList(headlineBullets, data.digest.headline_bullets);
    renderBulletList(themeBullets, data.digest.theme_bullets);
    renderBulletList(sourceBullets, data.digest.source_bullets);

    const healthItems = data.failures.length
      ? data.failures.map((name) => `${name} is currently unreachable.`)
      : ["All feeds responded in this refresh."];
    if (data.sources?.length) {
      healthItems.push(`Configured sources: ${data.sources.length}`);
    }
    renderBulletList(feedHealth, healthItems);

    renderUpdates(data.updates || []);
    lastUpdated.textContent = `Last updated: ${formatDate(data.digest.generated_at)}`;
  } catch (err) {
    renderBulletList(headlineBullets, ["Unable to load briefing right now."]);
    renderBulletList(themeBullets, ["Please refresh in a few seconds."]);
    renderBulletList(sourceBullets, [String(err)]);
    renderBulletList(feedHealth, ["Some feeds may be blocked or unavailable."]);
    updatesList.innerHTML = "";
    lastUpdated.textContent = "Last updated: failed";
  } finally {
    refreshBtn.disabled = false;
    refreshBtn.textContent = "Refresh Briefing";
  }
}

refreshBtn.addEventListener("click", loadBriefing);
loadBriefing();
