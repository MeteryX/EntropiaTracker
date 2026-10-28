"""
Entropia Tracker - Desktop Application
======================================

Eine lokale Tracking-App für Entropia Universe.
Überwacht chat.log und berechnet Kosten/Return für Hunting, Mining, Crafting.

Struktur:
- MainWindow: Hauptfenster mit Tabs
- LoadoutDialog: Loadout erstellen/bearbeiten
- TradeDialog: Trades erfassen
- SessionDetailDialog: Session-Details anzeigen
- Overlay: Streamer-Overlay (verschiebbar)
- ChatParser: Log-Zeilen parsen (in chat_parser.py)

Datenbank: SQLite (entropia_tracker.db)
Einstellungen: ~/.entropia_tracker_settings.json

Starten:
    python desktop.py

Build:
    build.bat (erstellt EXE mit PyInstaller)
"""
import sys
import json
import threading
import time
import tailer
import logging
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QListWidget,
    QFormLayout, QDoubleSpinBox, QComboBox, QMessageBox, QDialog,
    QDialogButtonBox, QFileDialog, QTextEdit, QStatusBar, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QPainter, QPen, QColor

# Datenbank und Modelle
from database import SessionLocal, engine, Base
import models
from seed_data import seed_database
from decay_calc import armor_decay_ped, weapon_cost_per_shot
from chat_parser import ChatParser, find_chat_log

# Logging Setup
log_file = Path.home() / "entropia_tracker.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("EntropiaTracker")
log.info("App gestartet")
from database import migrate_db
migrate_db()
seed_database()

STYLE = """
QMainWindow, QWidget { background: #0f172a; color: #e2e8f0; font-family: Segoe UI; font-size: 13px; }
QTabBar::tab { background: #1e293b; color: #94a3b8; padding: 10px 20px; border-radius: 6px 6px 0 0; }
QTabBar::tab:selected { background: #334155; color: #38bdf8; }
QPushButton { background: #0ea5e9; color: white; border: none; padding: 8px 18px; border-radius: 8px; font-weight: 500; }
QPushButton:hover { background: #0284c7; }
QPushButton:disabled { background: #334155; color: #64748b; }
QLineEdit, QComboBox, QDoubleSpinBox {
    background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 8px; color: #e2e8f0;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border-color: #38bdf8; }
QListWidget { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 4px; }
QListWidget::item { padding: 6px 8px; border-radius: 4px; }
QListWidget::item:hover { background: #334155; }
QListWidget::item:selected { background: #0ea5e9; }
QLabel#title { font-size: 22px; font-weight: bold; color: #38bdf8; }
QLabel#card { background: #1e293b; border-radius: 12px; padding: 16px; border: 1px solid #334155; }
QTableWidget { background: #1e293b; border: 1px solid #334155; border-radius: 8px; gridline-color: #334155; }
QTableWidget::item { padding: 4px; }
QHeaderView::section { background: #334155; color: #94a3b8; padding: 6px; border: none; }
"""


class ItemDialog(QDialog):
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle(f"Item: {item.name}")
        self.setMinimumWidth(400)
        f = QFormLayout(self)
        self.tt = QDoubleSpinBox(); self.tt.setRange(0, 1e6); self.tt.setDecimals(4); self.tt.setValue(item.tt_value or 0)
        self.mu = QDoubleSpinBox(); self.mu.setRange(0, 10000); self.mu.setDecimals(2); self.mu.setValue(item.markup or 100)
        self.dmg = QDoubleSpinBox(); self.dmg.setRange(0, 10000); self.dmg.setValue(item.damage or 0)
        self.dpp = QDoubleSpinBox(); self.dpp.setRange(0, 1000); self.dpp.setValue(item.dpp or 0)
        self.dec = QDoubleSpinBox(); self.dec.setRange(0, 100); self.dec.setDecimals(6); self.dec.setValue(item.decay or 0)
        self.mobs = QLineEdit(); self.mobs.setText(item.drop_mobs or "")
        self.mobs.setPlaceholderText("z.B. Atrox, Argonaut")
        f.addRow("TT-Wert:", self.tt)
        f.addRow("Markup %:", self.mu)
        f.addRow("Damage:", self.dmg)
        f.addRow("DPP:", self.dpp)
        f.addRow("Decay (PED):", self.dec)
        f.addRow("Drop von Mobs:", self.mobs)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        f.addRow(btns)

    def save(self):
        self.item.tt_value = self.tt.value()
        self.item.markup = self.mu.value()
        self.item.damage = self.dmg.value()
        self.item.dpp = self.dpp.value()
        self.item.decay = self.dec.value()
        self.item.drop_mobs = self.mobs.text().strip() or None


class LoadoutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Loadout")
        self.setMinimumWidth(520)
        f = QFormLayout(self)

        self.name = QLineEdit()
        self.weapon = QComboBox()
        self.helm = QComboBox(); self.chest = QComboBox(); self.arms = QComboBox()
        self.legs = QComboBox(); self.feet = QComboBox()
        self.heal = QComboBox()
        self.amp = QComboBox()
        self.amp_dec = QDoubleSpinBox(); self.amp_dec.setRange(0, 100); self.amp_dec.setDecimals(4); self.amp_dec.setValue(0)
        self.ammo = QDoubleSpinBox(); self.ammo.setRange(0, 100000); self.ammo.setDecimals(0); self.ammo.setValue(100)
        self.ammo.setToolTip("Ammo-Einheiten pro Schuss (180 = 0.018 PED)")
        self.wdec = QDoubleSpinBox(); self.wdec.setRange(0, 100); self.wdec.setDecimals(4); self.wdec.setValue(0.05)
        self.adec = QDoubleSpinBox(); self.adec.setRange(0, 100); self.adec.setDecimals(4); self.adec.setValue(0)
        self.hdec = QDoubleSpinBox(); self.hdec.setRange(0, 100); self.hdec.setDecimals(4); self.hdec.setValue(0.01)
        self.stats = QLabel("Select weapon for stats")
        self.stats.setWordWrap(True)

        db = SessionLocal()
        items = db.query(models.Item).order_by(models.Item.name).all()
        db.close()

        self.weapon.addItem("-- Waffe --", "")
        for c in (self.helm, self.chest, self.arms, self.legs, self.feet):
            c.addItem("-- Optional --", "")
        self.heal.addItem("-- Healing --", "")

        self.amp.addItem("-- Amplifier --", "")
        for it in items:
            if it.category == "weapon":
                self.weapon.addItem(it.name, it.name)
            elif it.category == "armor":
                for c in (self.helm, self.chest, self.arms, self.legs, self.feet):
                    c.addItem(it.name, it.name)
            elif it.category == "healing":
                self.heal.addItem(it.name, it.name)
            elif it.category in ("enhancer", "tool"):
                self.amp.addItem(it.name, it.name)

        self.weapon.currentIndexChanged.connect(self._on_weapon)
        self.heal.currentIndexChanged.connect(self._on_heal)
        self.amp.currentIndexChanged.connect(self._on_amp)
        for c in (self.helm, self.chest, self.arms, self.legs, self.feet):
            c.currentIndexChanged.connect(self._on_armor)

        f.addRow("Name:", self.name)
        f.addRow("Waffe:", self.weapon)
        f.addRow("Helm:", self.helm)
        f.addRow("Brust:", self.chest)
        f.addRow("Arme:", self.arms)
        f.addRow("Beine:", self.legs)
        f.addRow("Füße:", self.feet)
        f.addRow("Healing:", self.heal)
        f.addRow("Amplifier:", self.amp)
        f.addRow("Amp Decay:", self.amp_dec)
        f.addRow(self.stats)
        f.addRow("Ammo Burn (Einheiten):", self.ammo)
        self.ammo_ped = QLabel("= 0.0000 PED/Schuss")
        self.ammo.valueChanged.connect(self._update_ammo_ped)
        f.addRow(self.ammo_ped)
        f.addRow("Weapon Decay:", self.wdec)
        f.addRow("Armor Decay/Hit:", self.adec)
        f.addRow("Heal Decay/Hit:", self.hdec)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        f.addRow(btns)

    def _update_ammo_ped(self):
        ped = self.ammo.value() * 0.0001
        self.ammo_ped.setText(f"= {ped:.4f} PED/Schuss")

    def _on_amp(self):
        name = self.amp.currentData()
        if not name:
            self.amp_dec.setValue(0)
            return
        db = SessionLocal()
        it = db.query(models.Item).filter(models.Item.name == name).first()
        db.close()
        if it and it.decay:
            # Decay aus API ist in PEC → zu PED
            val = float(it.decay) / 100.0
            self.amp_dec.setValue(val)

    def _on_heal(self):
        name = self.heal.currentData()
        if not name:
            self.hdec.setValue(0)
            return
        db = SessionLocal()
        it = db.query(models.Item).filter(models.Item.name == name).first()
        db.close()
        if it and it.decay:
            # Decay aus API ist in PEC → zu PED
            val = float(it.decay) / 100.0
            self.hdec.setValue(val)

    def _on_weapon(self):
        name = self.weapon.currentData()
        if not name:
            self.stats.setText("No weapon")
            return
        db = SessionLocal()
        it = db.query(models.Item).filter(models.Item.name == name).first()
        db.close()
        if it:
            decay = float(it.decay) / 100.0 if it.decay else 0
            self.stats.setText(
                f"Damage: {it.damage or '-'} | DPP: {it.dpp or '-'}\n"
                f"TT: {it.tt_value:.2f} | Decay: {decay:.4f} PED | Ammo: {it.ammo_burn or '-'}"
            )
            if decay:
                self.wdec.setValue(decay)
            if it.ammo_burn is not None:
                self.ammo.setValue(float(it.ammo_burn))
        else:
            self.stats.setText("No stats in database")

    def _on_armor(self):
        # Armor Decay nur wenn mindestens ein Teil gewählt
        has_armor = any(c.currentData() for c in (self.helm, self.chest, self.arms, self.legs, self.feet))
        if not has_armor:
            self.adec.setValue(0)
        elif self.adec.value() == 0:
            self.adec.setValue(0.02)

    def data(self):
        return {
            "name": self.name.text().strip(),
            "weapon_name": self.weapon.currentData() or "",
            "armor_helmet": self.helm.currentData() or "",
            "armor_chest": self.chest.currentData() or "",
            "armor_arms": self.arms.currentData() or "",
            "armor_legs": self.legs.currentData() or "",
            "armor_feet": self.feet.currentData() or "",
            "healing_name": self.heal.currentData() or "",
            "amplifier_name": self.amp.currentData() or "",
            "amplifier_decay": self.amp_dec.value(),
            "ammo_burn": self.ammo.value(),
            "weapon_decay": self.wdec.value(),
            "armor_decay_per_hit": self.adec.value(),
            "healing_decay_per_hit": self.hdec.value(),
        }


class TradeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Trade")
        self.setMinimumWidth(440)
        f = QFormLayout(self)
        self.name = QLineEdit()
        self.item = QLineEdit()
        self.qty = QDoubleSpinBox(); self.qty.setRange(1, 100000); self.qty.setValue(1)
        self.tt = QDoubleSpinBox(); self.tt.setRange(0, 1e6); self.tt.setDecimals(2)
        self.buy = QDoubleSpinBox(); self.buy.setRange(0, 1000); self.buy.setValue(103)
        self.sell = QDoubleSpinBox(); self.sell.setRange(0, 1000); self.sell.setValue(104)
        self.profit = QLabel("Gewinn: -")
        f.addRow("Name:", self.name)
        f.addRow("Item:", self.item)
        f.addRow("Menge:", self.qty)
        f.addRow("TT:", self.tt)
        f.addRow("Kauf-MU %:", self.buy)
        f.addRow("Verkauf-MU %:", self.sell)
        f.addRow(self.profit)
        for w in (self.qty, self.tt, self.buy, self.sell):
            w.valueChanged.connect(self._calc)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        f.addRow(btns)
        self._calc()

    def _calc(self):
        c = self.tt.value() * self.qty.value() * self.buy.value() / 100
        r = self.tt.value() * self.qty.value() * self.sell.value() / 100
        self.profit.setText(f"Kosten {c:.2f} | Erlös {r:.2f} | Gewinn {r-c:.2f} PED")

    def data(self):
        return {
            "name": self.name.text().strip() or "Trade",
            "notes": f"{self.item.text()} x{int(self.qty.value())}",
            "items": [{"name": self.item.text(), "qty": self.qty.value(),
                       "tt": self.tt.value(), "buy_mu": self.buy.value(), "sell_mu": self.sell.value()}],
            "status": "open",
        }

    def _calc(self):
        c = self.tt.value() * self.qty.value() * self.buy.value() / 100
        r = self.tt.value() * self.qty.value() * self.sell.value() / 100
        self.profit.setText(f"Kosten {c:.2f} | Erlös {r:.2f} | Gewinn {r-c:.2f} PED")

    def data(self):
        return {
            "name": self.name.text().strip() or "Trade",
            "notes": f"{self.item.text()} x{int(self.qty.value())}",
            "items": [{"name": self.item.text(), "qty": self.qty.value(),
                       "tt": self.tt.value(), "buy_mu": self.buy.value(), "sell_mu": self.sell.value()}],
            "status": "open",
        }


