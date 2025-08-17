# clean.py
# Usage:
#   python3 clean.py --in perfumes.json --out perfumes_final.json --report
import json, re, argparse, hashlib

# ---------- regex helpers ----------
WS = re.compile(r"\s+")
NOTE_SEP = re.compile(r"\s*\|\s*")
ITEM_SEP = re.compile(r"\s*,\s*")
SLUG_ID_TAIL = re.compile(r"-\d+\.html?$", re.IGNORECASE)

# ---------- normalization maps ----------
LON_KEYS = {
    "very long lasting": "very long lasting",
    "very_long_lasting": "very long lasting",
    "verylonglasting": "very long lasting",
    "long lasting": "long lasting",
    "long_lasting": "long lasting",
    "longlasting": "long lasting",
    "moderate": "moderate",
    "weak": "weak",
    "poor": "poor",
}

BRAND_ALIASES = {
    "18 21 man made": "18.21 Man Made",
    # add more alias fixes as needed
}

# ---------- small utils ----------
def _canon_spaces(s: str) -> str:
    return WS.sub(" ", s).strip()

def _titleish(s: str) -> str:
    """Capitalize like a title but keep small words lowercase."""
    if not s:
        return s
    small = {"de","du","des","and","of","the","a","an","pour","eau"}
    parts = re.split(r'(\s+|-|/)', s.strip())
    out = []
    for p in parts:
        low = p.lower()
        out.append(low if low in small else (p[:1].upper() + p[1:]))
    return "".join(out)

def _to_int(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s.isdigit():
        return int(s)
    try:
        f = float(s)
        if f.is_integer():
            return int(f)
    except:
        pass
    return None

def _json_or_dict(v):
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, dict) else {}
        except:
            return {}
    return {}

def _normalize_counts(d: dict, key_map: dict) -> dict:
    """Normalize longevity dict keys and coerce counts to ints."""
    out = {}
    for k, v in (d or {}).items():
        lk = str(k).strip().lower()
        lk2 = lk.replace("_","")
        nk = key_map.get(lk) or key_map.get(lk2)
        if not nk:
            continue
        if isinstance(v, str):
            v = v.strip()
        num = _to_int(v)
        out[nk] = 0 if num is None else num
    return out

def _clean_list(items):
    """Deduplicate and nice-case a list of strings."""
    seen, out = set(), []
    for x in items or []:
        name = _titleish(_canon_spaces(str(x)))
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            out.append(name)
    return out

def _maybe_parse_embedded_json_from_list(parts):
    """Join list fragments that actually form a JSON blob and parse."""
    try:
        blob = "".join(parts).strip()
        if (blob.startswith('"') and blob.endswith('"')) or (blob.startswith("'") and blob.endswith("'")):
            blob = blob[1:-1]
        blob = blob.replace(r"\'", "'").replace(r'\"', '"')
        if blob.count("{")==blob.count("}") and blob.count("[")==blob.count("]"):
            parsed = json.loads(blob)
            return parsed if isinstance(parsed, (dict, list)) else None
    except:
        pass
    return None

# ---------- parsing fields ----------
def _parse_notes(raw):
    """
    Accepts:
      - dict: {"top":[...], "middle":[...], "base":[...]} (also 'head'/'heart'/'general'/'drydown')
      - string categorized: "Top: A, B | Middle: C | Base: D"
      - string flat: "A, B, C" (→ middle)
      - list (→ middle)
      - list with JSON fragments (reconstructed)
    """
    notes = {"top": [], "middle": [], "base": []}

    if isinstance(raw, dict):
        top = raw.get("top") or raw.get("head") or []
        mid = raw.get("middle") or raw.get("heart") or raw.get("general") or []
        base = raw.get("base") or raw.get("drydown") or []
        notes["top"]    = _clean_list(top if isinstance(top, list) else [])
        notes["middle"] = _clean_list(mid if isinstance(mid, list) else [])
        notes["base"]   = _clean_list(base if isinstance(base, list) else [])
        return notes

    if isinstance(raw, list):
        parsed = _maybe_parse_embedded_json_from_list(raw)
        if isinstance(parsed, dict):
            return _parse_notes(parsed)
        if isinstance(parsed, list):
            return {"top": [], "middle": _clean_list(parsed), "base": []}
        return {"top": [], "middle": _clean_list(raw), "base": []}

    if isinstance(raw, str) and raw.strip():
        s = raw.strip()
        # try JSON-like
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                return _parse_notes(json.loads(s))
            except:
                pass
        # categorized string
        if ":" in s and "|" in s:
            for part in NOTE_SEP.split(s):
                if ":" in part:
                    cat, items = part.split(":", 1)
                    bucket = "middle"
                    cat = cat.strip().lower()
                    if cat.startswith(("top","head")):
                        bucket = "top"
                    elif cat.startswith(("base","drydown")):
                        bucket = "base"
                    notes[bucket] = _clean_list([i for i in ITEM_SEP.split(items) if i.strip()])
        else:
            notes["middle"] = _clean_list([i for i in ITEM_SEP.split(s) if i.strip()])
        return notes

    return notes

def _parse_main_accords(raw):
    """Accept list/string/dict; returns a cleaned list."""
    if isinstance(raw, dict):
        arr = raw.get("main_accords") or raw.get("accords") or []
        return _clean_list(arr if isinstance(arr, list) else [])
    if isinstance(raw, list):
        return _clean_list(raw)
    if isinstance(raw, str) and raw.strip():
        s = raw.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                parsed = json.loads(s)
                return _parse_main_accords(parsed)
            except:
                pass
        parts = [p for p in re.split(r"\s*[|,]\s*", s) if p.strip()]
        return _clean_list(parts)
    return []

