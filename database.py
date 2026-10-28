from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).parent
    meipass = Path(getattr(sys, "_MEIPASS", BASE))
    db = BASE / "entropia_tracker.db"
    if not db.exists():
        db = meipass / "entropia_tracker.db"
    URL = f"sqlite:///{db}"
else:
    BASE = Path(__file__).resolve().parent
    URL = f"sqlite:///{BASE / 'entropia_tracker.db'}"

engine = create_engine(URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def migrate_db():
    with engine.connect() as c:
        # items
        cols = {r[1] for r in c.execute(text("PRAGMA table_info(items)"))}
        for col, typ in [
            ("damage","REAL"),("dps","REAL"),("dpp","REAL"),("decay","REAL"),
            ("ammo_burn","REAL"),("notes","TEXT"),("drop_mobs","TEXT"),
            ("tt_max","REAL"),("efficiency","REAL"),("range_m","REAL"),
            ("durability","REAL"),("limited","INTEGER"),("item_type","TEXT"),
            ("item_class","TEXT")
        ]:
            if col not in cols:
                c.execute(text(f"ALTER TABLE items ADD COLUMN {col} {typ}"))
                c.commit()
        # sessions
        cols = {r[1] for r in c.execute(text("PRAGMA table_info(sessions)"))}
        if "loadout_id" not in cols:
            c.execute(text("ALTER TABLE sessions ADD COLUMN loadout_id INTEGER")); c.commit()
        if "shots" not in cols:
            c.execute(text("ALTER TABLE sessions ADD COLUMN shots INTEGER DEFAULT 0")); c.commit()
        # loadouts
        cols = {r[1] for r in c.execute(text("PRAGMA table_info(loadouts)"))}
        for col in ["armor_helmet","armor_chest","armor_arms","armor_legs","armor_feet","healing_name","amplifier_name","plating_chest","plating_arms","plating_legs"]:
            if col not in cols:
                c.execute(text(f"ALTER TABLE loadouts ADD COLUMN {col} TEXT")); c.commit()
        if "amplifier_decay" not in cols:
            c.execute(text("ALTER TABLE loadouts ADD COLUMN amplifier_decay REAL DEFAULT 0")); c.commit()
