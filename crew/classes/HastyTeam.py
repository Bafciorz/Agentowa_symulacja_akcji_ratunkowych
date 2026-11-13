@dataclass
class HastyTeam(RescueUnit):
    """Szybka dwójka/trójka patrolowa (80. centyl). Lekki sprzęt, bardzo wysoka mobilność."""
    c: float = 1.42
    theta_0: float = -2.5
    w: float = 15.2
    d: float = 0.28
    e: float = -0.0015
    off_path_factor: float = 0.75
    steep_slope_factor: float = 0.95