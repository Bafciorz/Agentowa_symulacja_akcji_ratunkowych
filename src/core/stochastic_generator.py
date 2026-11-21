"""
Stochastyczny generator zdarzeń ratunkowych GOPR (Discrete Event Simulation - DES).

Moduł odpowiada za:
1. Niejednorodny proces Poissona napływu wezwań (rozkład wykładniczy z uwzględnieniem godzin szczytu).
2. Mieszany strumień kategorii urazów (kontuzje, złamania, stany krytyczne, zaginięcia w terenie).
3. Rozkłady trójkątne (triangular) czasu trwania akcji ratowniczej / zaopatrzenia poszkodowanego.
4. Ważone losowanie lokalizacji wypadku na grafie Gorców (oparte na wagach eksperckich lub danych historycznych GOPR).
5. Integrację ze środowiskiem SimPy i dyspozytorem GOPR.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import numpy as np
import simpy

from src.core.incident import Incident, Priority
from src.core.dispatcher import Dispatcher
from src.routing.gorce_trails_network import GORCE_TRAIL_NODES


# ==============================================================================
# DOMYŚLNE WAGI RYZYKA I POPULARNOŚCI WĘZŁÓW W GORCACH (DO CZASU WGRANIA DANYCH GOPR)
# ==============================================================================

# Wypadki na szlakach (urazy nóg, zasłabnięcia, wypadki rowerowe/piesze):
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

# Zaginięcia w terenie (procedura WiSAR):
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
# MODEL RYZYKA ORAZ INTEGRACJA Z DANYMI HISTORYCZNYMI GOPR
# ==============================================================================

class GOPRHistoricalRiskModel:
    """
    Model empirycznego rozkładu prawdopodobieństwa lokalizacji wypadków.
    Może działać na wagach domyślnych lub wczytać rzeczywiste statystyki GOPR
    (ze słownika zliczeń wypadków lub pliku JSON/CSV).
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
        """Tworzy model bezpośrednio ze zliczeń interwencji zarejestrowanych przez GOPR."""
        return cls(trail_weights=trail_counts, search_weights=search_counts)

    @classmethod
    def from_json(cls, file_path: Union[str, Path]) -> "GOPRHistoricalRiskModel":
        """Wczytuje zliczenia interwencji GOPR z pliku JSON."""
        path = Path(file_path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        trail = data.get("trail_incidents", data)
        search = data.get("search_incidents", None)
        return cls(trail_weights=trail, search_weights=search)

    def to_json(self, file_path: Union[str, Path]) -> None:
        """Zapisuje bieżący profil wag ryzyka do pliku JSON."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "trail_incidents": self.trail_weights,
            "search_incidents": self.search_weights
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_probabilities(self, incident_type: str = "TRAUMA") -> Dict[str, float]:
        """Zwraca znormalizowany wektor prawdopodobieństw P(X = w_i), gdzie suma p_i = 1.0."""
        source_weights = self.search_weights if incident_type.upper() == "SEARCH" else self.trail_weights
        total = sum(source_weights.values())
        if total <= 0:
            # Równomierny rozkład w razie braku wag
            count = len(source_weights)
            return {node: 1.0 / count for node in source_weights}
        return {node: float(weight) / total for node, weight in source_weights.items()}


# ==============================================================================
# FUNKCJE STOCHASTYCZNE (PROCES POISSONA, URAZY, ROZKŁADY TRÓJKĄTNE)
# ==============================================================================

def get_next_incident_delay(
    sim_time_minutes: float,
    start_hour: float = 8.0,
    peak_mean: float = 60.0,
    off_peak_mean: float = 240.0,
    rng: Optional[np.random.Generator] = None
) -> float:
    """
    Niejednorodny proces Poissona (NHPP).
    Losuje czas oczekiwania na kolejne wezwanie (Delta t) z rozkładu wykładniczego:
    Delta t ~ Exponential(scale=mu), gdzie:
    - w godzinach szczytu (10:00 - 16:00): mu = peak_mean (domyślnie 60 min),
    - poza szczytem: mu = off_peak_mean (domyślnie 240 min).
    """
    if rng is None:
        rng = np.random.default_rng()

    # Wyliczamy aktualną godzinę doby (np. start 8:00 + 120 min = godzina 10:00)
    hour_of_day = (start_hour + (sim_time_minutes / 60.0)) % 24.0

    # Szczyt ruchu turystycznego w Gorcach
    is_peak = (10.0 <= hour_of_day < 16.0)
    mean_delay = peak_mean if is_peak else off_peak_mean

    delay = float(rng.exponential(scale=mean_delay))
    return max(delay, 0.1)


def sample_incident_category(
    rng: Optional[np.random.Generator] = None,
    category_weights: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Mieszany strumień urazów GOPR (kontuzje, złamania, NZK, poszukiwania WiSAR).
    Losuje kategorię wezwania według wag prawdopodobieństwa:
    - 40% Drobne kontuzje (LOW): 1 ratownik, czas na miejscu: triangular(10, 15, 25) min.
    - 30% Poważne urazy (HIGH): 2 ratowników (nosze alpejskie), czas: triangular(20, 30, 45) min.
    - 10% Stany krytyczne (CRITICAL): 1 ratownik (defibrylator AED), czas: triangular(25, 40, 60) min.
    - 20% Zaginięcia w terenie (SEARCH): 1 ratownik / patrol WiSAR, czas: triangular(30, 60, 120) min.
    """
    if rng is None:
        rng = np.random.default_rng()

    # Domyślny realistyczny podział wezwań GOPR
    weights = category_weights or {
        "LOW": 0.40,
        "HIGH": 0.30,
        "CRITICAL": 0.10,
        "SEARCH": 0.20
    }

    categories = list(weights.keys())
    probs = np.array(list(weights.values()), dtype=float)
    probs /= probs.sum()

    chosen_category = rng.choice(categories, p=probs)

    if chosen_category == "LOW":
        duration = float(rng.triangular(left=10.0, mode=15.0, right=25.0))
        return {
            "incident_type": "MINOR_INJURY",
            "category_code": "LOW",
            "priority": Priority.LOW,
            "required_rescuers": 1,
            "duration": round(duration, 2),
            "description": "Drobna kontuzja (skręcenie stawu skokowego, stłuczenie, odwodnienie)"
        }
    elif chosen_category == "HIGH":
        duration = float(rng.triangular(left=20.0, mode=30.0, right=45.0))
        return {
            "incident_type": "MAJOR_TRAUMA",
            "category_code": "HIGH",
            "priority": Priority.HIGH,
            "required_rescuers": 2,  # Wymóg noszy alpejskich i koordynacji zespołu
            "duration": round(duration, 2),
            "description": "Poważny uraz (złamanie otwarte kości, uraz kręgosłupa - wymóg noszy)"
        }
    elif chosen_category == "CRITICAL":
        duration = float(rng.triangular(left=25.0, mode=40.0, right=60.0))
        return {
            "incident_type": "CRITICAL_CARDIAC",
            "category_code": "CRITICAL",
            "priority": Priority.CRITICAL,
            "required_rescuers": 1,  # Wyzwala natychmiastowe Triage i dojazd z AED
            "duration": round(duration, 2),
            "description": "Stan krytyczny (nagłe zatrzymanie krążenia NZK / głęboka hipotermia / AED)"
        }
    else:  # SEARCH
        duration = float(rng.triangular(left=30.0, mode=60.0, right=120.0))
        return {
            "incident_type": "SEARCH",
            "category_code": "SEARCH",
            "priority": Priority.MEDIUM,
            "required_rescuers": 1,  # Patrol poszukiwawczy WiSAR
            "duration": round(duration, 2),
            "description": "Poszukiwanie zaginionego turysty poza szlakiem (procedura WiSAR)"
        }


def sample_incident_location(
    incident_type: str = "TRAUMA",
    risk_model: Optional[GOPRHistoricalRiskModel] = None,
    rng: Optional[np.random.Generator] = None
) -> str:
    """Ważone losowanie lokalizacji wypadku na grafie węzłów Gorców."""
    if rng is None:
        rng = np.random.default_rng()

    model = risk_model or GOPRHistoricalRiskModel()
    prob_map = model.get_probabilities(incident_type)

    nodes = list(prob_map.keys())
    probs = np.array(list(prob_map.values()), dtype=float)

    # Bezpiecznik numeryczny (suma prawdopodobieństw = 1.0)
    probs /= probs.sum()

    chosen_node = str(rng.choice(nodes, p=probs))
    return chosen_node


# ==============================================================================
# GŁÓWNA KLASA GENERATORA (STOCHASTIC INCIDENT GENERATOR)
# ==============================================================================

class StochasticIncidentGenerator:
    """
    Fasada generatora stochastycznego łącząca proces Poissona, wagi lokalizacji GOPR
    oraz rozkłady trójkątne urazów w spójną całość.
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        risk_model: Optional[GOPRHistoricalRiskModel] = None,
        start_hour: float = 8.0,
        peak_mean: float = 60.0,
        off_peak_mean: float = 240.0,
        category_weights: Optional[Dict[str, float]] = None
    ):
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.risk_model = risk_model or GOPRHistoricalRiskModel()
        self.start_hour = start_hour
        self.peak_mean = peak_mean
        self.off_peak_mean = off_peak_mean
        self.category_weights = category_weights
        self.incident_counter = 0

    def get_next_delay(self, sim_time_minutes: float) -> float:
        """Zwraca czas do kolejnego wezwania (w minutach)."""
        return get_next_incident_delay(
            sim_time_minutes=sim_time_minutes,
            start_hour=self.start_hour,
            peak_mean=self.peak_mean,
            off_peak_mean=self.off_peak_mean,
            rng=self.rng
        )

    def generate_incident(
        self,
        sim_time_minutes: float,
        incident_id: Optional[str] = None
    ) -> Incident:
        """Generuje w pełni uformowany, losowy obiekt Incident."""
        self.incident_counter += 1

        # 1. Losowanie kategorii urazu i czasu zaopatrzenia
        cat_info = sample_incident_category(rng=self.rng, category_weights=self.category_weights)

        # 2. Losowanie lokalizacji węzła na grafie Gorców
        loc_node = sample_incident_location(
            incident_type=cat_info["incident_type"],
            risk_model=self.risk_model,
            rng=self.rng
        )

        # 3. Formatowanie ID zgłoszenia
        if incident_id is None:
            code = cat_info["category_code"]
            incident_id = f"W_{self.incident_counter:03d}_{code}_{loc_node[:8]}"

        # 4. Tworzenie obiektu Incident
        incident = Incident(
            incident_id=incident_id,
            target_node=loc_node,
            priority=cat_info["priority"],
            required_rescuers=cat_info["required_rescuers"],
            rescue_duration=cat_info["duration"],
            created_at=sim_time_minutes,
            incident_type=cat_info["incident_type"],
            description=cat_info["description"]
        )

        return incident


# ==============================================================================
# PROCES SIMPY: STOCHASTYCZNY STRUMIEŃ WEZWAŃ DLA DYSPOZYTORA GOPR
# ==============================================================================

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
    Czeka w pętli `yield env.timeout(delay)`, generuje wezwanie
    i natychmiast przekazuje je do dyspozytora GOPR.
    """
    count = 0
    while True:
        if max_incidents is not None and count >= max_incidents:
            break
        if run_until is not None and env.now >= run_until:
            break

        # 1. Losujemy czas oczekiwania na kolejne zgłoszenie (proces Poissona)
        delay = generator.get_next_delay(env.now)

        if run_until is not None and (env.now + delay) > run_until:
            break

        yield env.timeout(delay)

        # 2. Generujemy nowe zdarzenie w chwili env.now
        incident = generator.generate_incident(env.now)
        count += 1

        if collected_incidents is not None:
            collected_incidents.append(incident)

        # 3. Dyspozytor GOPR podejmuje zdarzenie
        dispatcher.handle_incident(incident)