def _extract_name_from_url(url: str) -> str:
    """From Fragrantica-like URLs, pull the perfume name segment."""
    try:
        if not url:
            return ""
        path = url.split("://", 1)[-1]
        parts = path.split("/")
        seg = parts[-1] or parts[-2]
        seg = SLUG_ID_TAIL.sub("", seg).replace("-", " ")
        return _titleish(_canon_spaces(seg))
    except:
        return ""

def _best_name(p):
    # string-like fields
    for key in ("name","title","display_name","perfume","fragrance","product_name","full_name","name_en","h1","page_title"):
        v = p.get(key)
        if isinstance(v, str) and v.strip():
            return _titleish(_canon_spaces(v))
    # dict form: {"title": "...", "image": "..."}
    nm = p.get("name")
    if isinstance(nm, dict):
        t = nm.get("title")
        if isinstance(t, str) and t.strip():
            return _titleish(_canon_spaces(t))
    # slug fallback
    slug = p.get("slug") or p.get("name_slug")
    if isinstance(slug, str) and slug.strip():
        return _titleish(_canon_spaces(slug.replace("-", " ")))
    # URL fallback
    for key in ("url","link","page","source_url"):
        v = p.get(key)
        if isinstance(v, str) and v.strip():
            cand = _extract_name_from_url(v)
            if cand:
                return cand
    return ""

def _best_brand(p):
    v = p.get("brand")
    if isinstance(v, str) and v.strip():
        canon = _canon_spaces(v).lower()
        fixed = BRAND_ALIASES.get(canon)
        return fixed if fixed else _titleish(_canon_spaces(v))
    url = p.get("url") or p.get("link") or ""
    if isinstance(url, str) and "/perfume/" in url:
        try:
            tail = url.split("/perfume/", 1)[1]
            brand_seg = tail.split("/", 1)[0].replace("-", " ")
            canon = _canon_spaces(brand_seg).lower()
            fixed = BRAND_ALIASES.get(canon)
            return fixed if fixed else _titleish(_canon_spaces(brand_seg))
        except:
            pass
    return ""

def _best_image(p):
    """Try to extract a representative image string (filename or URL)."""
    if isinstance(p.get("image"), str) and p["image"].strip():
        return p["image"].strip()
    if isinstance(p.get("image_url"), str) and p["image_url"].strip():
        return p["image_url"].strip()
    nm = p.get("name")
    if isinstance(nm, dict):
        img = nm.get("image")
        if isinstance(img, str) and img.strip():
            return img.strip()
    imgs = p.get("images")
    if isinstance(imgs, list) and imgs:
        first = imgs[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
        if isinstance(first, dict):
            for k in ("url", "src", "image"):
                if isinstance(first.get(k), str) and first[k].strip():
                    return first[k].strip()
    return None

def _slugify(brand, name):
    base = f"{brand} {name}".strip().lower()
    s = re.sub(r"[^a-z0-9]+","-", base).strip("-")
    return s or "perfume"

def _stable_id(brand, name, year):
    raw = f"{brand}::{name}::{year or ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

# ---------- main clean ----------
def clean(input_file="perfumes.json", output_file="perfumes_clean.json", report=False, keep_unnamed=False):
    data = json.load(open(input_file, "r", encoding="utf-8"))
    final = []

    for p in data:
        name  = _best_name(p)  # ensure string (handles dict-name too)
        brand = _best_brand(p)
        year  = _to_int(p.get("year"))
        notes = _parse_notes(p.get("notes", p.get("accords", [])))
        main_accords = _parse_main_accords(p.get("main_accords", p.get("accords", [])))
        longevity = _normalize_counts(_json_or_dict(p.get("longevity")), LON_KEYS)
        image = _best_image(p)

        # Optionally skip entries that are totally anonymous
        if not keep_unnamed and not name:
            if not brand and not any(notes.values()) and not main_accords:
                continue

        pid  = _stable_id(brand, name, year)
        slug = _slugify(brand, name)
        popularity = sum(longevity.values())  # no sillage, as requested

        final.append({
            "id": pid,
            "slug": slug,
            "name": name,
            "brand": brand,
            "year": year,
            "image": image,                 # split image if available
            "main_accords": main_accords,
            "notes": notes,                 # {top, middle, base}
            "longevity": longevity,         # dict of vote counts
            "popularity": popularity
        })

    # write the canonical, sillage-free JSON
    json.dump(final, open(output_file, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    if report:
        total = len(final)
        with_year = sum(1 for x in final if x["year"] is not None)
        empty_name = sum(1 for x in final if not x["name"])
        avg_notes = (
            sum(len(x["notes"]["top"])+len(x["notes"]["middle"])+len(x["notes"]["base"]) for x in final)/total
        ) if total else 0
        print("— REPORT —")
        print(f"Total: {total}")
        print(f"With year: {with_year} ({with_year*100//max(total,1)}%)")
        print(f"Empty names: {empty_name}")
        print(f"Avg notes per perfume: {avg_notes:.2f}")

    print(f"✅ Wrote {output_file} (no sillage)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="perfumes.json")
    ap.add_argument("--out", dest="out", default="perfumes_clean.json")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--keep-unnamed", action="store_true")
    args = ap.parse_args()
    clean(args.inp, args.out, report=args.report, keep_unnamed=args.keep_unnamed)

if __name__ == "__main__":
    main()