# Entropia Tracker

Desktop-App zum Tracken von Hunting, Mining und Crafting in Entropia Universe.

## Projektstruktur

```
entropia-tracker/
├── desktop.py          # Hauptanwendung (PySide6 GUI)
├── models.py           # SQLAlchemy Datenbankmodelle
├── database.py         # DB-Verbindung und Migration
├── chat_parser.py      # Chat.log Parser (Regex)
├── decay_calc.py       # Decay-Berechnungen
├── fetch_all_items.py  # Items von Entropia Central laden
├── seed_data.py        # Beispiel-Daten
├── requirements.txt    # Python-Abhängigkeiten
├── build.bat           # EXE erstellen
└── README.md           # Diese Datei
```

## Installation (PyCharm)

1. Ordner in PyCharm öffnen: File → Open → entropia-tracker
2. Terminal öffnen und Abhängigkeiten installieren:
   ```
   pip install -r requirements.txt
   ```
3. Items laden (einmalig):
   ```
   python fetch_all_items.py
   ```
4. App starten:
   ```
   python desktop.py
   ```

## Build (EXE)

```
build.bat
```
Erstellt `dist/EntropiaTracker.exe`

## Wichtige Dateien

### desktop.py
Hauptanwendung. Enthält:
- `MainWindow`: Hauptfenster mit allen Tabs
- `LoadoutDialog`: Loadout-Erstellung
- `TradeDialog`: Trade-Erfassung
- `Overlay`: Streamer-Overlay
- `_handle_line()`: Verarbeitet Log-Zeilen
- `_update_live()`: Aktualisiert Anzeige

### chat_parser.py
Regex-Muster für Log-Erkennung:
- Loot: `You received X x (N) Value: V PED`
- Damage: `You inflicted N points of damage`
- Skill: `You have gained N experience in your SKILL skill`

### models.py
Datenbankmodelle:
- `Item`: Waffen, Rüstung, Items
- `Loadout`: Ausrüstungskonfiguration
- `Session`: Tracking-Session
- `Trade`: Handelsgeschäfte

## Einstellungen

Gespeichert in `~/.entropia_tracker_settings.json`:
- `chat_path`: Pfad zur chat.log
- `window_pos`: Fensterposition
- `window_size`: Fenstergröße
- `onboarded`: Onboarding abgeschlossen

## Einheiten

- **PED**: Project Entropia Dollar (Hauptwährung)
- **PEC**: 0.01 PED
- **Ammo-Einheiten**: 1 Einheit = 0.0001 PED
- **Decay aus API**: In PEC, wird durch 100 geteilt

## Anpassungen

### Neues Log-Muster hinzufügen
In `chat_parser.py` → `PATTERNS` Dictionary erweitern.

### UI-Texte ändern
In `desktop.py` nach den entsprechenden `setText()` oder `QLabel()` suchen.

### Kostenberechnung ändern
In `desktop.py` → `_add_weapon_cost()`, `_add_armor_cost()`, `_add_heal_cost()`
