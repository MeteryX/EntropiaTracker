from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    tt_value = Column(Float, default=0.0)
    tt_max = Column(Float, nullable=True)
    markup = Column(Float, default=100.0)
    category = Column(String, default="other")
    # Stats
    damage = Column(Float, nullable=True)
    dps = Column(Float, nullable=True)
    dpp = Column(Float, nullable=True)
    efficiency = Column(Float, nullable=True)
    decay = Column(Float, nullable=True)
    ammo_burn = Column(Float, nullable=True)
    range_m = Column(Float, nullable=True)
    durability = Column(Float, nullable=True)
    limited = Column(Boolean, default=False)
    item_type = Column(String, nullable=True)  # Rifle, Pistol, etc.
    item_class = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    drop_mobs = Column(Text, nullable=True)

class Loadout(Base):
    __tablename__ = "loadouts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    weapon_name = Column(String)
    ammo_burn = Column(Float, default=0.0)
    weapon_decay = Column(Float, default=0.0)
    # Einzelne Rüstungsteile
    armor_helmet = Column(String, nullable=True)
    armor_chest = Column(String, nullable=True)
    armor_arms = Column(String, nullable=True)
    armor_legs = Column(String, nullable=True)
    armor_feet = Column(String, nullable=True)
    armor_decay_per_hit = Column(Float, default=0.0)
    healing_name = Column(String, nullable=True)
    healing_decay_per_hit = Column(Float, default=0.0)
    amplifier_name = Column(String, nullable=True)
    amplifier_decay = Column(Float, default=0.0)
    plating_chest = Column(String, nullable=True)
    plating_arms = Column(String, nullable=True)
    plating_legs = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String)  # hunting, mining, crafting, trading
    name = Column(String)
    loadout_id = Column(Integer, ForeignKey("loadouts.id"), nullable=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    total_cost_tt = Column(Float, default=0.0)
    total_return_tt = Column(Float, default=0.0)
    total_cost_mu = Column(Float, default=0.0)
    total_return_mu = Column(Float, default=0.0)
    shots = Column(Integer, default=0)
    data = Column(JSON, default=dict)

    loadout = relationship("Loadout")  # flexible extra data

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    buy_date = Column(DateTime, default=datetime.utcnow)
    sell_date = Column(DateTime, nullable=True)
    items = Column(JSON)  # list of {item_name, quantity, tt_value, buy_mu, sell_mu}
    notes = Column(Text, nullable=True)
    status = Column(String, default="open")  # open, closed

class ChatEvent(Base):
    __tablename__ = "chat_events"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    event_type = Column(String)
    raw_line = Column(Text)
    parsed = Column(JSON)
