@dataclass
class StretcherTeam(RescueUnit):
    """Zespół idący DO poszkodowanego z pustymi noszami (25. centyl).
    Wolniejszy poza szlakiem ze względu na gabaryty noszy."""
    c: float = 0.88
    theta_0: float = -2.8
    w: float = 13.5
    d: float = 0.18
    e: float = -0.0020
    off_path_factor: float = 0.55
    steep_slope_factor: float = 0.75

    def load_patient(self) -> "EvacuationTeam":
        """Zamienia zespół z pustymi noszami w zespół ewakuacyjny po dotarciu do poszkodowanego."""
        return EvacuationTeam(unit_id=self.unit_id, pos=self.pos)