// mdview frontend: list structures from the API and render the selected one
// with the vendored Mol* viewer. No build step — `molstar` is a global from
// vendor/molstar/molstar.js.
"use strict";

const listEl = document.getElementById("file-list");
const statusEl = document.getElementById("status");
const rootLabel = document.getElementById("root-label");

function setStatus(msg) {
  statusEl.textContent = msg;
}

async function main() {
  const viewer = await molstar.Viewer.create("viewer", {
    layoutIsExpanded: false,
    layoutShowControls: true,
    layoutShowSequence: true,
    viewportShowExpand: true,
  });

  let activeItem = null;

  async function load(entry, li) {
    if (activeItem) activeItem.classList.remove("active");
    li.classList.add("active");
    activeItem = li;
    setStatus(`Loading ${entry.relpath}…`);
    try {
      await viewer.plugin.clear();
      await viewer.loadStructureFromUrl(
        `/api/file/${encodeURI(entry.relpath)}`,
        entry.format,
        false,
      );
      setStatus(`Loaded ${entry.relpath}`);
    } catch (err) {
      console.error(err);
      setStatus(`Failed to load ${entry.relpath}: ${err}`);
    }
  }

  try {
    const resp = await fetch("/api/files");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    rootLabel.textContent = data.root;

    if (!data.files.length) {
      setStatus("No loadable structures found under the data root.");
      return;
    }

    for (const entry of data.files) {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = entry.relpath;
      name.title = entry.relpath;
      const fmt = document.createElement("span");
      fmt.className = "fmt";
      fmt.textContent = entry.format;
      li.append(name, fmt);
      li.addEventListener("click", () => load(entry, li));
      listEl.appendChild(li);
    }
    setStatus(`${data.files.length} structure(s). Click one to view.`);
  } catch (err) {
    console.error(err);
    rootLabel.textContent = "—";
    setStatus(`Could not list files: ${err}`);
  }
}

main();
