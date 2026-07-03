"""Safe discovery and resolution of structure files under the data root."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .config import COORD_EXTENSIONS, TOPOLOGY_EXTENSIONS, TRAJECTORY_EXTENSIONS

if TYPE_CHECKING:
    from .config import Settings


def _empty_buckets() -> dict[str, list[dict]]:
    return {"files": [], "topologies": [], "coordinates": [], "trajectories": []}


def _classify(path: Path, rel: Path, settings: Settings, buckets: dict[str, list[dict]]) -> None:
    """Append ``path`` to whichever loadable buckets its suffix belongs to."""
    suffix = path.suffix.lower()
    base = {"name": rel.name, "relpath": rel.as_posix(), "size": path.stat().st_size}
    fmt = settings.format_for(suffix)
    if fmt is not None:
        buckets["files"].append({**base, "format": fmt})
    if suffix in TOPOLOGY_EXTENSIONS:
        buckets["topologies"].append({**base, "format": TOPOLOGY_EXTENSIONS[suffix]})
    if suffix in COORD_EXTENSIONS:
        buckets["coordinates"].append({**base, "format": COORD_EXTENSIONS[suffix]})
    if suffix in TRAJECTORY_EXTENSIONS:
        buckets["trajectories"].append({**base, "format": TRAJECTORY_EXTENSIONS[suffix]})


def scan(settings: Settings) -> dict[str, list[dict]]:
    """Walk the data root recursively and bucket every loadable file.

    Returns ``{"files", "topologies", "coordinates", "trajectories"}`` where each
    entry is ``{"name", "relpath", "size", "format"}``. A single file may appear in
    more than one bucket (e.g. a ``.pdb`` is both natively loadable and usable as a
    coordinate source). Hidden files/directories (dot-prefixed) are skipped; results
    are sorted by relpath.
    """
    root = settings.root
    buckets = _empty_buckets()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        _classify(path, rel, settings, buckets)
    for bucket in buckets.values():
        bucket.sort(key=lambda e: e["relpath"])
    return buckets


def browse(settings: Settings, reldir: str = "") -> dict | None:
    """List one directory (non-recursive), or None if it escapes/​isn't a dir.

    Returns ``{"dir", "parent", "dirs", "files", "topologies", "coordinates",
    "trajectories"}`` — ``dirs`` are immediate subfolders ``{"name", "relpath"}``;
    the bucket lists hold only the loadable files *in this directory*. ``parent``
    is the parent's relpath, or None at the root.
    """
    root = settings.root
    cur = resolve_dir_within_root(root, reldir)
    if cur is None:
        return None

    rel = cur.relative_to(root)
    dir_norm = "" if rel == Path(".") else rel.as_posix()
    parent = None
    if dir_norm:
        p = rel.parent
        parent = "" if p == Path(".") else p.as_posix()

    dirs: list[dict] = []
    buckets = _empty_buckets()
    for child in cur.iterdir():
        if child.name.startswith("."):
            continue
        crel = child.relative_to(root)
        if child.is_dir():
            dirs.append({"name": child.name, "relpath": crel.as_posix()})
        elif child.is_file():
            _classify(child, crel, settings, buckets)

    dirs.sort(key=lambda d: d["name"].lower())
    for bucket in buckets.values():
        bucket.sort(key=lambda e: e["relpath"])
    return {
        "dir": dir_norm,
        "parent": parent,
        "dirs": dirs,
        "ancestor_models": _ancestor_models(root, cur, settings),
        **buckets,
    }


def _ancestor_models(root: Path, cur: Path, settings: Settings) -> list[dict]:
    """Model-eligible files (structures/topologies) in directories ABOVE ``cur``.

    MD layouts often keep the topology in a prep/parent dir and trajectories in an
    ``output/`` subdir, so the trajectory model picker offers parent models too.
    Nearest ancestor first; each entry carries its Mol* ``kind``.
    """
    out: list[dict] = []
    if cur == root:
        return out
    anc = cur.parent
    while True:
        for child in sorted(anc.iterdir()):
            if not child.is_file() or child.name.startswith("."):
                continue
            suffix = child.suffix.lower()
            crel = child.relative_to(root).as_posix()
            fmt = settings.format_for(suffix)
            if fmt is not None:
                out.append({"name": child.name, "relpath": crel, "format": fmt, "kind": "model-url"})
            elif suffix in TOPOLOGY_EXTENSIONS:
                out.append(
                    {"name": child.name, "relpath": crel,
                     "format": TOPOLOGY_EXTENSIONS[suffix], "kind": "topology-url"}
                )
        if anc == root:
            break
        anc = anc.parent
    return out


def list_structures(settings: Settings) -> list[dict]:
    """Natively loadable structures only (convenience wrapper around :func:`scan`)."""
    return scan(settings)["files"]


_atom_count_cache: dict[tuple[str, int, int], int | None] = {}


def _count_atoms(path: Path) -> int | None:
    """Best-effort atom count for a topology/coordinate file, or None if unknown.

    Reads only as much as needed: PSF/prmtop expose the count in a header field,
    so we stop as soon as it's read; PDB/gro are counted from their atom records.
    Used to pair a coordinate file with a compatible topology (equal atom counts).
    """
    suffix = path.suffix.lower()
    try:
        if suffix == ".psf":
            with path.open("rb") as fh:
                for raw in fh:
                    if b"!NATOM" in raw:
                        return int(raw.split(b"!NATOM")[0].split()[-1])
            return None
        if suffix in {".prmtop", ".parm7"}:
            with path.open("r", errors="ignore") as fh:
                lines = iter(fh)
                for line in lines:
                    if line.startswith("%FLAG POINTERS"):
                        next(lines, "")          # skip the %FORMAT line
                        return int(next(lines, "").split()[0])
            return None
        if suffix in {".pdb", ".ent", ".pqr"}:
            n = 0
            with path.open("rb") as fh:
                for raw in fh:
                    if raw.startswith(b"ATOM") or raw.startswith(b"HETATM"):
                        n += 1
            return n
        if suffix == ".gro":
            with path.open("r", errors="ignore") as fh:
                fh.readline()                    # title line
                return int(fh.readline().strip())
    except (OSError, ValueError, IndexError):
        return None
    return None


def count_atoms(path: Path) -> int | None:
    """Cached :func:`_count_atoms`, invalidated when the file's size/mtime change."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_size, int(st.st_mtime))
    if key not in _atom_count_cache:
        _atom_count_cache[key] = _count_atoms(path)
    return _atom_count_cache[key]


