// mdview frontend: a directory browser (breadcrumb + current folder) over the
// /api/browse endpoint, rendering the selected structure/trajectory with the
// vendored Mol* viewer. No build step — `molstar` is a global.
"use strict";

const el = (id) => document.getElementById(id);
const breadcrumbEl = el("breadcrumb");
const folderListEl = el("folder-list");
const fileListEl = el("file-list");
const filesSection = el("files-section");
const topoListEl = el("topo-list");
const topoSection = el("topo-section");
const trajSection = el("traj-section");
const trajModelSel = el("traj-model");
const trajCoordsSel = el("traj-coords");
const trajLoadBtn = el("traj-load");
const procOptions = el("proc-options");
const procStride = el("proc-stride");
const procStrip = el("proc-strip");
const procSelect = el("proc-select");
const procAlign = el("proc-align");
const procAlignSel = el("proc-align-sel");
const procNote = el("proc-note");
const emptyNote = el("empty-note");
const renderRes = el("render-res");
const renderName = el("render-name");
const renderBtn = el("render-btn");
const renderNote = el("render-note");
const renderGallery = el("render-gallery");
const statusEl = el("status");
const rootLabel = el("root-label");

function setStatus(msg) {
  statusEl.textContent = msg;
}

let viewer;
let activeRow = null;
// Current-directory trajectory state, read by the once-attached load button.
let curModels = [];
let curTrajectories = [];
let curProcessAvailable = false;
let curDir = "";

