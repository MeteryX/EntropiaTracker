"""
Chat.log Parser für Entropia Universe.
Erkennt Loot, Damage, Skills, Claims, Crafting, Globals.
"""
import re
from datetime import datetime
from pathlib import Path

class ChatParser:
    PATTERNS = {
        # Echte Muster aus chat.log
        "loot": re.compile(r"You received (.+?) x \((\d+)\) Value: ([\d.]+) PED", re.I),
        "damage": re.compile(r"You inflicted ([\d.]+) points of damage", re.I),
        "crit": re.compile(r"Critical hit.*?You inflicted ([\d.]+) points of damage", re.I),
        "took_damage": re.compile(r"You took ([\d.]+) points of damage", re.I),
        "dodge": re.compile(r"The target Dodged your attack", re.I),
        "heal": re.compile(r"You healed yourself ([\d.]+) points", re.I),
        "skill": re.compile(r"You have gained ([\d.]+) experience in your (.+?) skill", re.I),
        "global": re.compile(r"killed a creature \((.+?)\) with a value of ([\d.]+) PED", re.I),
        "hof": re.compile(r"Hall of Fame", re.I),
        "deposit": re.compile(r"found a deposit \((.+?)\) with a value of ([\d.]+) PED", re.I),
        "craft": re.compile(r"constructed an item \((.+?)\) worth ([\d.]+) PED", re.I),
    }

    @staticmethod
    def parse_line(line: str):
        line = line.strip()
        if not line:
            return None
        for etype, pat in ChatParser.PATTERNS.items():
            m = pat.search(line)
            if m:
                return {
                    "type": etype,
                    "raw": line,
                    "groups": m.groups(),
                    "time": datetime.utcnow(),
                }
        return None


def find_chat_log() -> Path | None:
    """Sucht automatisch nach chat.log."""
    candidates = [
        Path.home() / "Documents" / "Entropia Universe" / "chat.log",
        Path.home() / "Documents" / "Entropia Universe" / "Chat.log",
        Path(r"C:\Users") / Path.home().name / "Documents" / "Entropia Universe" / "chat.log",
    ]
    # Auch in typischen Steam/Standalone-Pfaden
    for base in [Path.home() / "Documents", Path("C:/")]:
        if base.exists():
            for p in base.rglob("chat.log"):
                if "entropia" in str(p).lower():
                    candidates.append(p)
                    break
    for c in candidates:
        if c.exists():
            return c
    return None