def match_topologies(settings: Settings, coords_rel: str) -> dict | None:
    """Topologies (this folder + ancestors) pairable with ``coords_rel``.

    A coordinate file (e.g. a ``.pdb``) can be given real bonds — and its
    untruncated residue names, so Mol* draws carbohydrate/SNFG symbols — by
    merging it with a topology (``.psf``/``.prmtop``) via :func:`mdview.convert`.
    This finds candidate topologies and flags the ones whose atom count equals the
    coordinate file's, so the UI can offer a one-click "load with bonds". Matches
    are listed first, same-folder before ancestors. Returns None if ``coords_rel``
    escapes the root or isn't a file.
    """
    root = settings.root
    coord_path = resolve_within_root(root, coords_rel)
    if coord_path is None:
        return None
    coord_atoms = count_atoms(coord_path)

    seen: set[Path] = set()
    topos: list[dict] = []
    origin = coord_path.parent
    folder = origin
    while True:
        for child in sorted(folder.iterdir()):
            if not child.is_file() or child.name.startswith("."):
                continue
            if child.suffix.lower() not in TOPOLOGY_EXTENSIONS or child in seen:
                continue
            seen.add(child)
            n = count_atoms(child)
            topos.append({
                "name": child.name,
                "relpath": child.relative_to(root).as_posix(),
                "format": TOPOLOGY_EXTENSIONS[child.suffix.lower()],
                "n_atoms": n,
                "match": coord_atoms is not None and n == coord_atoms,
                "ancestor": folder != origin,
            })
        if folder == root:
            break
        folder = folder.parent

    topos.sort(key=lambda t: (not t["match"], t["ancestor"], t["name"].lower()))
    return {"coords": coords_rel, "coord_atoms": coord_atoms, "topologies": topos}


def resolve_within_root(root: Path, relpath: str) -> Path | None:
    """Resolve ``relpath`` under ``root``, or None if it escapes the root.

    Guards against ``..`` traversal and symlinks that point outside the root by
    resolving the final path and confirming ``root`` is one of its parents.
    """
    root = root.resolve()
    candidate = (root / relpath).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate


def resolve_dir_within_root(root: Path, reldir: str) -> Path | None:
    """Resolve ``reldir`` to a directory under ``root`` (``""`` = root itself).

    Like :func:`resolve_within_root` but requires a directory; guards against
    ``..`` traversal and symlinks escaping the root.
    """
    root = root.resolve()
    candidate = (root / reldir).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    if not candidate.is_dir():
        return None
    return candidate
