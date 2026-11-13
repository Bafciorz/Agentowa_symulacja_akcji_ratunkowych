@dataclass
class EvacuationTeam(RescueUnit):
    """Zespół wracający Z poszkodowanym w noszach (10. centyl).
    Drastyczny spadek prędkości na stromiznach (>15 st.) przez konieczność asekuracji linowej."""
    c: float = 0.55
    theta_0: float = -3.2
    w: float = 12.0
    d: float = 0.12
    e: float = -0.0022
    off_path_factor: float = 0.45
    steep_slope_factor: float = 0.35