class SessionDetailDialog(QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Session: {session.name}")
        self.setMinimumSize(520, 480)
        lay = QVBoxLayout(self)

        # Kopf
        head = QLabel(
            f"<b>{session.type.upper()}</b> – {session.name}<br>"
            f"Start: {session.start_time.strftime('%Y-%m-%d %H:%M') if session.start_time else '-'}<br>"
            f"Ende: {session.end_time.strftime('%Y-%m-%d %H:%M') if session.end_time else 'läuft'}"
        )
        head.setTextFormat(Qt.RichText)
        lay.addWidget(head)

        # Zahlen
        cost = session.total_cost_tt or 0
        ret = session.total_return_tt or 0
        ret_mu = session.total_return_mu or 0
        pct = (ret / cost * 100) if cost else 0
        profit = ret_mu - cost
        color = "#22c55e" if profit >= 0 else "#ef4444"
        stats = QLabel(
            f"Kosten: {cost:.4f} PED\n"
            f"Return TT: {ret:.4f}\n"
            f"Return MU: {ret_mu:.4f}\n"
            f"Return: {pct:.1f}%\n"
            f"Gewinn: {profit:+.2f} PED\n"
            f"Schüsse: {session.shots or 0}"
        )
        stats.setStyleSheet(f"font-size: 14px; padding: 10px; border: 2px solid {color}; border-radius: 8px;")
        lay.addWidget(stats)

        data = session.data or {}

        # Loot
        lay.addWidget(QLabel("<b>Loot</b>"))
        loot_list = QListWidget()
        for item in data.get("loot", []):
            loot_list.addItem(f"{item.get('name','?')} x{item.get('qty',1)}  TT:{item.get('tt',0):.4f}")
        if not data.get("loot"):
            loot_list.addItem("(keine Daten)")
        lay.addWidget(loot_list)

        # Skills
        lay.addWidget(QLabel("<b>Skills</b>"))
        skill_list = QListWidget()
        skills = data.get("skills", {})
        for name, val in sorted(skills.items(), key=lambda x: -x[1]):
            skill_list.addItem(f"{name}: +{val:.2f}")
        if not skills:
            skill_list.addItem("(keine Daten)")
        lay.addWidget(skill_list)

        # Claims (Mining)
        if data.get("claims"):
            lay.addWidget(QLabel("<b>Claims</b>"))
            cl = QListWidget()
            for c in data["claims"]:
                cl.addItem(str(c))
            lay.addWidget(cl)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(260, 130)
        self._drag_pos = None
        lay = QVBoxLayout(self)
        self.lbl = QLabel("Keine Session")
        self.lbl.setStyleSheet("background: rgba(15,23,42,220); color: #e2e8f0; padding: 12px; border-radius: 8px;")
        lay.addWidget(self.lbl)

    def set_text(self, t):
        self.lbl.setText(t)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None


class ReturnChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = []
        self.setMinimumHeight(100)

    def add_point(self, pct):
        self.points.append(float(pct))
        if len(self.points) > 80:
            self.points = self.points[-80:]
        self.update()

    def paintEvent(self, e):
        if len(self.points) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#1e293b"))
        p.setPen(QPen(QColor("#38bdf8"), 2))
        mx, mn = max(self.points), min(self.points)
        rng = (mx - mn) or 1
        for i in range(1, len(self.points)):
            x1 = int((i-1) / (len(self.points)-1) * (w-10)) + 5
            y1 = int(h - 8 - (self.points[i-1] - mn) / rng * (h-16))
            x2 = int(i / (len(self.points)-1) * (w-10)) + 5
            y2 = int(h - 8 - (self.points[i] - mn) / rng * (h-16))
            p.drawLine(x1, y1, x2, y2)
        p.end()


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.lbl = QLabel("Overlay")
        self.lbl.setStyleSheet("""
            background: rgba(15,23,42,230);
            color: #e2e8f0;
            border-radius: 8px;
            padding: 10px;
            font-family: Consolas, monospace;
            font-size: 12px;
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.lbl)
        self.resize(320, 100)

    def set_data(self, loots, maxl, cost, ret, mu, profit_tt, profit_mu, pct, shrap, anteil, wpn, arm, heal):
        color = "#22c55e" if profit_mu >= 0 else "#ef4444"
        self.lbl.setStyleSheet(f"""
            background: rgba(15,23,42,230);
            color: #e2e8f0;
            border: 2px solid {color};
            border-radius: 8px;
            padding: 10px;
            font-family: Consolas, monospace;
            font-size: 12px;
        """)
        txt = (
            f"Loots: {loots} | Max: {maxl:.4f}\n"
            f"Cost: {cost:.4f} | Ret: {ret:.4f} (Shrap: {shrap:.4f} / {anteil:.0f}%)\n"
            f"MU: {mu:.4f} | Profit: {profit_tt:+.4f} / MU: {profit_mu:+.4f}\n"
            f"Wpn: {wpn:.4f} | Arm: {arm:.4f} | Heal: {heal:.4f}"
        )
        self.lbl.setText(txt)

    def set_text(self, t):
        self.lbl.setText(t)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if hasattr(self, "_drag") and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)


class LogSignals(QObject):
    line = Signal(str)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Entropia Tracker")
        self.resize(1080, 680)
        self.setStyleSheet(STYLE)
        self.overlays = []
        self.overlay = Overlay()
        self.return_history = []
        self.chat_path = None
        self.watching = False
        self.settings_file = Path.home() / ".entropia_tracker_settings.json"
        self.settings = self._load_settings()
        if self.settings.get("chat_path"):
            p = Path(self.settings["chat_path"])
            if p.exists():
                self.chat_path = p
        self.signals = LogSignals()
        self.signals.line.connect(self._handle_line)
        self.lines_received = 0
        self.lines_parsed = 0
        self.session_loot = []
        self.session_loot_count = 0
        self.session_cost = 0.0
        self.session_return_tt = 0.0
        self.session_return_mu = 0.0

        c = QWidget(); self.setCentralWidget(c)
        lay = QVBoxLayout(c)
        t = QLabel("Entropia Tracker"); t.setObjectName("title"); lay.addWidget(t)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self.tabs.addTab(self._hunt(), "Hunting")
        self.tabs.addTab(self._mine(), "Mining")
        self.tabs.addTab(self._craft(), "Crafting")
        self.tabs.addTab(self._loadouts(), "Loadouts")
        self.tabs.addTab(self._sessions(), "Sessions")
        self.tabs.addTab(self._globals(), "Globals/HOF")
        self.tabs.addTab(self._trades(), "Trading")
        self.tabs.addTab(self._items(), "Items")
        # Statusbar
        self.statusBar().showMessage("Ready")
        self.refresh()
        # Fensterposition wiederherstellen
        if self.settings.get("window_pos"):
            self.move(*self.settings["window_pos"])
        if self.settings.get("window_size"):
            self.resize(*self.settings["window_size"])
        # Onboarding
        if not self.settings.get("onboarded"):
            self._show_onboarding()
        # Gespeicherten Log-Pfad automatisch verbinden
        if self.chat_path and self.chat_path.exists():
            self.log_status.setText(f"Log: {self.chat_path.name}")
            self.log_status.setStyleSheet("color: #22c55e; font-size: 12px;")
            self.start_watching()

    def _show_onboarding(self):
        QMessageBox.information(self, "Welcome",
            "Welcome to Entropia Tracker!\n\n"
            "1. Select your chat.log (Chat.log button)\n"
            "2. Create a Loadout (Loadouts tab)\n"
            "3. Start a session (Start button)\n\n"
            "The log path will be remembered.")
        self.settings["onboarded"] = True
        self._save_settings()

    def closeEvent(self, e):
        # Fensterposition speichern
        self.settings["window_pos"] = [self.x(), self.y()]
        self.settings["window_size"] = [self.width(), self.height()]
        self._save_settings()
        # Backup
        self._backup_db()
        e.accept()

    def _backup_db(self):
        try:
            import shutil
            from datetime import datetime
            src = Path(__file__).parent / "entropia_tracker.db"
            if src.exists():
                backup_dir = Path.home() / ".entropia_tracker_backups"
                backup_dir.mkdir(exist_ok=True)
                dst = backup_dir / f"backup_{datetime.now().strftime('%Y%m%d')}.db"
                if not dst.exists():
                    shutil.copy(src, dst)
        except Exception as e:
            log.error(f"Fehler: {e}")

    def _hunt(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self.hunt_lbl = QLabel("Keine Session")
        self.hunt_lbl.setObjectName("card")
        self.hunt_lbl.setStyleSheet("font-size: 15px; padding: 16px; border: 2px solid #334155; border-radius: 10px;")
        lay.addWidget(self.hunt_lbl)

        # Loadout-Auswahl
        lo_row = QHBoxLayout()
        lo_row.addWidget(QLabel("Loadout:"))
        self.lo_combo = QComboBox()
        self.lo_combo.currentIndexChanged.connect(self._on_loadout_selected)
        lo_row.addWidget(self.lo_combo)
        lay.addLayout(lo_row)

        # Loot-Tabelle
        lay.addWidget(QLabel("Loot dieser Session:"))
        self.loot_list = QListWidget()
        self.loot_list.setMaximumHeight(120)
        lay.addWidget(QLabel("Loot:"))
        lay.addWidget(self.loot_list)
        self.skill_list = QListWidget()
        self.skill_list.setMaximumHeight(70)
        lay.addWidget(QLabel("Skills:"))
        lay.addWidget(self.skill_list)
        # Graph
        lay.addWidget(QLabel("Return-Verlauf:"))
        self.chart = ReturnChart()
        lay.addWidget(self.chart)
        row = QHBoxLayout()
        self.btn_start = QPushButton("Start"); self.btn_start.setToolTip("Start a new hunting session")
        self.btn_stop = QPushButton("Stop"); self.btn_stop.setEnabled(False); self.btn_stop.setToolTip("End current session")
        self.btn_start.clicked.connect(self.start_hunt)
        self.btn_stop.clicked.connect(self.stop_hunt)
        row.addWidget(self.btn_start); row.addWidget(self.btn_stop)
        b1 = QPushButton("Overlay"); b1.setToolTip("Toggle streamer overlay"); b1.clicked.connect(self.toggle_ov); row.addWidget(b1)
        b2 = QPushButton("Chat.log"); b2.setToolTip("Select chat.log file"); b2.clicked.connect(self.pick_log); row.addWidget(b2)
        b3 = QPushButton("Export"); b3.setToolTip("Export session to CSV"); b3.clicked.connect(self.export_csv); row.addWidget(b3)
        self.log_status = QLabel("Log: nicht verbunden")
        self.log_status.setStyleSheet("color: #94a3b8; font-size: 12px;")
        lay.addWidget(self.log_status)
        self.debug_lbl = QLabel("Zeilen: 0 | Erkannt: 0")
        self.debug_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        lay.addWidget(self.debug_lbl)
        lay.addLayout(row); lay.addStretch(); return w

    def start_hunt(self):
        if not self.active_loadout:
            QMessageBox.warning(self, "Loadout", "Bitte zuerst ein Loadout auswählen.")
            return
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.session_loot = []
        self.session_loot_count = 0
        self._last_loot_time = None
        self.session_shots = 0
        self.session_kills = 0
        self.session_max_loot = 0.0
        self.session_weapon_decay = 0.0
        self.session_armor_decay = 0.0
        self.session_heal_decay = 0.0
        self.session_armor_cost = 0.0
        self.session_heal_cost = 0.0
        self.session_damage = 0.0
        self.session_cost = 0.0
        self.session_return_tt = 0.0
        self.session_return_mu = 0.0
        self.session_shrapnel = 0.0
        self.session_skills = {}
        self.skill_list.clear()
        self.loot_list.clear()
        db = SessionLocal()
        s = models.Session(
            type="hunting",
            name=f"Hunt {self.active_loadout.name}",
            loadout_id=self.active_loadout.id
        )
        db.add(s)
        db.commit()
        self.current_session_id = s.id
        db.close()
        self._update_live()
        # Watcher sicherstellen
        if self.chat_path:
            if not self.watching:
                self.start_watching()
            else:
                log.debug("Watcher läuft bereits")

    def stop_hunt(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if self.current_session_id:
            from datetime import datetime
            db = SessionLocal()
            s = db.query(models.Session).get(self.current_session_id)
            if s:
                s.end_time = datetime.utcnow()
                s.total_cost_tt = self.session_cost
                s.total_return_tt = self.session_return_tt
                s.total_cost_mu = self.session_cost
                s.total_return_mu = self.session_return_mu
                s.shots = self.session_shots
                s.data = {"skills": self.session_skills, "loot": self.session_loot}
                db.commit()
            db.close()
            log.info(f"Session beendet: Cost={self.session_cost:.4f}, Return={self.session_return_tt:.4f}")
            self.current_session_id = None
        self.mining_cost = 0.0
        self.mine_drops = 0
        self.mine_claims_count = 0
        self.craft_attempts = 0
        self.craft_success = 0
        self.craft_cost = 0.0
        self.craft_return = 0.0
        self.settings_file = Path.home() / ".entropia_tracker_settings.json"
        self.settings = self._load_settings()
        if self.settings.get("chat_path"):
            p = Path(self.settings["chat_path"])
            if p.exists():
                self.chat_path = p
        self.hunt_lbl.setText("Session beendet.")
        self.hunt_lbl.setStyleSheet("font-size: 15px; padding: 16px; border: 2px solid #334155; border-radius: 10px;")
        self.overlay.set_text("Session beendet.")
        self._r_se()

    def toggle_ov(self):
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show()
            self.overlay.set_text(self.hunt_lbl.text())
            # Tracking starten auch ohne Session
            if self.chat_path and not self.watching:
                self.start_watching()
            if not hasattr(self, "session_loot"):
                self.session_loot = []
                self.session_loot_count = 0
                self.session_cost = 0.0
                self.session_return_tt = 0.0
                self.session_return_mu = 0.0

    def auto_find_log(self):
        p = find_chat_log()
        if p:
            self.chat_path = p
            QMessageBox.information(self, "Chat.log", f"Gefunden:\n{p}")
            self.start_watching()
        else:
            QMessageBox.warning(self, "Chat.log", "Nicht automatisch gefunden.\nBitte manuell wählen.")

    def pick_log(self):
        p, _ = QFileDialog.getOpenFileName(self, "Chat.log", "", "Log (*.log *.txt)")
        if not p:
            return
        self.chat_path = Path(p)
        self.settings["chat_path"] = str(p)
        self._save_settings()
        self.watching = False
        self.log_status.setText(f"Log: {self.chat_path.name}")
        self.log_status.setStyleSheet("color: #22c55e; font-size: 12px;")
        QMessageBox.information(self, "Chat.log", f"Verbunden:\n{p}")
        self.start_watching()

    def start_watching(self):
        if not self.chat_path:
            self.log_status.setText("Log: kein Pfad")
            return
        if not self.chat_path.exists():
            self.log_status.setText("Log: Datei nicht gefunden")
            self.log_status.setStyleSheet("color: #ef4444; font-size: 12px;")
            return
        if self.watching:
            return
        self.watching = True
        self.log_status.setText(f"Log: verbunden ({self.chat_path.name})")
        self.log_status.setStyleSheet("color: #22c55e; font-size: 12px;")
        threading.Thread(target=self._watch_loop, daemon=True).start()

    def _watch_loop(self):
        """Liest neue Zeilen mit tailer.follow (wie LootNanny)."""
        try:
            with open(self.chat_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                # Zum Ende springen
                f.seek(0, 2)
                for line in tailer.follow(f, delay=0.05):
                    if not self.watching:
                        break
                    self.signals.line.emit(line.strip())
        except Exception as e:
            self.signals.line.emit(f"[ERROR] {e}")
            self.watching = False  # Bei Fehler neu starten erlauben
            log.error(f"Watcher Fehler: {e}")

    def _handle_line(self, line):
        self.lines_received += 1
        if hasattr(self, "debug_lbl"):
            self.debug_lbl.setText(f"Zeilen: {self.lines_received} | Erkannt: {self.lines_parsed}")
        if line.startswith("[ERROR]"):
            return
        ev = ChatParser.parse_line(line)
        if not ev:
            return
        self.lines_parsed += 1
        if hasattr(self, "debug_lbl"):
            self.debug_lbl.setText(f"Zeilen: {self.lines_received} | Erkannt: {self.lines_parsed}")
        if not hasattr(self, "session_loot"):
            return
        if ev["type"] == "loot":
            name, qty, val = ev["groups"]
            # Komplett ignorieren?
            if self._is_ignored_track(name):
                return
            qty = int(qty)
            log_val = float(val)
            db = SessionLocal()
            it = db.query(models.Item).filter(models.Item.name == name).first()
            mu = (it.markup if it else 100.0)
            # Log-Wert ist Gesamt-TT, nicht pro Stück
            if log_val > 0:
                tt_total = log_val
                tt = log_val / qty if qty else log_val
            elif it and it.tt_value:
                tt = it.tt_value
                tt_total = tt * qty
            else:
                tt = 0.0
                tt_total = 0.0
            db.close()
            self.session_loot.append({"name": name, "qty": qty, "tt": tt, "time": ev.get("time")})
            # Loot-Counter: nur zählen wenn nicht ignoriert
            if not self._is_ignored_loot(name):
                now = datetime.utcnow()
                last_loot_time = getattr(self, "_last_loot_time", None)
                if not last_loot_time or (now - last_loot_time).total_seconds() > 2:
                    self.session_loot_count = getattr(self, "session_loot_count", 0) + 1
                self._last_loot_time = now
            self.session_return_tt += tt_total
            self.session_return_mu += tt_total * (mu / 100.0)
            # Shrapnel separat tracken
            if "shrapnel" in name.lower():
                self.session_shrapnel = getattr(self, "session_shrapnel", 0) + tt_total
            if tt_total > getattr(self, "session_max_loot", 0):
                self.session_max_loot = tt_total
            log.debug(f"Loot: {name} x{qty} = {tt_total:.4f} PED")
            self._update_live()
        elif ev["type"] == "damage":
            self.session_shots += 1
            self._add_weapon_cost()
            self._update_live()
        elif ev["type"] == "skill":
            amount = float(ev["groups"][0])
            skill = ev["groups"][1].strip()
            self.session_skills[skill] = self.session_skills.get(skill, 0) + amount
            self._refresh_skills()
            self._update_live()
        elif ev["type"] == "took_damage":
            dmg = float(ev["groups"][0]) if ev["groups"] else 0
            if self.active_loadout and self.active_loadout.armor_decay_per_hit:
                self._add_armor_cost()
            self._update_live()
        elif ev["type"] == "claim":
            self.mine_claims_count += 1
            self.mine_drops += 1
            res = ev["groups"][0].strip() if ev["groups"] else "Resource"
            self.mining_claims.append(res)
            db = SessionLocal()
            it = db.query(models.Item).filter(models.Item.name.ilike(f"%{res}%")).first()
            if it:
                self.mining_return += it.tt_value or 0
            db.close()
            self.mine_list.addItem(f"Claim: {res}")
            self._update_mine()
        elif ev["type"] == "no_resource":
            self.mine_drops += 1
            probe_cost = 0.01
            if self.active_loadout:
                probe_cost = getattr(self.active_loadout, "ammo_burn", 0.01) or 0.01
            self.mining_cost += probe_cost
            self._update_mine()
        elif ev["type"] == "craft":
            item_name = ev["groups"][0] if ev["groups"] else "Item"
            val = float(ev["groups"][1]) if len(ev["groups"]) > 1 else 0
            self.craft_attempts += 1
            self.craft_success += 1
            self.craft_return += val
            # Materialkosten schätzen (Output * 0.8 als grobe Annahme)
            est_cost = val * 0.8
            self.craft_cost += est_cost
            self.craft_list.addItem(f"Craft: {item_name} ({val:.2f} PED)")
            self.mat_lbl.setText(f"Geschätzte Materialkosten: {self.craft_cost:.2f} PED")
            self._update_craft()
        elif ev["type"] == "craft_fail":
            self.craft_attempts += 1
            self.craft_cost += 0.5
            self.craft_list.addItem("Fail")
            self._update_craft()
        elif ev["type"] == "global":
            self._handle_global(ev, is_hof=False)
        elif ev["type"] == "hof":
            self._handle_global(ev, is_hof=True)

    def _handle_global(self, ev, is_hof=False):
        """Verarbeitet Global/HOF Events und macht Screenshot bei Schwellenwert."""
        try:
            if is_hof:
                value = 0
                name = "HOF"
            else:
                name = ev["groups"][0] if ev["groups"] else "Unknown"
                value = float(ev["groups"][1]) if len(ev["groups"]) > 1 else 0
            threshold = self.settings.get("screenshot_threshold", 0)
            if value >= threshold or is_hof:
                self._take_screenshot(name, value, is_hof)
            if hasattr(self, "global_list"):
                prefix = "HOF" if is_hof else "Global"
                self.global_list.addItem(f"{prefix}: {name} ({value:.0f} PED)")
        except Exception as e:
            log.error(f"Fehler: {e}")

    def _take_screenshot(self, name, value, is_hof):
        """Macht einen Screenshot und speichert ihn."""
        try:
            from datetime import datetime
            import subprocess
            folder = Path.home() / "Documents" / "Globals"
            folder.mkdir(parents=True, exist_ok=True)
            prefix = "HOF" if is_hof else "Global"
            filename = f"{prefix}_{name}_{value:.0f}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            path = folder / filename
            # Windows Screenshot ohne Konsolenfenster
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            subprocess.run([
                "powershell", "-WindowStyle", "Hidden", "-Command",
                f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Screen]::PrimaryScreen | Out-Null; $bmp = New-Object System.Drawing.Bitmap([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); $g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size); $bmp.Save('{path}')"
            ], capture_output=True, timeout=5, startupinfo=startupinfo)
        except Exception as e:
            log.error(f"Fehler: {e}")

    def _globals(self):
        w = QWidget(); lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Globals & Hall of Fame"))
        # Player Name
        row0 = QHBoxLayout()
        row0.addWidget(QLabel("Player Name:"))
        self.player_name = QLineEdit()
        self.player_name.setPlaceholderText("Dein Avatar-Name für Global-Filter")
        self.player_name.setText(self.settings.get("player_name", ""))
        self.player_name.textChanged.connect(lambda t: self._save_setting("player_name", t))
        row0.addWidget(self.player_name)
        lay.addLayout(row0)
        # Threshold
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Screenshot ab (PED):"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0, 100000)
        self.threshold_spin.setValue(self.settings.get("screenshot_threshold", 50))
        self.threshold_spin.valueChanged.connect(self._save_threshold)
        row1.addWidget(self.threshold_spin)
        lay.addLayout(row1)
        # Folder selection
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Speicherort:"))
        self.screenshot_folder = QLineEdit()
        self.screenshot_folder.setText(self.settings.get("screenshot_folder", str(Path.home() / "Documents" / "Globals")))
        self.screenshot_folder.setReadOnly(True)
        row2.addWidget(self.screenshot_folder)
        b_folder = QPushButton("Ordner wählen")
        b_folder.clicked.connect(self._pick_screenshot_folder)
        row2.addWidget(b_folder)
        lay.addLayout(row2)
        # Ignore-Listen Einstellungen
        row3 = QHBoxLayout()
        self.ignore_loot_check = QCheckBox("Loot-Counter Ignore aktiv")
        self.ignore_loot_check.setChecked(self.settings.get("ignore_loot_enabled", False))
        self.ignore_loot_check.stateChanged.connect(self._save_ignore_settings)
        row3.addWidget(self.ignore_loot_check)
        lay.addLayout(row3)
        self.ignore_loot_list = QLineEdit()
        self.ignore_loot_list.setPlaceholderText("Items für Loot-Counter ignorieren (kommagetrennt)")
        self.ignore_loot_list.setText(self.settings.get("ignore_loot_items", ""))
        self.ignore_loot_list.textChanged.connect(self._save_ignore_settings)
        lay.addWidget(self.ignore_loot_list)
        row4 = QHBoxLayout()
        self.ignore_track_check = QCheckBox("Tracker Ignore aktiv")
        self.ignore_track_check.setChecked(self.settings.get("ignore_track_enabled", False))
        self.ignore_track_check.stateChanged.connect(self._save_ignore_settings)
        row4.addWidget(self.ignore_track_check)
        lay.addLayout(row4)
        self.ignore_track_list = QLineEdit()
        self.ignore_track_list.setPlaceholderText("Items komplett ignorieren (kommagetrennt)")
        self.ignore_track_list.setText(self.settings.get("ignore_track_items", ""))
        self.ignore_track_list.textChanged.connect(self._save_ignore_settings)
        lay.addWidget(self.ignore_track_list)
        # List
        self.global_list = QListWidget()
        lay.addWidget(self.global_list)
        return w

    def _pick_screenshot_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Screenshot-Ordner", self.screenshot_folder.text())
        if folder:
            self.screenshot_folder.setText(folder)
            self.settings["screenshot_folder"] = folder
            self._save_settings()

    def _save_ignore_settings(self):
        self.settings["ignore_loot_enabled"] = self.ignore_loot_check.isChecked()
        self.settings["ignore_loot_items"] = self.ignore_loot_list.text()
        self.settings["ignore_track_enabled"] = self.ignore_track_check.isChecked()
        self.settings["ignore_track_items"] = self.ignore_track_list.text()
        self._save_settings()

    def _save_setting(self, key, value):
        """Speichert eine einzelne Einstellung."""
        self.settings[key] = value
        self._save_settings()

    def _is_ignored_loot(self, name):
        if not self.settings.get("ignore_loot_enabled"):
            return False
        items = [i.strip().lower() for i in self.settings.get("ignore_loot_items", "").split(",") if i.strip()]
        return name.lower() in items

    def _is_ignored_track(self, name):
        if not self.settings.get("ignore_track_enabled"):
            return False
        items = [i.strip().lower() for i in self.settings.get("ignore_track_items", "").split(",") if i.strip()]
        return name.lower() in items

    def _save_threshold(self, val):
        self.settings["screenshot_threshold"] = val
        self._save_settings()

    def _refresh_skills(self):
        # Alle Skill-Listen aktualisieren
        for lst in [getattr(self, "skill_list", None),
                    getattr(self, "mine_skill_list", None),
                    getattr(self, "craft_skill_list", None)]:
            if lst is None:
                continue
            lst.clear()
            for name, total in sorted(self.session_skills.items(), key=lambda x: -x[1]):
                lst.addItem(f"{name}: +{total:.2f}")

    def _add_weapon_cost(self):
        if not self.active_loadout:
            return
        lo = self.active_loadout
        # Ammo in Einheiten, 1 Einheit = 0.0001 PED
        ammo_cost = (lo.ammo_burn or 0) * 0.0001
        decay_cost = lo.weapon_decay or 0
        self.session_cost += ammo_cost + decay_cost
        self.session_weapon_decay = getattr(self, "session_weapon_decay", 0) + decay_cost

    def _add_armor_cost(self):
        if not self.active_loadout:
            return
        c = self.active_loadout.armor_decay_per_hit or 0
        self.session_cost += c
        self.session_armor_cost += c

    def _add_heal_cost(self):
        if not self.active_loadout:
            return
        c = self.active_loadout.healing_decay_per_hit or 0
        self.session_cost += c
        self.session_heal_cost += c

    def _update_live(self):
        try:
            cost = self.session_cost
            ret_tt = self.session_return_tt
            ret_mu = self.session_return_mu
            shrap = getattr(self, "session_shrapnel", 0)
            pct = (ret_tt / cost * 100) if cost > 0 else 0
            profit = ret_mu - cost
            profit_ns = (ret_mu - shrap) - cost
            pct_ns = ((ret_tt - shrap) / cost * 100) if cost > 0 else 0
            color = "#22c55e" if profit >= 0 else "#ef4444"
            wpn = getattr(self, "session_weapon_decay", 0)
            arm = getattr(self, "session_armor_cost", 0)
            heal = getattr(self, "session_heal_cost", 0)
            loots = getattr(self, "session_loot_count", 0)
            maxl = getattr(self, "session_max_loot", 0)
            txt = (
                f"{'Loots: ' + str(loots):<14}{'Cost: ' + f'{cost:.4f}':<16}{'Shrap: ' + f'{shrap:.4f}':<16}{'Wpn: ' + f'{wpn:.4f}'}\n"
                f"{'Max: ' + f'{maxl:.4f}':<14}{'Ret: ' + f'{ret_tt:.4f}':<16}{'Anteil: ' + f'{(shrap/ret_tt*100) if ret_tt else 0:.0f}%':<16}{'Arm: ' + f'{arm:.4f}'}\n"
                f"{'':<14}{'MU: ' + f'{ret_mu:.4f}':<16}{'ProfNS: ' + f'{profit_ns:+.4f}':<16}{'Heal: ' + f'{heal:.4f}'}\n"
                f"{'':<14}{'Profit: ' + f'{profit:+.4f}':<16}{'RetNS: ' + f'{pct_ns:.1f}%':<16}"
            )
            self.hunt_lbl.setText(txt)
            self.hunt_lbl.setStyleSheet(f"font-size: 14px; padding: 12px; border: 3px solid {color}; border-radius: 10px;")
            profit_tt = ret_tt - cost
            profit_mu = ret_mu - cost
            self.overlay.set_data(loots, maxl, cost, ret_tt, ret_mu, profit_tt, profit_mu, pct, shrap,
                                   (shrap/ret_tt*100) if ret_tt else 0, wpn, arm, heal)
            if hasattr(self, "chart"):
                self.chart.add_point(pct)
        except Exception as e:
            self.hunt_lbl.setText(f"Update-Fehler: {e}")

    def export_csv(self):
        if not self.session_loot:
            QMessageBox.information(self, "Export", "Keine Loot-Daten in dieser Session.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export", "session.csv", "CSV (*.csv)")
        if path:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Item", "Qty", "TT"])
                for l in self.session_loot:
                    w.writerow([l["name"], l["qty"], l["tt"]])
            QMessageBox.information(self, "Export", f"Gespeichert:\n{path}")

    def _mine(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self.mine_lbl = QLabel("Keine Mining-Session")
        self.mine_lbl.setObjectName("card")
        self.mine_lbl.setStyleSheet("font-size: 15px; padding: 16px; border: 2px solid #334155; border-radius: 10px;")
        lay.addWidget(self.mine_lbl)
        self.mine_list = QListWidget(); self.mine_list.setMaximumHeight(120)
        lay.addWidget(QLabel("Claims:")); lay.addWidget(self.mine_list)
        self.mine_skill_list = QListWidget(); self.mine_skill_list.setMaximumHeight(80)
        lay.addWidget(QLabel("Skills:")); lay.addWidget(self.mine_skill_list)
        row = QHBoxLayout()
        b1 = QPushButton("Mining starten"); b1.clicked.connect(self.start_mine)
        b2 = QPushButton("Mining beenden"); b2.clicked.connect(self.stop_mine)
        row.addWidget(b1); row.addWidget(b2)
        lay.addLayout(row); lay.addStretch(); return w

    def start_mine(self):
        self.mining_claims = []; self.mining_cost = 0.0; self.mining_return = 0.0
        self.session_skills = {}
        self.mine_list.clear()
        self.mine_skill_list.clear()
        self._add_session("mining")
        self._update_mine()
        if self.chat_path and not self.watching: self.start_watching()

    def _export_session_csv(self):
        """Speichert Session automatisch in Sessions.csv"""
        try:
            import csv
            from datetime import datetime
            path = Path.home() / "Sessions.csv"
            exists = path.exists()
            with open(path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if not exists:
                    w.writerow(["Date", "Type", "Name", "Cost", "Return_TT", "Return_MU", "Profit", "Loots", "Shots"])
                profit = self.session_return_mu - self.session_cost
                w.writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "hunting",
                    f"Hunt {self.active_loadout.name}" if self.active_loadout else "Hunt",
                    f"{self.session_cost:.4f}",
                    f"{self.session_return_tt:.4f}",
                    f"{self.session_return_mu:.4f}",
                    f"{profit:.4f}",
                    self.session_loot_count,
                    self.session_shots
                ])
        except Exception as e:
            log.error(f"Fehler: {e}")

    def stop_mine(self):
        if self.current_session_id:
            from datetime import datetime
            db = SessionLocal()
            s = db.query(models.Session).get(self.current_session_id)
            if s:
                s.end_time = datetime.utcnow()
                s.data = {"skills": self.session_skills, "claims": self.mining_claims}
                db.commit()
            db.close()
            self.current_session_id = None
        self.mine_lbl.setText("Mining beendet.")
        self._r_se()

    def _update_mine(self):
        pct = (self.mining_return / self.mining_cost * 100) if self.mining_cost else 0
        profit = self.mining_return - self.mining_cost
        find_rate = (self.mine_claims_count / self.mine_drops * 100) if self.mine_drops else 0
        dud_rate = 100 - find_rate if self.mine_drops else 0
        color = "#22c55e" if profit >= 0 else "#ef4444"
        self.mine_lbl.setText(
            f"Cost: {self.mining_cost:.4f} PED | Return: {self.mining_return:.4f} PED\n"
            f"Profit: {profit:+.4f} PED | Return: {pct:.1f}%\n"
            f"Find-Rate: {find_rate:.0f}% | Dud: {dud_rate:.0f}%\n"
            f"Claims: {self.mine_claims_count} | Drops: {self.mine_drops}"
        )
        self.mine_lbl.setStyleSheet(f"font-size: 14px; padding: 12px; border: 3px solid {color}; border-radius: 10px;")

    def _craft(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self.craft_lbl = QLabel("Keine Crafting-Session")
        self.craft_lbl.setObjectName("card")
        self.craft_lbl.setStyleSheet("font-size: 15px; padding: 16px; border: 2px solid #334155; border-radius: 10px;")
        lay.addWidget(self.craft_lbl)
        self.craft_list = QListWidget(); self.craft_list.setMaximumHeight(100)
        lay.addWidget(QLabel("Versuche:")); lay.addWidget(self.craft_list)
        self.craft_skill_list = QListWidget(); self.craft_skill_list.setMaximumHeight(70)
        lay.addWidget(QLabel("Skills:")); lay.addWidget(self.craft_skill_list)
        # Materialkosten
        lay.addWidget(QLabel("Materialkosten (geschätzt):"))
        self.mat_lbl = QLabel("Noch keine Crafts")
        self.mat_lbl.setStyleSheet("padding: 6px; background: #1e293b; border-radius: 6px;")
        lay.addWidget(self.mat_lbl)
        row = QHBoxLayout()
        b1 = QPushButton("Crafting starten"); b1.clicked.connect(self.start_craft)
        b2 = QPushButton("Crafting beenden"); b2.clicked.connect(self.stop_craft)
        row.addWidget(b1); row.addWidget(b2)
        lay.addLayout(row); lay.addStretch(); return w

    def start_craft(self):
        self.craft_attempts = 0; self.craft_success = 0
        self.craft_cost = 0.0; self.craft_return = 0.0
        self.session_skills = {}
        self.craft_list.clear()
        self.craft_skill_list.clear()
        self._add_session("crafting")
        self._update_craft()
        if self.chat_path and not self.watching: self.start_watching()

    def stop_craft(self):
        if self.current_session_id:
            from datetime import datetime
            db = SessionLocal()
            s = db.query(models.Session).get(self.current_session_id)
            if s:
                s.end_time = datetime.utcnow()
                s.data = {"skills": self.session_skills}
                db.commit()
            db.close()
            self.current_session_id = None
        self.craft_lbl.setText("Crafting beendet.")
        self._r_se()

    def _update_craft(self):
        rate = (self.craft_success / self.craft_attempts * 100) if self.craft_attempts else 0
        roi = (self.craft_return / self.craft_cost * 100) if self.craft_cost else 0
        profit = self.craft_return - self.craft_cost
        color = "#22c55e" if profit >= 0 else "#ef4444"
        self.craft_lbl.setText(
            f"Cost: {self.craft_cost:.4f} PED | Return: {self.craft_return:.4f} PED\n"
            f"Profit: {profit:+.4f} PED | ROI: {roi:.1f}%\n"
            f"Attempts: {self.craft_attempts} | Success: {self.craft_success} ({rate:.0f}%)"
        )
        self.craft_lbl.setStyleSheet(f"font-size: 14px; padding: 12px; border: 3px solid {color}; border-radius: 10px;")

    def _loadouts(self):
        w = QWidget(); lay = QVBoxLayout(w)
        top = QHBoxLayout()
        top.addWidget(QLabel("Loadouts"))
        top.addStretch()
        b_new = QPushButton("New"); b_new.clicked.connect(self.new_loadout)
        b_del = QPushButton("Delete"); b_del.clicked.connect(self.delete_loadout)
        top.addWidget(b_new); top.addWidget(b_del)
        lay.addLayout(top)
        self.lo_list = QListWidget()
        self.lo_list.itemDoubleClicked.connect(self.edit_loadout)
        lay.addWidget(self.lo_list)
        return w

    def delete_loadout(self):
        item = self.lo_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Delete", "Select a loadout first.")
            return
        name = item.text().split(" | ")[0]
        if QMessageBox.question(self, "Delete", f"Delete '{name}'?") != QMessageBox.Yes:
            return
        db = SessionLocal()
        lo = db.query(models.Loadout).filter(models.Loadout.name == name).first()
        if lo:
            db.delete(lo); db.commit()
        db.close()
        self._r_lo()
        self._reload_loadouts()

    def _sessions(self):
        w = QWidget(); lay = QVBoxLayout(w)
        # Overview box
        self.overview_lbl = QLabel("Overview loading...")
        self.overview_lbl.setStyleSheet("padding: 8px; background: #1e293b; border-radius: 6px;")
        lay.addWidget(self.overview_lbl)
        # Buttons
        btn_row = QHBoxLayout()
        b_cmp = QPushButton("Compare"); b_cmp.clicked.connect(self.compare_sessions)
        b_del = QPushButton("Delete"); b_del.clicked.connect(self.delete_session)
        btn_row.addWidget(b_cmp); btn_row.addWidget(b_del); btn_row.addStretch()
        lay.addLayout(btn_row)
        # Session list with search
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        self.se_search = QLineEdit()
        self.se_search.setPlaceholderText("Filter sessions...")
        self.se_search.textChanged.connect(self._r_se)
        search_row.addWidget(self.se_search)
        lay.addLayout(search_row)
        lay.addWidget(QLabel("Sessions:"))
        self.se_list = QListWidget()
        self.se_list.setMaximumHeight(150)
        self.se_list.itemDoubleClicked.connect(self.show_session_detail)
        self.se_list.itemClicked.connect(self._show_session_table)
        # Rechtsklick für Umbenennen
        self.se_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.se_list.customContextMenuRequested.connect(self._session_context_menu)
        lay.addWidget(self.se_list)
        # Detail table
        lay.addWidget(QLabel("Session Details:"))
        self.se_table = QTableWidget()
        self.se_table.setColumnCount(5)
        self.se_table.setHorizontalHeaderLabels(["Item", "Qty", "TT", "MU%", "Value"])
        self.se_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.se_table.setMinimumHeight(200)
        lay.addWidget(self.se_table)
        return w

    def _show_session_table(self, item):
        text = item.text()
        # Extract name from "TYPE – Name | Date | Return%"
        parts = text.split(" | ")
        name_part = parts[0] if parts else text
        name = name_part.split(" – ")[-1] if " – " in name_part else name_part
        db = SessionLocal()
        s = db.query(models.Session).filter(models.Session.name == name).order_by(models.Session.start_time.desc()).first()
        db.close()
        self.se_table.setRowCount(0)
        if not s or not s.data:
            return
        loot = s.data.get("loot", [])
        self.se_table.setRowCount(len(loot))
        for i, l in enumerate(loot):
            self.se_table.setItem(i, 0, QTableWidgetItem(l.get("name", "?")))
            self.se_table.setItem(i, 1, QTableWidgetItem(str(l.get("qty", 1))))
            self.se_table.setItem(i, 2, QTableWidgetItem(f"{l.get('tt', 0):.4f}"))
            self.se_table.setItem(i, 3, QTableWidgetItem("100"))
            val = l.get("tt", 0) * l.get("qty", 1)
            self.se_table.setItem(i, 4, QTableWidgetItem(f"{val:.4f}"))

    def _session_context_menu(self, pos):
        item = self.se_list.itemAt(pos)
        if not item:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        rename = menu.addAction("Rename")
        delete = menu.addAction("Delete")
        action = menu.exec(self.se_list.mapToGlobal(pos))
        if action == rename:
            self._rename_session(item)
        elif action == delete:
            self.delete_session()

    def _rename_session(self, item):
        text = item.text()
        parts = text.split(" | ")
        name_part = parts[0] if parts else text
        old_name = name_part.split(" – ")[-1] if " – " in name_part else name_part
        new_name, ok = QLineEdit().text(), True
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        if ok and new_name.strip():
            db = SessionLocal()
            s = db.query(models.Session).filter(models.Session.name == old_name).first()
            if s:
                s.name = new_name.strip()
                db.commit()
            db.close()
            self._r_se()

    def delete_session(self):
        item = self.se_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Delete", "Select a session first.")
            return
        text = item.text()
        name = text.split(" – ")[-1] if " – " in text else text
        if QMessageBox.question(self, "Delete", f"Delete session '{name}'?") != QMessageBox.Yes:
            return
        db = SessionLocal()
        s = db.query(models.Session).filter(models.Session.name == name).first()
        if s:
            db.delete(s); db.commit()
        db.close()
        self._r_se()

    def compare_sessions(self):
        db = SessionLocal()
        sessions = db.query(models.Session).order_by(models.Session.start_time.desc()).limit(20).all()
        db.close()
        if len(sessions) < 2:
            QMessageBox.information(self, "Vergleich", "Mindestens 2 Sessions nötig.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Session-Vergleich")
        dlg.setMinimumWidth(480)
        f = QFormLayout(dlg)
        c1 = QComboBox(); c2 = QComboBox()
        for s in sessions:
            label = f"{s.type} – {s.name}"
            c1.addItem(label, s.id)
            c2.addItem(label, s.id)
        f.addRow("Session A:", c1)
        f.addRow("Session B:", c2)
        result = QLabel("")
        result.setWordWrap(True)
        f.addRow(result)
        def do_cmp():
            db = SessionLocal()
            a = db.query(models.Session).get(c1.currentData())
            b = db.query(models.Session).get(c2.currentData())
            db.close()
            if not a or not b:
                return
            def line(s):
                c = s.total_cost_tt or 0
                r = s.total_return_mu or 0
                p = (r / c * 100) if c else 0
                return f"{s.name}: Kosten {c:.2f} | Return {r:.2f} | {p:.1f}%"
            result.setText(f"{line(a)}\n{line(b)}\n\nDifferenz Return: {(b.total_return_mu or 0) - (a.total_return_mu or 0):+.2f}")
        btn = QPushButton("Vergleichen")
        btn.clicked.connect(do_cmp)
        f.addRow(btn)
        dlg.exec()

    def _update_overview(self):
        from datetime import datetime, timedelta
        db = SessionLocal()
        now = datetime.utcnow()
        day = now - timedelta(days=1)
        week = now - timedelta(days=7)
        day_s = db.query(models.Session).filter(models.Session.start_time >= day).all()
        week_s = db.query(models.Session).filter(models.Session.start_time >= week).all()
        db.close()
        def summ(sessions):
            c = sum(s.total_cost_tt or 0 for s in sessions)
            r = sum(s.total_return_mu or 0 for s in sessions)
            return c, r, r - c
        dc, dr, dp = summ(day_s)
        wc, wr, wp = summ(week_s)
        self.overview_lbl.setText(
            f"Heute: Kosten {dc:.2f} | Return {dr:.2f} | Gewinn {dp:+.2f}\n"
            f"7 Tage: Kosten {wc:.2f} | Return {wr:.2f} | Gewinn {wp:+.2f}"
        )

    def show_session_detail(self, li):
        text = li.text()
        name = text.split(" – ")[-1] if " – " in text else text
        db = SessionLocal()
        s = db.query(models.Session).filter(models.Session.name == name).order_by(models.Session.start_time.desc()).first()
        if s:
            SessionDetailDialog(s, self).exec()
        else:
            QMessageBox.information(self, "Session", "Keine Details gefunden.")
        db.close()

    def _trades(self):
        w = QWidget(); lay = QVBoxLayout(w)
        top = QHBoxLayout(); top.addWidget(QLabel("Trading")); top.addStretch()
        b = QPushButton("Neuer Trade"); b.clicked.connect(self.new_trade); top.addWidget(b)
        lay.addLayout(top)
        self.tr_list = QListWidget(); lay.addWidget(self.tr_list); return w

    def _items(self):
        w = QWidget(); lay = QVBoxLayout(w)
        top = QHBoxLayout()
        top.addWidget(QLabel("Suche:"))
        self.search_item = QLineEdit()
        self.search_item.setPlaceholderText("Itemname...")
        self.search_item.textChanged.connect(self._r_it)
        top.addWidget(self.search_item)
        top.addWidget(QLabel("Kategorie:"))
        self.filter_cat = QComboBox()
        self.filter_cat.addItems(["Alle", "weapon", "armor", "healing", "resource", "tool", "enhancer", "other"])
        self.filter_cat.currentIndexChanged.connect(self._r_it)
        top.addWidget(self.filter_cat)
        self.filter_mob = QLineEdit()
        self.filter_mob.setPlaceholderText("Mob")
        self.filter_mob.textChanged.connect(self._r_it)
        top.addWidget(self.filter_mob)
        b_new = QPushButton("Neues Item")
        b_new.clicked.connect(self.new_item)
        top.addWidget(b_new)
        lay.addLayout(top)
        lay.addWidget(QLabel("Items (Doppelklick = bearbeiten)"))
        self.it_list = QListWidget()
        self.it_list.itemDoubleClicked.connect(self.edit_item)
        lay.addWidget(self.it_list)
        return w

    def _settings(self):
        w = QWidget(); lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Einstellungen"))
        self.chat_path_lbl = QLabel("Chat.log: nicht gesetzt")
        lay.addWidget(self.chat_path_lbl)
        b_ex = QPushButton("Alle Sessions exportieren")
        b_ex.clicked.connect(self.export_all_sessions)
        lay.addWidget(b_ex)
        b_port = QPushButton("Portfolio exportieren")
        b_port.clicked.connect(self.export_portfolio)
        lay.addWidget(b_port)
        b_ov = QPushButton("Zusätzliches Overlay öffnen")
        b_ov.clicked.connect(self.add_overlay)
        lay.addWidget(b_ov)
        lay.addWidget(QLabel("Standard-Markup %:"))
        self.default_mu = QDoubleSpinBox(); self.default_mu.setRange(0, 1000); self.default_mu.setValue(100)
        lay.addWidget(self.default_mu)
        lay.addStretch(); return w

    def _load_settings(self):
        try:
            if self.settings_file.exists():
                return json.loads(self.settings_file.read_text(encoding="utf-8"))
        except Exception as e:
            log.error(f"Fehler: {e}")
        return {"chat_path": "", "default_mu": 100.0}

    def _save_settings(self):
        try:
            self.settings_file.write_text(json.dumps(self.settings), encoding="utf-8")
        except Exception as e:
            log.error(f"Fehler: {e}")

    def add_overlay(self):
        ov = Overlay()
        ov.show()
        txt = self.hunt_lbl.text() if hasattr(self, "hunt_lbl") else "Overlay"
        ov.set_text(txt)
        self.overlays.append(ov)

    def export_all_sessions(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "sessions.csv", "CSV (*.csv)")
        if not path:
            return
        import csv
        db = SessionLocal()
        sessions = db.query(models.Session).all()
        db.close()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Type", "Name", "Cost", "ReturnTT", "ReturnMU", "Shots", "Notes"])
            for s in sessions:
                w.writerow([s.type, s.name, s.total_cost_tt or 0, s.total_return_tt or 0,
                            s.total_return_mu or 0, s.shots or 0, s.notes or ""])
        QMessageBox.information(self, "Export", f"{len(sessions)} Sessions exportiert.")

    def export_portfolio(self):
        path, _ = QFileDialog.getSaveFileName(self, "Portfolio", "portfolio.csv", "CSV (*.csv)")
        if not path:
            return
        import csv
        db = SessionLocal()
        trades = db.query(models.Trade).all()
        db.close()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Trade", "Status", "Notes"])
            for t in trades:
                w.writerow([t.name, t.status, t.notes or ""])
        QMessageBox.information(self, "Export", f"{len(trades)} Trades exportiert.")

    def _on_loadout_selected(self):
        name = self.lo_combo.currentData()
        if not name:
            self.active_loadout = None
            return
        db = SessionLocal()
        lo = db.query(models.Loadout).filter(models.Loadout.name == name).first()
        if lo:
            # Werte kopieren bevor Session geschlossen wird
            self.active_loadout = type('Loadout', (), {
                'id': lo.id,
                'name': lo.name,
                'weapon_name': lo.weapon_name,
                'ammo_burn': lo.ammo_burn,
                'weapon_decay': lo.weapon_decay,
                'armor_decay_per_hit': lo.armor_decay_per_hit,
                'healing_decay_per_hit': lo.healing_decay_per_hit,
                'amplifier_decay': lo.amplifier_decay,
            })()
        else:
            self.active_loadout = None
        db.close()

    def _reload_loadouts(self):
        self.lo_combo.clear()
        self.lo_combo.addItem("-- Loadout wählen --", "")
        db = SessionLocal()
        for lo in db.query(models.Loadout).all():
            self.lo_combo.addItem(lo.name, lo.name)
        db.close()

    def refresh(self):
        try:
            self._r_lo()
        except Exception as e:
            log.error(f"Fehler: {e}")
        try:
            self._r_se()
        except Exception as e:
            log.error(f"Fehler: {e}")
        try:
            self._r_it()
        except Exception as e:
            log.error(f"Fehler: {e}")
        try:
            self._r_tr()
        except Exception as e:
            log.error(f"Fehler: {e}")
        try:
            self._reload_loadouts()
        except Exception as e:
            log.error(f"Fehler: {e}")

    def _r_it(self):
        if not hasattr(self, "it_list"):
            return
        self.it_list.clear()
        db = SessionLocal()
        q = db.query(models.Item)
        cat = self.filter_cat.currentText() if hasattr(self, "filter_cat") else "Alle"
        if cat and cat != "Alle":
            q = q.filter(models.Item.category == cat)
        items = q.order_by(models.Item.name).all()
        db.close()
        search = self.search_item.text().strip().lower() if hasattr(self, "search_item") else ""
        mob = self.filter_mob.text().strip().lower() if hasattr(self, "filter_mob") else ""
        if search:
            items = [it for it in items if search in it.name.lower()]
        if mob:
            items = [it for it in items if mob in (it.drop_mobs or "").lower()]
        if not items:
            self.it_list.addItem("Keine Items für diesen Filter.")
            return
        for it in items[:500]:
            extra = f" | {it.drop_mobs}" if it.drop_mobs else ""
            self.it_list.addItem(f"{it.name}  ({it.category})  {it.markup}%{extra}")
        self.it_list.addItem(f"--- {len(items)} Items ---")

    def _update_loadout_compare(self):
        self.cmp_list.clear()
        db = SessionLocal()
        loadouts = db.query(models.Loadout).all()
        db.close()
        for lo in loadouts:
            cost = (lo.ammo_burn or 0) + (lo.weapon_decay or 0) + (lo.amplifier_decay or 0)
            dpp = 0
            if lo.weapon_name:
                db = SessionLocal()
                it = db.query(models.Item).filter(models.Item.name == lo.weapon_name).first()
                if it and it.dpp:
                    dpp = it.dpp
                db.close()
            self.cmp_list.addItem(f"{lo.name}: Kosten/Schuss {cost:.4f} | DPP {dpp:.1f}")

    def _r_lo(self):
        self.lo_list.clear()
        db = SessionLocal()
        for lo in db.query(models.Loadout).all():
            self.lo_list.addItem(f"{lo.name} | {lo.weapon_name or '-'}")
        db.close()

    def _r_se(self):
        self.se_list.clear()
        search = self.se_search.text().lower() if hasattr(self, "se_search") else ""
        db = SessionLocal()
        for s in db.query(models.Session).order_by(models.Session.start_time.desc()).all():
            if search and search not in s.name.lower():
                continue
            profit = (s.total_return_mu or 0) - (s.total_cost_tt or 0)
            pct = ((s.total_return_mu or 0) / s.total_cost_tt * 100) if s.total_cost_tt else 0
            date = s.start_time.strftime("%Y-%m-%d") if s.start_time else "-"
            item = QListWidgetItem(f"{s.type.upper()} – {s.name} | {date} | {pct:.1f}%")
            if profit > 0:
                item.setForeground(QColor("#22c55e"))
            elif profit < 0:
                item.setForeground(QColor("#ef4444"))
            self.se_list.addItem(item)
        db.close()

    def _r_it(self):
        self.it_list.clear()
        db = SessionLocal()
        q = db.query(models.Item)
        cat = self.filter_cat.currentText()
        if cat and cat != "Alle":
            q = q.filter(models.Item.category == cat)
        mob = self.filter_mob.text().strip().lower()
        items = q.order_by(models.Item.name).all()
        db.close()
        if mob:
            items = [it for it in items if mob in (it.drop_mobs or "").lower() or mob in (it.name or "").lower()]
        if not items:
            self.it_list.addItem("Keine Items für diesen Filter.")
            return
        for it in items:
            extra = f"  [{it.drop_mobs}]" if it.drop_mobs else ""
            self.it_list.addItem(f"{it.name}  ({it.category})  {it.markup}%{extra}")
        self.it_list.addItem(f"--- {len(items)} Items ---")

    def _r_tr(self):
        self.tr_list.clear()
        db = SessionLocal()
        for t in db.query(models.Trade).order_by(models.Trade.buy_date.desc()).all():
            self.tr_list.addItem(f"{t.name} [{t.status}] {t.notes or ''}")
        db.close()

    def new_item(self):
        """Dialog zum Erstellen eines neuen Items."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Neues Item")
        dlg.setMinimumWidth(400)
        f = QFormLayout(dlg)
        name = QLineEdit()
        cat = QComboBox()
        cat.addItems(["weapon", "armor", "healing", "tool", "enhancer", "resource", "other"])
        tt = QDoubleSpinBox(); tt.setRange(0, 1e6); tt.setDecimals(4)
        mu = QDoubleSpinBox(); mu.setRange(0, 10000); mu.setDecimals(2); mu.setValue(100)
        dmg = QDoubleSpinBox(); dmg.setRange(0, 10000); dmg.setDecimals(2)
        dpp = QDoubleSpinBox(); dpp.setRange(0, 1000); dpp.setDecimals(3)
        decay = QDoubleSpinBox(); decay.setRange(0, 100); decay.setDecimals(6)
        ammo = QDoubleSpinBox(); ammo.setRange(0, 100000); ammo.setDecimals(0)
        f.addRow("Name:", name)
        f.addRow("Kategorie:", cat)
        f.addRow("TT-Wert:", tt)
        f.addRow("Markup %:", mu)
        f.addRow("Damage:", dmg)
        f.addRow("DPP:", dpp)
        f.addRow("Decay (PED):", decay)
        f.addRow("Ammo Burn:", ammo)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        f.addRow(btns)
        if dlg.exec() == QDialog.Accepted and name.text().strip():
            db = SessionLocal()
            item = models.Item(
                name=name.text().strip(),
                category=cat.currentText(),
                tt_value=tt.value(),
                markup=mu.value(),
                damage=dmg.value() or None,
                dpp=dpp.value() or None,
                decay=decay.value() or None,
                ammo_burn=ammo.value() or None
            )
            db.add(item)
            db.commit()
            db.close()
            self._r_it()
            QMessageBox.information(self, "Item", f"'{name.text()}' hinzugefügt.")

    def edit_item(self, li):
        name = li.text().split("  (")[0]
        if not name or name.startswith("---"): return
        db = SessionLocal()
        it = db.query(models.Item).filter(models.Item.name == name).first()
        if it:
            d = ItemDialog(it, self)
            if d.exec() == QDialog.Accepted:
                d.save(); db.commit()
        db.close()
        self._r_it()

    def edit_loadout(self, li):
        name = li.text().split(" | ")[0]
        db = SessionLocal()
        lo = db.query(models.Loadout).filter(models.Loadout.name == name).first()
        if not lo:
            db.close()
            return
        d = LoadoutDialog(self)
        d.name.setText(lo.name or "")
        for combo, val in [
            (d.weapon, lo.weapon_name), (d.helm, lo.armor_helmet),
            (d.chest, lo.armor_chest), (d.arms, lo.armor_arms),
            (d.legs, lo.armor_legs), (d.feet, lo.armor_feet),
            (d.heal, lo.healing_name)
        ]:
            i = combo.findData(val)
            if i >= 0:
                combo.setCurrentIndex(i)
        d.ammo.setValue(lo.ammo_burn or 0)
        d.wdec.setValue(lo.weapon_decay or 0)
        d.adec.setValue(lo.armor_decay_per_hit or 0)
        d.hdec.setValue(lo.healing_decay_per_hit or 0)
        if d.exec() == QDialog.Accepted:
            data = d.data()
            for k, v in data.items():
                setattr(lo, k, v)
            db.commit()
        db.close()
        self._r_lo()

    def new_loadout(self):
        d = LoadoutDialog(self)
        if d.exec() == QDialog.Accepted:
            data = d.data()
            if not data["name"]:
                QMessageBox.warning(self, "Fehler", "Name fehlt."); return
            db = SessionLocal()
            db.add(models.Loadout(**data)); db.commit(); db.close()
            self._r_lo()
            self._reload_loadouts()

    def new_trade(self):
        d = TradeDialog(self)
        if d.exec() == QDialog.Accepted:
            db = SessionLocal()
            db.add(models.Trade(**d.data())); db.commit(); db.close()
            self._r_tr()

    def _add_session(self, typ):
        db = SessionLocal()
        db.add(models.Session(type=typ, name=f"{typ.capitalize()} Session"))
        db.commit(); db.close()
        self._r_se()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # Icon setzen
    icon_path = Path(__file__).parent / "logo.ico"
    if icon_path.exists():
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(icon_path)))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
