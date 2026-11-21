"""
Stochastyczny generator zdarzeń ratunkowych GOPR (Discrete Event Simulation - DES).

Architektura oparta na Wzorcu Strategii (Strategy Pattern) i wstrzykiwaniu zależności:
- AbstractArrivalProcess: PoissonArrivalProcess (szczyt/pozaszczyt), ConstantArrivalProcess
- AbstractIncidentTypeSampler: GOPRTriageSampler (proporcje urazów, czasy trójkątne, rejestracja nowych typów)
- AbstractSpatialSampler: NodeNetworkSpatialSampler (węzły szlaków Gorców, dane empiryczne GOPR)
- StochasticIncidentGenerator: fasada łącząca strategie w spójny strumień zdarzeń SimPy
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Callable
import numpy as np
import simpy

from src.core.incident import Incident, Priority
from src.core.dispatcher import Dispatcher
from src.routing.gorce_trails_network import GORCE_TRAIL_NODES
from src.core.stochastic_interface import (
    IncidentTypeSpec,
    AbstractArrivalProcess,
    AbstractIncidentTypeSampler,
    AbstractSpatialSampler
)


# ==============================================================================
# DOMYŚLNE WAGI RYZYKA I POPULARNOŚCI WĘZŁÓW W GORCACH (DO CZASU WGRANIA DANYCH GOPR)
# ==============================================================================

DEFAULT_TRAIL_NODE_WEIGHTS: Dict[str, float] = {
    "Schronisko_Turbacz": 35.0,     # Główny węzeł turystyczny, taras, polana pod schroniskiem
    "Hala_Dluga": 15.0,             # Otwarta przestrzeń, krzyżówka szlaków GSB
    "Turbacz_Szczyt": 10.0,         # Najwyższy punkt, kamienie, podejście ze schroniska
    "Polana_Gabrowska": 10.0,       # Kluczowe skrzyżowanie szlaków, kamieniste podejście
    "Kiczora": 8.0,                 # Drugi szczyt pasma, ekspozycja i rumowiska skalne
    "Stare_Wierchy": 10.0,          # Drugie schronisko na zachodnim ramieniu, duży ruch
    "Obidowiec": 4.0,               # Szlak grzbietowy GSB
    "Jaworzyna_Kamienicka": 3.0,    # Szlak zielony GPN, polana z kapliczką
    "Przelecz_Knurowska": 2.0,      # Początek podejścia od wschodu
    "Kowaniec_NowyTarg": 2.0,       # Początek szlaku żółtego w dolinie
    "Kudlon": 1.0,                  # Mniej uczęszczany, dziki szczyt GPN
    "Dolina_Kamienicy_Wiatrolomy": 0.0  # Teren poza szlakiem - brak typowych wypadków szlakowych
}

DEFAULT_SEARCH_NODE_WEIGHTS: Dict[str, float] = {
    "Dolina_Kamienicy_Wiatrolomy": 45.0,  # Gęsty las, wiatrołomy, zwalone pnie, strome zbocza potoku
    "Kudlon": 25.0,                       # Dziki, skalisty rejon północny GPN
    "Jaworzyna_Kamienicka": 15.0,         # Schodzenie w boczne żleby i doliny potoków
    "Obidowiec": 8.0,                     # Zgubienie szlaku w gęstym lesie grzbietowym
    "Kiczora": 5.0,                       # Trudne, strome stoki w stronę Knurowskiej
    "Polana_Gabrowska": 2.0,              # Błędne odbicie w nieznaną ścieżkę leśną
    "Hala_Dluga": 0.0,
    "Schronisko_Turbacz": 0.0,
    "Turbacz_Szczyt": 0.0,
    "Stare_Wierchy": 0.0,
    "Przelecz_Knurowska": 0.0,
    "Kowaniec_NowyTarg": 0.0
}


# ==============================================================================
# 1. IMPLEMENTACJE PROCESÓW NAPŁYWU (ARRIVAL PROCESSES)
# ==============================================================================

class PoissonArrivalProcess(AbstractArrivalProcess):
    """
    Niejednorodny proces Poissona (NHPP).
    Czasy oczekiwania (Delta t) losowane z rozkładu wykładniczego:
    Delta t ~ Exponential(scale=mu), gdzie:
    - w godzinach szczytu (peak_start - peak_end): mu = peak_mean (np. 60 min),
    - poza szczytem: mu = off_peak_mean (np. 240 min).
    """

    def __init__(
        self,
        peak_mean: float = 60.0,
        off_peak_mean: float = 240.0,
        start_hour: float = 8.0,
        peak_start: float = 10.0,
        peak_end: float = 16.0
    ):
        self.peak_mean = peak_mean
        self.off_peak_mean = off_peak_mean
        self.start_hour = start_hour
        self.peak_start = peak_start
        self.peak_end = peak_end

    def get_next_delay(
        self,
        sim_time_minutes: float,
        rng: Optional[np.random.Generator] = None
    ) -> float:
        if rng is None:
            rng = np.random.default_rng()

        hour_of_day = (self.start_hour + (sim_time_minutes / 60.0)) % 24.0
        is_peak = (self.peak_start <= hour_of_day < self.peak_end)
        mean_delay = self.peak_mean if is_peak else self.off_peak_mean

        delay = float(rng.exponential(scale=mean_delay))
        return max(delay, 0.1)


class ConstantArrivalProcess(AbstractArrivalProcess):
    """
    Deterministyczny proces o stałym interwale czasowym.
    Idealny do testów regresyjnych, debugowania i benchmarków wydajnościowych.
    """

    def __init__(self, interval_minutes: float = 30.0):
        self.interval_minutes = interval_minutes

    def get_next_delay(
        self,
        sim_time_minutes: float,
        rng: Optional[np.random.Generator] = None
    ) -> float:
        return self.interval_minutes


# ==============================================================================
# 2. IMPLEMENTACJE MODELI PRZESTRZENNYCH (SPATIAL SAMPLERS)
# ==============================================================================

class GOPRHistoricalRiskModel:
    """
    Model danych empirycznych GOPR (przechowuje surowe zliczenia lub wagi dla szlaków i poszukiwań).
    """

    def __init__(
        self,
        trail_weights: Optional[Dict[str, float]] = None,
        search_weights: Optional[Dict[str, float]] = None
    ):
        self.trail_weights = dict(trail_weights or DEFAULT_TRAIL_NODE_WEIGHTS)
        self.search_weights = dict(search_weights or DEFAULT_SEARCH_NODE_WEIGHTS)

    @classmethod
    def from_counts(
        cls,
        trail_counts: Dict[str, Union[int, float]],
        search_counts: Optional[Dict[str, Union[int, float]]] = None
    ) -> "GOPRHistoricalRiskModel":
        return cls(trail_weights=trail_counts, search_weights=search_counts)

    @classmethod
    def from_json(cls, file_path: Union[str, Path]) -> "GOPRHistoricalRiskModel":
        path = Path(file_path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        trail = data.get("trail_incidents", data)
        search = data.get("search_incidents", None)
        return cls(trail_weights=trail, search_weights=search)

    def to_json(self, file_path: Union[str, Path]) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "trail_incidents": self.trail_weights,
            "search_incidents": self.search_weights
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_probabilities(self, incident_type: str = "TRAUMA") -> Dict[str, float]:
        source_weights = self.search_weights if str(incident_type).upper() == "SEARCH" else self.trail_weights
        total = sum(source_weights.values())
        if total <= 0:
            count = len(source_weights)
            return {node: 1.0 / count for node in source_weights}
        return {node: float(weight) / total for node, weight in source_weights.items()}


class NodeNetworkSpatialSampler(AbstractSpatialSampler):
    """
    Strategia przestrzenna losująca węzeł z sieci szlaków Gorców (GORCE_TRAIL_NODES).
    """

    def __init__(self, risk_model: Optional[GOPRHistoricalRiskModel] = None):
        self.risk_model = risk_model or GOPRHistoricalRiskModel()

    def get_probabilities(self, incident_type: str = "TRAUMA") -> Dict[str, float]:
        return self.risk_model.get_probabilities(incident_type)

    def sample_location(
        self,
        incident_type: str = "TRAUMA",
        rng: Optional[np.random.Generator] = None
    ) -> str:
        if rng is None:
            rng = np.random.default_rng()

        prob_map = self.get_probabilities(incident_type)
        nodes = list(prob_map.keys())
        probs = np.array(list(prob_map.values()), dtype=float)
        probs /= probs.sum()

        return str(rng.choice(nodes, p=probs))


# ==============================================================================
# 3. IMPLEMENTACJE KLASYFIKACJI MEDYCZNEJ / TRIAGE (INCIDENT TYPE SAMPLERS)
# ==============================================================================

class GOPRTriageSampler(AbstractIncidentTypeSampler):
    """
    Strategia kategoryzacji medycznej GOPR.
    Zamiast sztywnego if/elif, zarządza rejestrem obiektów IncidentTypeSpec i ich wagami.
    """

    def __init__(self, specs_with_weights: Optional[List[tuple[IncidentTypeSpec, float]]] = None):
        self.specs: List[IncidentTypeSpec] = []
        self.weights: List[float] = []

        if specs_with_weights:
            for spec, w in specs_with_weights:
                self.register_type(spec, w)

    def register_type(self, spec: IncidentTypeSpec, weight: float) -> None:
        """Dodaje nową kategorię urazu lub modyfikuje istniejącą."""
        self.specs.append(spec)
        self.weights.append(float(weight))

    @classmethod
    def default_gopr(cls, custom_weights: Optional[Dict[str, float]] = None) -> "GOPRTriageSampler":
        """Fabryka tworząca realistyczny profil wezwań GOPR."""
        w = custom_weights or {
            "LOW": 0.40,
            "HIGH": 0.30,
            "CRITICAL": 0.10,
            "SEARCH": 0.20
        }

        spec_low = IncidentTypeSpec(
            name="MINOR_INJURY",
            category_code="LOW",
            priority=Priority.LOW,
            required_rescuers=1,
            duration_sampler=lambda r: float(r.triangular(10.0, 15.0, 25.0)),
            description="Drobna kontuzja (skręcenie stawu skokowego, stłuczenie, odwodnienie)"
        )
        spec_high = IncidentTypeSpec(
            name="MAJOR_TRAUMA",
            category_code="HIGH",
            priority=Priority.HIGH,
            required_rescuers=2,  # Wymóg noszy alpejskich
            duration_sampler=lambda r: float(r.triangular(20.0, 30.0, 45.0)),
            description="Poważny uraz (złamanie otwarte kości, uraz kręgosłupa - wymóg noszy)"
        )
        spec_critical = IncidentTypeSpec(
            name="CRITICAL_CARDIAC",
            category_code="CRITICAL",
            priority=Priority.CRITICAL,
            required_rescuers=1,  # Defibrylator AED / Triage
            duration_sampler=lambda r: float(r.triangular(25.0, 40.0, 60.0)),
            description="Stan krytyczny (nagłe zatrzymanie krążenia NZK / głęboka hipotermia / AED)"
        )
        spec_search = IncidentTypeSpec(
            name="SEARCH",
            category_code="SEARCH",
            priority=Priority.MEDIUM,
            required_rescuers=1,  # Patrol WiSAR
            duration_sampler=lambda r: float(r.triangular(30.0, 60.0, 120.0)),
            description="Poszukiwanie zaginionego turysty poza szlakiem (procedura WiSAR)"
        )

        sampler = cls()
        sampler.register_type(spec_low, w.get("LOW", 0.40))
        sampler.register_type(spec_high, w.get("HIGH", 0.30))
        sampler.register_type(spec_critical, w.get("CRITICAL", 0.10))
        sampler.register_type(spec_search, w.get("SEARCH", 0.20))
        return sampler

    def get_category_probabilities(self) -> Dict[str, float]:
        total = sum(self.weights)
        if total <= 0:
            return {s.category_code: 1.0 / len(self.specs) for s in self.specs}
        return {s.category_code: w / total for s, w in zip(self.specs, self.weights)}

    def sample_incident_type(
        self,
        rng: Optional[np.random.Generator] = None
    ) -> IncidentTypeSpec:
        if rng is None:
            rng = np.random.default_rng()

        total = sum(self.weights)
        probs = [w / total for w in self.weights]
        chosen_idx = rng.choice(len(self.specs), p=probs)
        return self.specs[chosen_idx]


# ==============================================================================
# 4. GŁÓWNA FASADA GENERATORA (STOCHASTIC INCIDENT GENERATOR)
# ==============================================================================

class StochasticIncidentGenerator:
    """
    Fasada łącząca strategie: czasową, medyczną i przestrzenną.
    Udostępnia API do generowania zdarzeń i zarządzania ziarnem symulacji (seed).
    """

    def __init__(
        self,
        arrival_process: Optional[AbstractArrivalProcess] = None,
        spatial_sampler: Optional[AbstractSpatialSampler] = None,
        type_sampler: Optional[AbstractIncidentTypeSampler] = None,
        seed: Optional[int] = None,
        # Argumenty kompatybilności wstecznej:
        risk_model: Optional[GOPRHistoricalRiskModel] = None,
        start_hour: float = 8.0,
        peak_mean: float = 60.0,
        off_peak_mean: float = 240.0,
        category_weights: Optional[Dict[str, float]] = None
    ):
        self.seed = seed
        self.rng = np.random.default_rng(seed)

        # 1. Oś czasowa
        if arrival_process is not None:
            self.arrival_process = arrival_process
        else:
            self.arrival_process = PoissonArrivalProcess(
                peak_mean=peak_mean,
                off_peak_mean=off_peak_mean,
                start_hour=start_hour
            )

        # 2. Oś przestrzenna
        if spatial_sampler is not None:
            self.spatial_sampler = spatial_sampler
        else:
            self.spatial_sampler = NodeNetworkSpatialSampler(risk_model=risk_model)

        # 3. Oś medyczna / Triage
        if type_sampler is not None:
            self.type_sampler = type_sampler
        else:
            self.type_sampler = GOPRTriageSampler.default_gopr(custom_weights=category_weights)

        self.incident_counter = 0

    def get_next_delay(self, sim_time_minutes: float) -> float:
        """Zwraca czas do kolejnego wezwania (w minutach)."""
        return self.arrival_process.get_next_delay(sim_time_minutes=sim_time_minutes, rng=self.rng)

    def generate_incident(
        self,
        sim_time_minutes: float,
        incident_id: Optional[str] = None
    ) -> Incident:
        """Generuje w pełni uformowany obiekt Incident."""
        self.incident_counter += 1

        # 1. Losowanie kategorii i parametrów urazu
        type_spec = self.type_sampler.sample_incident_type(rng=self.rng)

        # 2. Losowanie czasu akcji ze strategii przypisanej do urazu
        duration = round(float(type_spec.duration_sampler(self.rng)), 2)

        # 3. Losowanie lokalizacji
        loc_node = self.spatial_sampler.sample_location(
            incident_type=type_spec.name,
            rng=self.rng
        )

        # 4. ID zgłoszenia
        if incident_id is None:
            incident_id = f"W_{self.incident_counter:03d}_{type_spec.category_code}_{str(loc_node)[:8]}"

        # 5. Tworzenie obiektu Incident
        return Incident(
            incident_id=incident_id,
            target_node=loc_node,
            priority=type_spec.priority,
            required_rescuers=type_spec.required_rescuers,
            rescue_duration=duration,
            created_at=sim_time_minutes,
            incident_type=type_spec.name,
            description=type_spec.description
        )


# ==============================================================================
# 5. FUNKCJE POMOCNICZE I PROCES SIMPY (KOMPATYBILNOŚĆ WSTECZNA)
# ==============================================================================

def get_next_incident_delay(
    sim_time_minutes: float,
    start_hour: float = 8.0,
    peak_mean: float = 60.0,
    off_peak_mean: float = 240.0,
    rng: Optional[np.random.Generator] = None
) -> float:
    """Funkcja pomocnicza: deleguje do PoissonArrivalProcess."""
    proc = PoissonArrivalProcess(
        peak_mean=peak_mean,
        off_peak_mean=off_peak_mean,
        start_hour=start_hour
    )
    return proc.get_next_delay(sim_time_minutes, rng=rng)


def sample_incident_category(
    rng: Optional[np.random.Generator] = None,
    category_weights: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """Funkcja pomocnicza: deleguje do GOPRTriageSampler."""
    if rng is None:
        rng = np.random.default_rng()
    sampler = GOPRTriageSampler.default_gopr(custom_weights=category_weights)
    spec = sampler.sample_incident_type(rng)
    duration = round(float(spec.duration_sampler(rng)), 2)
    return {
        "incident_type": spec.name,
        "category_code": spec.category_code,
        "priority": spec.priority,
        "required_rescuers": spec.required_rescuers,
        "duration": duration,
        "description": spec.description
    }


def sample_incident_location(
    incident_type: str = "TRAUMA",
    risk_model: Optional[GOPRHistoricalRiskModel] = None,
    rng: Optional[np.random.Generator] = None
) -> str:
    """Funkcja pomocnicza: deleguje do NodeNetworkSpatialSampler."""
    sampler = NodeNetworkSpatialSampler(risk_model=risk_model)
    return sampler.sample_location(incident_type=incident_type, rng=rng)


def stochastic_incident_stream(
    env: simpy.Environment,
    dispatcher: Dispatcher,
    generator: StochasticIncidentGenerator,
    max_incidents: Optional[int] = None,
    run_until: Optional[float] = None,
    collected_incidents: Optional[List[Incident]] = None
):
    """
    Proces SimPy generujący dynamiczny strumień zdarzeń na osi czasu DES.
    """
    count = 0
    while True:
        if max_incidents is not None and count >= max_incidents:
            break
        if run_until is not None and env.now >= run_until:
            break

        delay = generator.get_next_delay(env.now)
        if run_until is not None and (env.now + delay) > run_until:
            break

        yield env.timeout(delay)

        incident = generator.generate_incident(env.now)
        count += 1

        if collected_incidents is not None:
            collected_incidents.append(incident)

        dispatcher.handle_incident(incident)
