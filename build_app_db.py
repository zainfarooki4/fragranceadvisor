# build_app_db.py
import json, sqlite3, os
from pathlib import Path

DB = "app.db"
DATA = "perfumes_clean.json"   # <- your cleaned file

def main():
    if not Path(DATA).exists():
        raise SystemExit(f"Missing {DATA}. Run clean.py first.")

    if os.path.exists(DB):
        os.remove(DB)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Pragmas for decent perf
    cur.executescript("""
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;
    PRAGMA temp_store=MEMORY;
    """)

    # Schema (no sillage)
    cur.executescript("""
    CREATE TABLE perfumes(
      id TEXT PRIMARY KEY,
      brand TEXT NOT NULL,
      name TEXT NOT NULL,
      image TEXT,                  -- optional image/filename/url
      year INTEGER,
      slug TEXT NOT NULL UNIQUE,
      popularity INTEGER DEFAULT 0
    );

    CREATE TABLE notes(
      perfume_id TEXT NOT NULL,
      kind TEXT CHECK(kind IN ('top','middle','base')) NOT NULL,
      note TEXT NOT NULL,
      PRIMARY KEY (perfume_id, kind, note),
      FOREIGN KEY (perfume_id) REFERENCES perfumes(id) ON DELETE CASCADE
    );

    CREATE TABLE accords(
      perfume_id TEXT NOT NULL,
      accord TEXT NOT NULL,
      rank INTEGER,                -- preserves order from JSON
      PRIMARY KEY (perfume_id, accord),
      FOREIGN KEY (perfume_id) REFERENCES perfumes(id) ON DELETE CASCADE
    );

    -- Full-text search across brand, name, and combined notes/accords
    CREATE VIRTUAL TABLE perfume_fts USING fts5(
      brand, name, notes,
      content='',
      tokenize='porter'
    );

    CREATE INDEX idx_perfumes_brand ON perfumes(brand);
    CREATE INDEX idx_perfumes_year  ON perfumes(year);
    CREATE INDEX idx_notes_note     ON notes(note);
    CREATE INDEX idx_accords_accord ON accords(accord);
    """)

    data = json.load(open(DATA, "r", encoding="utf-8"))

    perf_rows, note_rows, acc_rows, fts_rows = [], [], [], []
    for p in data:
        # Some cleaners include "image"; if not present, None is fine.
        image = p.get("image")
        perf_rows.append((
            p["id"], p["brand"], p["name"], image, p.get("year"), p["slug"], p.get("popularity", 0)
        ))

        all_notes = []
        for kind in ("top", "middle", "base"):
            for n in p.get("notes", {}).get(kind, []):
                note_rows.append((p["id"], kind, n))
                all_notes.append(n)

        # main_accords (ordered)
        for idx, a in enumerate(p.get("main_accords", []), start=1):
            acc_rows.append((p["id"], a, idx))

        # FTS text: brand, name, notes + accords
        fts_rows.append((
            p["brand"], p["name"], " ".join(all_notes + p.get("main_accords", []))
        ))

    with conn:
        cur.executemany(
            "INSERT INTO perfumes(id,brand,name,image,year,slug,popularity) VALUES (?,?,?,?,?,?,?)",
            perf_rows
        )
        cur.executemany(
            "INSERT INTO notes(perfume_id,kind,note) VALUES (?,?,?)",
            note_rows
        )
        cur.executemany(
            "INSERT INTO accords(perfume_id,accord,rank) VALUES (?,?,?)",
            acc_rows
        )
        cur.executemany(
            "INSERT INTO perfume_fts(brand,name,notes) VALUES (?,?,?)",
            fts_rows
        )

    conn.close()
    print(f"✅ Built {DB} with {len(perf_rows)} perfumes")

if __name__ == "__main__":
    main()