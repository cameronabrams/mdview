"""DCD header repair for serving.

Some NAMD/CHARMM DCD files store ``NSET`` (the frame count) as 0 in their header
even though the file contains frames. Mol*'s DCD reader trusts ``NSET`` and so
reads zero frames, which makes trajectory loading fail with an opaque
"Unresolved dependency" error. We recompute the true frame count from the file
geometry and patch the 4-byte ``NSET`` field while streaming, leaving everything
else byte-for-byte identical.

The patch is applied conservatively: only when the geometry yields a clean
integer frame count that disagrees with the header. Fixed-atom DCDs (NAMNF > 0,
which Mol* doesn't support anyway) and anything we can't parse are served as-is.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterator

_NSET_OFFSET = 8  # bytes 8..12 hold ICNTRL[0] = NSET
_HEAD_READ = 8192  # enough for the first block + title + natom block


def _endian(head: bytes) -> str | None:
    """Return '<' or '>' from the leading block-size marker (84), or None."""
    for e in ("<", ">"):
        if len(head) >= 4 and struct.unpack(e + "i", head[0:4])[0] == 84:
            return e
    return None


def _true_frame_count(head: bytes, file_size: int, e: str) -> int | None:
    """Frame count implied by the file geometry, or None if unparseable."""
    if head[4:8] != b"CORD" or len(head) < 88:
        return None
    icntrl = struct.unpack(e + "20i", head[8:88])
    namnf, has_cell, four_dim = icntrl[8], icntrl[10] != 0, icntrl[11] == 1
    if namnf > 0:
        return None  # fixed-atom DCD — unsupported, leave untouched

    off = 92  # past [84]['CORD'][20 int32][84]
    if len(head) < off + 4:
        return None
    title_len = struct.unpack(e + "i", head[off : off + 4])[0]
    off += 4 + title_len + 4  # title block
    if len(head) < off + 12 or struct.unpack(e + "i", head[off : off + 4])[0] != 4:
        return None
    natom = struct.unpack(e + "i", head[off + 4 : off + 8])[0]
    header_size = off + 12  # past [4][natom][4]

    per_frame = 3 * (4 + natom * 4 + 4)
    if has_cell:
        per_frame += 4 + 48 + 4
    if four_dim:
        per_frame += 4 + natom * 4 + 4

    body = file_size - header_size
    if per_frame <= 0 or body < 0 or body % per_frame != 0:
        return None
    return body // per_frame


def repair_plan(path: Path) -> tuple[int, str] | None:
    """If the DCD's NSET is wrong, return (correct_nset, endian); else None."""
    size = path.stat().st_size
    with path.open("rb") as fh:
        head = fh.read(_HEAD_READ)
    e = _endian(head)
    if e is None:
        return None
    header_nset = struct.unpack(e + "i", head[_NSET_OFFSET : _NSET_OFFSET + 4])[0]
    true_n = _true_frame_count(head, size, e)
    if true_n is None or true_n == header_nset:
        return None
    return true_n, e


def patched_stream(
    path: Path, nset: int, endian: str, chunk_size: int = 1 << 20
) -> Iterator[bytes]:
    """Yield the file bytes with the NSET header field overwritten."""
    packed = struct.pack(endian + "i", nset)
    with path.open("rb") as fh:
        first = bytearray(fh.read(chunk_size))
        if len(first) >= _NSET_OFFSET + 4:
            first[_NSET_OFFSET : _NSET_OFFSET + 4] = packed
        yield bytes(first)
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            yield chunk
