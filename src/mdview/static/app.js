// mdview frontend: list structures from the API and render the selected one
// with the vendored Mol* viewer. Topology-only files (PSF/prmtop) are paired
// with a coordinate file and converted server-side. No build step — `molstar`
// is a global from vendor/molstar/molstar.js.
"use strict";

const fileListEl = document.getElementById("file-list");
const filesSection = document.getElementById("files-section");
const topoListEl = document.getElementById("topo-list");
const topoSection = document.getElementById("topo-section");
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

  let activeRow = null;

  function markActive(el) {
    if (activeRow) activeRow.classList.remove("active");
    if (el) el.classList.add("active");
    activeRow = el;
  }

  async function loadUrl(url, format, label, row) {
    markActive(row || null);
    setStatus(`Loading ${label}…`);
    try {
      await viewer.plugin.clear();
      await viewer.loadStructureFromUrl(url, format, false);
      setStatus(`Loaded ${label}`);
    } catch (err) {
      console.error(err);
      setStatus(`Failed to load ${label}: ${err}`);
    }
  }

  // --- native structures ---------------------------------------------------
  function renderFiles(files) {
    if (!files.length) return;
    filesSection.hidden = false;
    for (const entry of files) {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = entry.relpath;
      name.title = entry.relpath;
      const fmt = document.createElement("span");
      fmt.className = "fmt";
      fmt.textContent = entry.format;
      li.append(name, fmt);
      li.addEventListener("click", () =>
        loadUrl(`/api/file/${encodeURI(entry.relpath)}`, entry.format, entry.relpath, li),
      );
      fileListEl.appendChild(li);
    }
  }

  // --- topologies (need a coordinate file) ---------------------------------
  function renderTopologies(topologies, coordinates, convertAvailable) {
    if (!topologies.length) return;
    topoSection.hidden = false;
    for (const topo of topologies) {
      const wrap = document.createElement("div");
      wrap.className = "topo";

      const name = document.createElement("div");
      name.className = "name";
      const n = document.createElement("span");
      n.textContent = topo.relpath;
      n.title = topo.relpath;
      const fmt = document.createElement("span");
      fmt.className = "fmt";
      fmt.textContent = topo.format;
      name.append(n, fmt);

      const pair = document.createElement("div");
      pair.className = "pair";
      const select = document.createElement("select");
      if (!convertAvailable) {
        const opt = document.createElement("option");
        opt.textContent = "convert extra not installed";
        select.append(opt);
        select.disabled = true;
      } else if (!coordinates.length) {
        const opt = document.createElement("option");
        opt.textContent = "no coordinate files found";
        select.append(opt);
        select.disabled = true;
      } else {
        for (const c of coordinates) {
          const opt = document.createElement("option");
          opt.value = c.relpath;
          opt.textContent = c.relpath;
          select.append(opt);
        }
      }
      const btn = document.createElement("button");
      btn.textContent = "Load";
      btn.disabled = select.disabled;
      btn.addEventListener("click", () => {
        const coords = select.value;
        const url =
          `/api/convert/${encodeURI(topo.relpath)}` +
          `?coords=${encodeURIComponent(coords)}&format=cif`;
        loadUrl(url, "mmcif", `${topo.relpath} + ${coords}`, wrap);
      });
      pair.append(select, btn);

      wrap.append(name, pair);
      topoListEl.appendChild(wrap);
    }
  }

  // --- fetch + render ------------------------------------------------------
  try {
    const resp = await fetch("/api/files");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    rootLabel.textContent = data.root;

    renderFiles(data.files);
    renderTopologies(data.topologies, data.coordinates, data.convert_available);

    const total = data.files.length + data.topologies.length;
    if (!total) {
      setStatus("No loadable structures found under the data root.");
    } else {
      const extra = data.topologies.length
        ? `, ${data.topologies.length} topolog${data.topologies.length === 1 ? "y" : "ies"}`
        : "";
      setStatus(`${data.files.length} structure(s)${extra}. Click one to view.`);
    }
  } catch (err) {
    console.error(err);
    rootLabel.textContent = "—";
    setStatus(`Could not list files: ${err}`);
  }
}

main();
