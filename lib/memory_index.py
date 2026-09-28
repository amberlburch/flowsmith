"""
memory_index — retrieval + dedup over the workspace memory layer.

The memory layer is markdown that gets loaded wholesale into context: learned
rules, feedback, project state, references, plus the file-per-fact auto-memory.
That dilutes context as it grows and has no way to flag a near-duplicate rule on
insert. This module adds retrieval-over-recall and dedup WITHOUT changing the
storage format — markdown stays canonical and human-editable; this is a derived
cache (gitignored under cache/).

Retrieval uses SQLite FTS5 BM25, matching the existing `session_index.py` /
`/recall` pattern in this workspace (no torch, no embeddings service). Semantic
embeddings would need a local model (~2GB) for marginal gain over BM25 on a small
curated corpus; lexical retrieval is the right-sized choice here. Dedup uses token
Jaccard overlap — enough to flag "this rule already exists" on insert.

Indexes two roots:
  - memory/*.md                              (legacy: rules, feedback, project, reference)
  - projects/<home-slug>/memory/*.md   (file-per-fact auto-memory)
Credential files (gitignored) are never indexed.

Chunking:
  - learned-rules.md      → one chunk per numbered rule
  - file-per-fact files   → one chunk per file
  - other legacy files    → one chunk per H2 (## ) section, else whole file

CLI:
    python3 lib/memory_index.py --incremental        (default — only changed files)
    python3 lib/memory_index.py --rebuild
    python3 lib/memory_index.py --query "lead list rules"
    python3 lib/memory_index.py --dupe "Never add Corient employees to lead lists"
    python3 lib/memory_index.py --stats
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from pathlib import Path

CLAUDE = Path.home() / ".claude"
DB_PATH = CLAUDE / "cache" / "memory.db"

# Roots to index. (label, dir, glob)
ROOTS = [
    ("legacy", CLAUDE / "memory", "*.md"),
    ("fact", CLAUDE / "projects" / ("-" + str(Path.home()).strip("/").replace("/", "-")) / "memory", "*.md"),
]

# Never index credential-bearing files (also gitignored).
EXCLUDE_NAMES = {
    "reference_auth_credentials.md",
    "reference_google_workspace_oauth.md",
    "reference_n8n_credentials.md",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    path        TEXT PRIMARY KEY,
    sha         TEXT NOT NULL,
    indexed_at  TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    path UNINDEXED,
    root UNINDEXED,
    chunk_id UNINDEXED,
    title,
    content,
    tokenize='unicode61 remove_diacritics 2'
);
"""

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "is", "it", "for", "on",
    "that", "this", "with", "as", "be", "are", "at", "by", "not", "no", "if",
    "because", "never", "always", "do", "you", "your", "i",
}


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP and len(t) > 2}


def _rel(path: str) -> str:
    """Display path relative to ~/.claude when possible, else the absolute path.
    Never raises — a memory root outside ~/.claude is unusual but must not crash."""
    try:
        return str(Path(path).relative_to(CLAUDE))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_file(path: Path) -> list[tuple[str, str]]:
    """Return [(title, content), ...] for a markdown file."""
    text = path.read_text(errors="replace")

    if path.name == "learned-rules.md":
        # One chunk per numbered rule: lines starting "N. ".
        chunks: list[tuple[str, str]] = []
        current: list[str] = []
        title = ""
        for line in text.splitlines():
            m = re.match(r"^(\d+)\.\s", line)
            if m:
                if current:
                    chunks.append((title, "\n".join(current).strip()))
                title = f"rule {m.group(1)}"
                current = [line]
            elif current:
                current.append(line)
        if current:
            chunks.append((title, "\n".join(current).strip()))
        return [c for c in chunks if c[1]]

    # Strip YAML frontmatter for the body, keep it for the first chunk's title.
    fm_title = ""
    body = text
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if fm:
        name_m = re.search(r"^name:\s*(.+)$", fm.group(1), re.MULTILINE)
        if name_m:
            fm_title = name_m.group(1).strip()
        body = text[fm.end():]

    # Split on H2 sections; if none, whole file is one chunk.
    parts = re.split(r"(?m)^##\s+(.+)$", body)
    if len(parts) <= 1:
        title = fm_title or path.stem
        return [(title, body.strip())] if body.strip() else []

    chunks = []
    preamble = parts[0].strip()
    if preamble:
        chunks.append((fm_title or path.stem, preamble))
    # parts after split: [pre, h2title, h2body, h2title, h2body, ...]
    for i in range(1, len(parts), 2):
        h = parts[i].strip()
        b = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if b:
            chunks.append((h, b))
    return chunks


def _iter_files():
    for root_label, root_dir, glob in ROOTS:
        if not root_dir.exists():
            continue
        for path in sorted(root_dir.glob(glob)):
            if path.name in EXCLUDE_NAMES or path.name == "MEMORY.md":
                continue
            yield root_label, path


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