function markActive(node) {
  if (activeRow) activeRow.classList.remove("active");
  if (node) node.classList.add("active");
  activeRow = node;
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

// --- breadcrumb + folder navigation ---------------------------------------
function crumb(label, target) {
  const span = document.createElement("span");
  span.className = "crumb";
  span.textContent = label;
  span.addEventListener("click", () => loadDir(target));
  return span;
}

function renderBreadcrumb(dir) {
  breadcrumbEl.replaceChildren(crumb("root", ""));
  if (!dir) return;
  let acc = "";
  for (const part of dir.split("/")) {
    acc = acc ? `${acc}/${part}` : part;
    const sep = document.createElement("span");
    sep.className = "crumb-sep";
    sep.textContent = " / ";
    breadcrumbEl.append(sep, crumb(part, acc));
  }
}

function renderFolders(parent, dirs) {
  folderListEl.replaceChildren();
  const addFolder = (label, target) => {
    const li = document.createElement("li");
    li.className = "folder";
    li.textContent = `📁 ${label}`;
    li.addEventListener("click", () => loadDir(target));
    folderListEl.appendChild(li);
  };
  if (parent !== null) addFolder(".. (up)", parent);
  for (const d of dirs) addFolder(`${d.name}/`, d.relpath);
}

// --- native structures ----------------------------------------------------
function renderFiles(files) {
  fileListEl.replaceChildren();
  filesSection.hidden = !files.length;
  for (const entry of files) {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = entry.name;
    name.title = entry.relpath;
    const fmt = document.createElement("span");
    fmt.className = "fmt";
    fmt.textContent = entry.format;
    li.append(name, fmt);
    li.addEventListener("click", () =>
      loadUrl(`/api/file/${encodeURI(entry.relpath)}`, entry.format, entry.name, li),
    );
    fileListEl.appendChild(li);
  }
}

// --- topologies (need a coordinate file) ----------------------------------
function renderTopologies(topologies, coordinates, convertAvailable) {
  topoListEl.replaceChildren();
  topoSection.hidden = !topologies.length;
  for (const topo of topologies) {
    const wrap = document.createElement("div");
    wrap.className = "topo";

    const name = document.createElement("div");
    name.className = "name";
    const n = document.createElement("span");
    n.textContent = topo.name;
    n.title = topo.relpath;
    const fmt = document.createElement("span");
    fmt.className = "fmt";
    fmt.textContent = topo.format;
    name.append(n, fmt);

    const pair = document.createElement("div");
    pair.className = "pair";
    const select = document.createElement("select");
    if (!convertAvailable) {
      select.append(new Option("convert extra not installed"));
      select.disabled = true;
    } else if (!coordinates.length) {
      select.append(new Option("no coordinate files here"));
      select.disabled = true;
    } else {
      for (const c of coordinates) select.append(new Option(c.name, c.relpath));
    }
    const btn = document.createElement("button");
    btn.textContent = "Load";
    btn.disabled = select.disabled;
    btn.addEventListener("click", () => {
      const coords = select.value;
      // mol2 carries the topology's explicit bonds (real connectivity, not a guess).
      const url =
        `/api/convert/${encodeURI(topo.relpath)}` +
        `?coords=${encodeURIComponent(coords)}&format=mol2`;
      loadUrl(url, "mol2", `${topo.name} + ${coords.split("/").pop()}`, wrap);
    });
    pair.append(select, btn);
    wrap.append(name, pair);
    topoListEl.appendChild(wrap);
  }
}

// --- trajectories (model/topology + coordinates -> Mol* playback) ---------
function renderTrajectories(files, topologies, trajectories, ancestorModels, processAvailable) {
  trajSection.hidden = !trajectories.length;
  curProcessAvailable = processAvailable;
  procOptions.hidden = !processAvailable;
  procNote.textContent = "";

  // Models: a native structure (model-url) or topology (topology-url) in THIS
  // folder, plus model-eligible files from ancestor folders (common MD layout:
  // topology in a parent dir, trajectory in an output/ subdir).
  curModels = [
    ...files.map((f) => ({ ...f, kind: "model-url", label: f.name })),
    ...topologies.map((t) => ({ ...t, kind: "topology-url", label: t.name })),
    ...ancestorModels.map((m) => ({ ...m, label: `↑ ${m.relpath}` })),
  ];
  curTrajectories = trajectories;
  if (!trajectories.length) return;

  trajModelSel.replaceChildren();
  for (const m of curModels) trajModelSel.append(new Option(`${m.label} (${m.format})`, m.relpath));
  trajCoordsSel.replaceChildren();
  for (const t of trajectories) trajCoordsSel.append(new Option(`${t.name} (${t.format})`, t.relpath));

  const noModel = curModels.length === 0;
  trajLoadBtn.disabled = noModel;
  if (noModel) trajModelSel.append(new Option("no model/topology in this folder"));
}

function processingRequested() {
  return (
    curProcessAvailable &&
    (Number(procStride.value) > 1 ||
      procStrip.checked ||
      procAlign.checked ||
      procSelect.value.trim() !== "")
  );
}

async function loadProcessed(model, traj) {
  procNote.textContent = "Processing on the server…";
  procNote.className = "ok";
  const body = {
    top: model.relpath,
    traj: traj.relpath,
    select: procSelect.value.trim() || "all",
    strip: procStrip.checked,
    stride: Math.max(1, Number(procStride.value) || 1),
    align: procAlign.checked,
    align_select: procAlignSel.value.trim() || "backbone",
  };
  const resp = await fetch("/api/prepare", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  procNote.textContent = `${data.n_atoms} atoms, ${data.n_frames} frames`;
  await viewer.plugin.clear();
  await viewer.loadTrajectory({
    model: { kind: "model-url", url: data.model_url, format: data.model_format, isBinary: false },
    coordinates: {
      kind: "coordinates-url",
      url: data.trajectory_url,
      format: data.trajectory_format,
      isBinary: true,
    },
  });
}

async function loadRaw(model, traj) {
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
}

async function onTrajLoad() {
  const model = curModels[trajModelSel.selectedIndex];
  const traj = curTrajectories[trajCoordsSel.selectedIndex];
  if (!model || !traj) return;
  markActive(null);
  procNote.textContent = "";
  trajLoadBtn.disabled = true;
  const processed = processingRequested();
  setStatus(`${processed ? "Processing" : "Loading"} ${traj.name} on ${model.name}…`);
  try {
    if (processed) await loadProcessed(model, traj);
    else await loadRaw(model, traj);
    setStatus(`Loaded ${traj.name} (use the playback bar to animate)`);
  } catch (err) {
    console.error(err);
    procNote.className = "";
    procNote.textContent = String(err.message || err);
    setStatus(`Failed to load trajectory: ${err.message || err}`);
  } finally {
    trajLoadBtn.disabled = false;
  }
}

// --- directory rendering + navigation -------------------------------------
function render(data) {
  rootLabel.textContent = data.root;
  renderBreadcrumb(data.dir);
  renderFolders(data.parent, data.dirs);
  renderFiles(data.files);
  renderTopologies(data.topologies, data.coordinates, data.convert_available);
  renderTrajectories(
    data.files, data.topologies, data.trajectories,
    data.ancestor_models, data.process_available,
  );

  const nLoadable = data.files.length + data.topologies.length + data.trajectories.length;
  emptyNote.hidden = nLoadable > 0 || data.dirs.length > 0;
  const bits = [`${data.dirs.length} folder(s)`];
  if (data.files.length) bits.push(`${data.files.length} structure(s)`);
  if (data.trajectories.length) bits.push(`${data.trajectories.length} trajectory(ies)`);
  setStatus(bits.join(", "));
}

async function loadDir(dir) {
  setStatus(`Opening ${dir || "root"}…`);
  try {
    const resp = await fetch(`/api/browse?dir=${encodeURIComponent(dir)}`);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
    curDir = dir;
    render(data);
  } catch (err) {
    console.error(err);
    setStatus(`Could not browse ${dir || "root"}: ${err.message || err}`);
  }
}

// --- render the current view to a PNG saved on the server -----------------
const nextFrame = () =>
  new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

async function captureDataUri(scale) {
  const helper = viewer.plugin.helpers.viewportScreenshot;
  if (!helper) throw new Error("screenshot helper unavailable");
  const c3d = viewer.plugin.canvas3d;
  // Supersample by temporarily raising the canvas pixelScale (Mol*'s hi-res
  // lever), then restore. Falls back to viewport size if anything goes wrong.
  if (scale > 1 && c3d) {
    const prev = (c3d.props && c3d.props.pixelScale) || 1;
    try {
      c3d.setProps({ pixelScale: prev * scale });
      await nextFrame();
      return await helper.getImageDataUri();
    } finally {
      c3d.setProps({ pixelScale: prev });
      await nextFrame();
    }
  }
  return await helper.getImageDataUri();
}

async function loadRenders() {
  try {
    const resp = await fetch("/api/renders");
    const data = await resp.json();
    renderGallery.replaceChildren();
    for (const r of data.renders) {
      const a = document.createElement("a");
      a.href = r.url;
      a.target = "_blank";
      a.title = r.name;
      const img = document.createElement("img");
      img.src = r.url;
      img.alt = r.name;
      a.appendChild(img);
      renderGallery.appendChild(a);
    }
  } catch (err) {
    console.error(err);
  }
}

async function renderToServer() {
  renderBtn.disabled = true;
  renderNote.textContent = "Rendering…";
  try {
    const dataUri = await captureDataUri(Number(renderRes.value) || 1);
    const resp = await fetch("/api/render", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ image: dataUri, name: renderName.value.trim() || null }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
    renderNote.textContent = `Saved ${data.filename}`;
    renderName.value = "";
    await loadRenders();
  } catch (err) {
    console.error(err);
    renderNote.textContent = `Render failed: ${err.message || err}`;
  } finally {
    renderBtn.disabled = false;
  }
}

async function main() {
  viewer = await molstar.Viewer.create("viewer", {
    layoutIsExpanded: false,
    layoutShowControls: true,
    layoutShowSequence: true,
    viewportShowExpand: true,
  });
  trajLoadBtn.addEventListener("click", onTrajLoad);
  renderBtn.addEventListener("click", renderToServer);
  await loadRenders();
  await loadDir("");
}

main();
