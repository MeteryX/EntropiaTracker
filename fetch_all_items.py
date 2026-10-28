"""
Holt umfassende Item-Daten von der Entropia Central Wiki-API
und schreibt sie in die lokale Datenbank.

Ausführung:
    python fetch_all_items.py

Die API ist öffentlich und read-only.
https://api.entropiacentral.com
"""
import json
import time
import urllib.request
from pathlib import Path

from database import SessionLocal, engine, migrate_db
import models

BASE = "https://api.entropiacentral.com"
CATEGORIES = {
    "weapons": "weapon",
    "armors": "armor",
    "armor-parts": "armor",
    "healing-tools": "healing",
    "materials": "resource",
    "finders": "tool",
    "excavators": "tool",
}

def api_get(path, params=None):
    url = BASE + path
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += "?" + qs
    req = urllib.request.Request(url, headers={"User-Agent": "EntropiaTracker/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def fetch_all(category):
    """Holt alle Einträge einer Kategorie (paginiert)."""
    items = []
    page = 1
    page_size = 50
    while True:
        print(f"  {category} Seite {page} ...", end=" ")
        try:
            data = api_get(f"/{category}", {"pageNumber": page, "pageSize": page_size})
        except Exception as e:
            print(f"Fehler: {e}")
            break
        # API-Antwort kann Liste oder Objekt mit 'items' / direkt Array sein
        batch = data if isinstance(data, list) else data.get("items", data.get("data", []))
        if not batch:
            print("leer")
            break
        items.extend(batch)
        print(f"{len(batch)} Einträge")
        if len(batch) < page_size:
            break
        page += 1
        time.sleep(0.4)  # freundlich zur API
    return items

def extract_name(entry):
    return entry.get("name") or entry.get("Name") or entry.get("title") or "Unknown"

def extract_tt(entry):
    for key in ("tt", "TT", "ttValue", "tradeTerminalValue", "value"):
        if key in entry and entry[key] is not None:
            try:
                return float(entry[key])
            except Exception:
                pass
    return 0.0

def main():
    models.Base.metadata.create_all(bind=engine)
    migrate_db()  # Spalten hinzufügen falls alte DB
    db = SessionLocal()
    added = 0
    skipped = 0
    seen_names = set()

    # Bereits vorhandene Namen laden
    for existing in db.query(models.Item.name).all():
        seen_names.add(existing[0])

    for api_cat, local_cat in CATEGORIES.items():
        print(f"\n=== {api_cat} ===")
        entries = fetch_all(api_cat)
        for entry in entries:
            name = extract_name(entry)
            if not name or name == "Unknown":
                continue
            if name in seen_names:
                skipped += 1
                continue
            seen_names.add(name)
            item = models.Item(
                name=name,
                tt_value=extract_tt(entry),
                tt_max=entry.get("ttMax") or entry.get("maxTT") or entry.get("tt"),
                markup=100.0,
                category=local_cat,
                damage=entry.get("damage") or entry.get("Damage"),
                dps=entry.get("dps") or entry.get("DPS"),
                dpp=entry.get("dpp") or entry.get("DPP"),
                efficiency=entry.get("efficiency") or entry.get("Efficiency"),
                decay=entry.get("decay") or entry.get("Decay"),
                ammo_burn=entry.get("ammoBurn") or entry.get("ammo_burn"),
                range_m=entry.get("range") or entry.get("Range"),
                durability=entry.get("durability") or entry.get("Durability"),
                limited=bool(entry.get("limited") or entry.get("Limited")),
                item_type=entry.get("type") or entry.get("Type"),
                item_class=entry.get("class") or entry.get("Class"),
            )
            db.add(item)
            added += 1
        try:
            db.commit()
            print(f"  -> {added} neu, {skipped} übersprungen (gesamt)")
        except Exception as e:
            db.rollback()
            print(f"  Commit-Fehler (übersprungen): {e}")

    db.close()
    print(f"\nFertig. {added} Items hinzugefügt, {skipped} übersprungen.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print("\n" + "=" * 50)
        print("FEHLER:")
        print("=" * 50)
        traceback.print_exc()
    print("\nDrücke Enter zum Beenden...")
    input()
