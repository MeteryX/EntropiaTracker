"""
Decay-Berechnung für Entropia Universe.
Basierend auf Loot 2.0 Formeln.
"""

def armor_decay_ped(damage_absorbed: float, durability: float = 0) -> float:
    """
    Armor Decay in PED (Loot 2.0).
    Formel: Decay = damage * 0.05 * (1 - durability/100000) / 100
    (Ergebnis in PEC, dann /100 für PED)
    """
    if damage_absorbed <= 0:
        return 0.0
    factor = 1.0 - (durability / 100000.0)
    pec = damage_absorbed * 0.05 * factor
    return pec / 100.0  # PEC -> PED


def weapon_cost_per_shot(decay: float, ammo_burn: float, ammo_mu: float = 100.0) -> float:
    """
    Kosten pro Schuss in PED.
    Ammo ist in Einheiten (1 Einheit = 0.01 PEC = 0.0001 PED bei TT).
    """
    ammo_ped = (ammo_burn * 0.0001) * (ammo_mu / 100.0)
    return (decay or 0) + ammo_ped


def healing_decay_ped(heal_amount: float, heal_per_pec: float = 20.0) -> float:
    """
    Healing Decay Schätzung.
    heal_per_pec = wie viel HP pro PEC (typisch 18-25).
    """
    if heal_per_pec <= 0:
        return 0.0
    pec = heal_amount / heal_per_pec
    return pec / 100.0