def reindex(conn: sqlite3.Connection, *, rebuild: bool = False) -> dict:
    if rebuild:
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM sources")
        conn.commit()

    known = dict(conn.execute("SELECT path, sha FROM sources").fetchall())
    seen: set[str] = set()
    files_indexed = 0
    chunks_written = 0

    for root_label, path in _iter_files():
        key = str(path)
        seen.add(key)
        text = path.read_text(errors="replace")
        sha = _sha(text)
        if known.get(key) == sha and not rebuild:
            continue  # unchanged

        # Replace this file's chunks.
        conn.execute("DELETE FROM chunks WHERE path = ?", (key,))
        for idx, (title, content) in enumerate(_chunk_file(path)):
            conn.execute(
                "INSERT INTO chunks (path, root, chunk_id, title, content) VALUES (?,?,?,?,?)",
                (key, root_label, f"{path.stem}#{idx}", title, content),
            )
            chunks_written += 1
        conn.execute(
            "INSERT INTO sources (path, sha, indexed_at) VALUES (?,?,datetime('now')) "
            "ON CONFLICT(path) DO UPDATE SET sha=excluded.sha, indexed_at=excluded.indexed_at",
            (key, sha),
        )
        files_indexed += 1

    # Drop sources/chunks for files that no longer exist.
    for stale in set(known) - seen:
        conn.execute("DELETE FROM chunks WHERE path = ?", (stale,))
        conn.execute("DELETE FROM sources WHERE path = ?", (stale,))

    conn.commit()
    return {"files_indexed": files_indexed, "chunks_written": chunks_written}


def _ensure_fresh(conn: sqlite3.Connection) -> None:
    """Keep the index current on every read. Incremental reindex is cheap (a sha
    compare per file over ~50 small markdown files), so recall()/find_duplicates()
    are always fresh without needing a cron job or Stop hook."""
    reindex(conn)


# ---------------------------------------------------------------------------
# Retrieval + dedup (public API)
# ---------------------------------------------------------------------------

def _fts_query(text: str) -> str:
    """Build a safe FTS5 OR-query from free text."""
    toks = _TOKEN_RE.findall(text.lower())
    toks = [t for t in toks if t not in _STOP and len(t) > 2]
    return " OR ".join(toks) if toks else text.strip().replace('"', "")


def recall(query: str, k: int = 5) -> list[dict]:
    """Top-k relevant memory chunks for a query. Each: path, title, snippet, score."""
    conn = db()
    _ensure_fresh(conn)
    fts = _fts_query(query)
    if not fts:
        return []
    rows = conn.execute(
        "SELECT path, title, snippet(chunks, 4, '[', ']', ' … ', 12), bm25(chunks) "
        "FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?",
        (fts, k),
    ).fetchall()
    out = []
    for path, title, snip, score in rows:
        out.append({
            "path": _rel(path),
            "title": title,
            "snippet": snip.strip(),
            "score": round(-float(score), 3),  # bm25 is negative; flip so higher = better
        })
    return out


def find_duplicates(text: str, threshold: float = 0.65, limit: int = 3) -> list[dict]:
    """Flag existing chunks that substantially contain `text`.

    Used on rule insert: if a near-identical rule already exists, surface it (and
    its rule number, embedded in the title) so the caller can supersede instead of
    duplicating. Uses the overlap coefficient (intersection / smaller token set),
    not Jaccard — a short new rule is a duplicate when most of its tokens already
    appear in a longer existing rule, regardless of that rule's extra reasoning.
    """
    conn = db()
    _ensure_fresh(conn)
    target = _tokens(text)
    if not target:
        return []
    hits: list[dict] = []
    for path, title, content in conn.execute("SELECT path, title, content FROM chunks"):
        other = _tokens(content)
        if not other:
            continue
        inter = len(target & other)
        overlap = inter / min(len(target), len(other))
        if overlap >= threshold:
            hits.append({
                "path": _rel(path),
                "title": title,
                "similarity": round(overlap, 3),
                "excerpt": content[:160],
            })
    hits.sort(key=lambda h: h["similarity"], reverse=True)
    return hits[:limit]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Memory retrieval + dedup index")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--incremental", action="store_true", help="index only changed files (default)")
    g.add_argument("--rebuild", action="store_true", help="drop and reindex everything")
    g.add_argument("--query", help="retrieve top-k chunks for a query")
    g.add_argument("--dupe", help="flag near-duplicate chunks for the given text")
    g.add_argument("--stats", action="store_true", help="index stats")
    p.add_argument("-k", type=int, default=5)
    args = p.parse_args(argv)

    conn = db()

    if args.query:
        for r in recall(args.query, k=args.k):
            print(f"[{r['score']}] {r['path']} — {r['title']}")
            print(f"    {r['snippet']}")
        return 0

    if args.dupe:
        dupes = find_duplicates(args.dupe)
        if not dupes:
            print("No near-duplicates above threshold.")
        for d in dupes:
            print(f"~{d['similarity']} {d['path']} — {d['title']}: {d['excerpt']}")
        return 0

    if args.stats:
        _ensure_fresh(conn)
        files = conn.execute("SELECT count(*) FROM sources").fetchone()[0]
        chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        by_root = conn.execute("SELECT root, count(*) FROM chunks GROUP BY root").fetchall()
        print(f"files: {files}, chunks: {chunks}")
        for root, n in by_root:
            print(f"  {root}: {n} chunks")
        return 0

    result = reindex(conn, rebuild=args.rebuild)
    print(f"indexed {result['files_indexed']} file(s), wrote {result['chunks_written']} chunk(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
