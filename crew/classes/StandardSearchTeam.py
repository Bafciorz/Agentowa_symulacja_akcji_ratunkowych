@dataclass
class StandardSearchTeam(RescueUnit):
    """Standardowy zespół poszukiwawczy z plecakami medycznymi i linami (50. centyl)."""
    c: float = 1.15
    theta_0: float = -2.6
    w: float = 14.5
    d: float = 0.22
    e: float = -0.0018
    off_path_factor: float = 0.67
    steep_slope_factor: float = 0.85