// mdview frontend: list structures from the API and render the selected one
// with the vendored Mol* viewer. Topology-only files (PSF/prmtop) are paired
// with a coordinate file and converted server-side. No build step — `molstar`
// is a global from vendor/molstar/molstar.js.
"use strict";

const fileListEl = document.getElementById("file-list");
const filesSection = document.getElementById("files-section");
const topoListEl = document.getElementById("topo-list");
const topoSection = document.getElementById("topo-section");
const trajSection = document.getElementById("traj-section");
const trajModelSel = document.getElementById("traj-model");
const trajCoordsSel = document.getElementById("traj-coords");
const trajLoadBtn = document.getElementById("traj-load");
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
        // mol2 carries the topology's explicit bonds, so Mol* uses the real
        // connectivity instead of guessing it from (often distorted) distances.
        const url =
          `/api/convert/${encodeURI(topo.relpath)}` +
          `?coords=${encodeURIComponent(coords)}&format=mol2`;
        loadUrl(url, "mol2", `${topo.relpath} + ${coords}`, wrap);
      });
      pair.append(select, btn);

      wrap.append(name, pair);
      topoListEl.appendChild(wrap);
    }
  }

  // --- trajectories (model/topology + coordinates -> Mol* playback) --------
  function renderTrajectories(files, topologies, trajectories) {
    if (!trajectories.length) return;
    trajSection.hidden = false;

    // Models can be a native structure (model-url) or a topology (topology-url).
    const models = [
      ...files.map((f) => ({ ...f, kind: "model-url" })),
      ...topologies.map((t) => ({ ...t, kind: "topology-url" })),
    ];
    for (const m of models) {
      const opt = document.createElement("option");
      opt.value = m.relpath;
      opt.textContent = `${m.relpath} (${m.format})`;
      trajModelSel.appendChild(opt);
    }
    for (const t of trajectories) {
      const opt = document.createElement("option");
      opt.value = t.relpath;
      opt.textContent = `${t.relpath} (${t.format})`;
      trajCoordsSel.appendChild(opt);
    }

    const noModel = models.length === 0;
    trajLoadBtn.disabled = noModel;
    if (noModel) {
      const opt = document.createElement("option");
      opt.textContent = "no model/topology found";
      trajModelSel.appendChild(opt);
    }

    trajLoadBtn.addEventListener("click", async () => {
      const model = models[trajModelSel.selectedIndex];
      const traj = trajectories[trajCoordsSel.selectedIndex];
      if (!model || !traj) return;
      markActive(null);
      setStatus(`Loading ${traj.relpath} on ${model.relpath}…`);
      try {
        await viewer.plugin.clear();
        await viewer.loadTrajectory({
          // model/topology files (psf/pdb/gro) are text; trajectories are binary
          model: {
            kind: model.kind,
            url: `/api/file/${encodeURI(model.relpath)}`,
            format: model.format,
            isBinary: false,
          },
          coordinates: {
            kind: "coordinates-url",
            url: `/api/file/${encodeURI(traj.relpath)}`,
            format: traj.format,
            isBinary: true,
          },
        });
        setStatus(`Loaded ${traj.relpath} (use the playback bar to animate)`);
      } catch (err) {
        console.error(err);
        setStatus(`Failed to load trajectory: ${err}`);
      }
    });
  }

  // --- fetch + render ------------------------------------------------------
  try {
    const resp = await fetch("/api/files");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    rootLabel.textContent = data.root;

    renderFiles(data.files);
    renderTopologies(data.topologies, data.coordinates, data.convert_available);
    renderTrajectories(data.files, data.topologies, data.trajectories);

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
