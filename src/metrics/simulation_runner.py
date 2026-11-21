"""
Silnik symulacji i generator benchmarku do ewaluacji optymalizacyjnej (GOPR DES).

Moduł odpowiada za:
1. Obiektową reprezentację zbioru benchmarkowego wypadków (BenchmarkDataset).
2. Elastyczną konfigurację obsady personalno-sprzętowej baz GOPR (BaseStaffing: zawodowi, ochotnicy, quady).
3. Uruchamianie symulacji w SimPy dla zadanej konfiguracji obsady baz (allocation).
4. Agregację metryk czasowych (średni czas dotarcia, 95-percentyl Triage, funkcja kosztu J dla optymalizatora).
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Iterator
import numpy as np
import simpy

from src.core.incident import Incident, Priority
from src.core.rescuer import Rescuer
from src.core.dispatcher import Dispatcher
from src.core.stochastic_generator import StochasticIncidentGenerator
from src.routing.routing_interface import AbstractRoutingService
from src.routing.gorce_trails_network import GorceTrailRoutingService, GORCE_TRAIL_NODES
from src.routing.weather_conditions import WeatherConditions


# ==============================================================================
# ELASTYCZNA OBSADA BAZY GOPR (BASE STAFFING)
# ==============================================================================

@dataclass
class BaseStaffing:
    """
    Obsada personalno-sprzętowa pojedynczej stacji / punktu ratunkowego GOPR.
    Pozwala optymalizatorowi precyzyjnie przydzielać różne zasoby do dowolnej bazy.
    """
    professionals: int = 0      # Ratownicy zawodowi (start natychmiast, tempo standardowe)
    volunteers: int = 0         # Ochotnicy (czas mobilizacji 5 min z domu/bazy)
    quads: int = 0              # Pojazdy zmotoryzowane (skuter śnieżny / quad, wysoka prędkość)

    @property
    def total_rescuers(self) -> int:
        """Łączna liczba ratowników/pojazdów w tej bazie."""
        return self.professionals + self.volunteers + self.quads

    @classmethod
    def from_any(cls, value: Union["BaseStaffing", int, Dict[str, int]]) -> "BaseStaffing":
        """
        Uniwersalny konwerter:
        - Obiekt BaseStaffing -> zwraca bez zmian,
        - Int (np. 2) -> traktowany jako 2 zawodowców,
        - Słownik (np. {"professionals": 2, "quads": 1}) -> tworzy obiekt BaseStaffing.
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            return cls(professionals=value)
        if isinstance(value, dict):
            return cls(
                professionals=value.get("professionals", 0),
                volunteers=value.get("volunteers", 0),
                quads=value.get("quads", 0)
            )
        raise TypeError(f"Nieobsługiwany typ konfiguracji bazy: {type(value)}")


# ==============================================================================
# OBIEKTOWA REPREZENTACJA ZBIORU BENCHMARKOWEGO (BENCHMARK DATASET)
# ==============================================================================

@dataclass
class BenchmarkDataset:
    """
    Obiektowa reprezentacja wzorcowego zbioru wypadków w Gorcach.
    Enkapsuluje listę zdarzeń, użyte ziarno losowości (seed) oraz statystyki.
    """
    incidents: List[Incident]
    seed: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def generate(
        cls,
        num_incidents: int = 100,
        seed: int = 42,
        start_hour: float = 8.0,
        peak_mean: float = 60.0,
        off_peak_mean: float = 240.0,
        generator: Optional[StochasticIncidentGenerator] = None
    ) -> "BenchmarkDataset":
        """
        Metoda fabryczna: wytwarza powtarzalny zbiór N wypadków
        zgodnie z niejednorodnym procesem Poissona.
        """
        gen = generator or StochasticIncidentGenerator(
            seed=seed,
            start_hour=start_hour,
            peak_mean=peak_mean,
            off_peak_mean=off_peak_mean
        )

        incidents_list: List[Incident] = []
        current_time = 0.0

        for i in range(num_incidents):
            delay = gen.get_next_delay(current_time)
            current_time += delay
            inc_id = f"BENCH_{i+1:03d}"
            incident = gen.generate_incident(sim_time_minutes=round(current_time, 2), incident_id=inc_id)
            incidents_list.append(incident)

        meta = {
            "num_incidents": num_incidents,
            "seed": seed,
            "start_hour": start_hour,
            "total_span_minutes": round(current_time, 2)
        }

        return cls(incidents=incidents_list, seed=seed, metadata=meta)

    def save_to_json(self, filepath: Union[str, Path]) -> None:
        """Zapisuje zbiór benchmarkowy wraz z metadanymi do pliku JSON."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "seed": self.seed,
            "metadata": self.metadata,
            "incidents": [
                {
                    "incident_id": inc.incident_id,
                    "target_node": inc.target_node,
                    "priority": int(inc.priority),
                    "required_rescuers": inc.required_rescuers,
                    "rescue_duration": inc.rescue_duration,
                    "created_at": inc.created_at,
                    "incident_type": inc.incident_type,
                    "description": inc.description
                }
                for inc in self.incidents
            ]
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_json(cls, filepath: Union[str, Path]) -> "BenchmarkDataset":
        """Wczytuje zbiór benchmarkowy z pliku JSON (obsługuje format obiektowy i surową listę)."""
        path = Path(filepath)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            raw_incidents = data
            seed = None
            metadata = {}
        else:
            raw_incidents = data.get("incidents", [])
            seed = data.get("seed", None)
            metadata = data.get("metadata", {})

        incidents: List[Incident] = []
        for item in raw_incidents:
            inc = Incident(
                incident_id=item["incident_id"],
                target_node=item["target_node"],
                priority=Priority(item["priority"]),
                required_rescuers=item.get("required_rescuers", 1),
                rescue_duration=item.get("rescue_duration", 30.0),
                created_at=item.get("created_at", 0.0),
                incident_type=item.get("incident_type", "TRAUMA"),
                description=item.get("description", "")
            )
            incidents.append(inc)

        return cls(incidents=incidents, seed=seed, metadata=metadata)

    def clone(self) -> "BenchmarkDataset":
        """Tworzy czystą kopię obiektów zdarzeń do nowej symulacji."""
        cloned_incidents = [
            Incident(
                incident_id=inc.incident_id,
                target_node=inc.target_node,
                priority=inc.priority,
                required_rescuers=inc.required_rescuers,
                rescue_duration=inc.rescue_duration,
                created_at=inc.created_at,
                incident_type=inc.incident_type,
                description=inc.description
            )
            for inc in self.incidents
        ]
        return BenchmarkDataset(incidents=cloned_incidents, seed=self.seed, metadata=dict(self.metadata))

    @property
    def total_duration_hours(self) -> float:
        """Łączny czas trwania scenariusza w godzinach."""
        if not self.incidents:
            return 0.0
        max_time = max(inc.created_at for inc in self.incidents)
        return round(max_time / 60.0, 2)

    @property
    def priority_breakdown(self) -> Dict[str, int]:
        """Rozkład liczbowy kategorii priorytetów."""
        counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        for inc in self.incidents:
            counts[inc.priority.name] = counts.get(inc.priority.name, 0) + 1
        return counts

    # Protokół kolekcji Pythona
    def __len__(self) -> int:
        return len(self.incidents)

    def __iter__(self) -> Iterator[Incident]:
        return iter(self.incidents)

    def __getitem__(self, index: int) -> Incident:
        return self.incidents[index]


# ==============================================================================
# RAPORT WYNIKOWY SYMULACJI (SIMULATION RESULTS)
# ==============================================================================

@dataclass
class SimulationResults:
    """Zagregowane wyniki z przebiegu symulacji dla danej dyslokacji ratowników."""
    allocation: Dict[str, Any]
    total_incidents: int
    resolved_count: int
    unresolved_count: int

    response_times: List[float] = field(default_factory=list)
    critical_response_times: List[float] = field(default_factory=list)

    mean_response_time: float = 0.0
    median_response_time: float = 0.0
    p95_response_time: float = 0.0
    p95_critical_response_time: float = 0.0

    def compute_fitness(self, w_critical: float = 1.5, budget_penalty: float = 0.0) -> float:
        """
        Oblicza wartość funkcji celu J minimalizowanej przez optymalizator Tomasza:
        J = Mean(T_response) + w_critical * P95(Triage_Critical) + Kary_budzetowe
        """
        crit_part = self.p95_critical_response_time if self.p95_critical_response_time > 0 else self.mean_response_time
        unresolved_penalty = self.unresolved_count * 100.0
        j_score = self.mean_response_time + (w_critical * crit_part) + budget_penalty + unresolved_penalty
        return round(j_score, 2)

    def summary_dict(self) -> Dict[str, Any]:
        """Zwraca czytelny słownik ze statystykami."""
        alloc_summary = {}
        for base, val in self.allocation.items():
            if isinstance(val, BaseStaffing):
                alloc_summary[base] = {
                    "professionals": val.professionals,
                    "volunteers": val.volunteers,
                    "quads": val.quads
                }
            else:
                alloc_summary[base] = val

        return {
            "allocation": alloc_summary,
            "total_incidents": self.total_incidents,
            "resolved_count": self.resolved_count,
            "unresolved_count": self.unresolved_count,
            "mean_response_time_min": self.mean_response_time,
            "median_response_time_min": self.median_response_time,
            "p95_response_time_min": self.p95_response_time,
            "p95_critical_response_time_min": self.p95_critical_response_time,
            "fitness_score_J": self.compute_fitness()
        }


# ==============================================================================
# GŁÓWNY SILNIK SYMULACJI (EVALUATION RUNNER DLA OPTYMALIZATORA)
# ==============================================================================

def run_simulation_evaluation(
    allocation: Dict[str, Union[BaseStaffing, int, Dict[str, int]]],
    benchmark_incidents: Union[BenchmarkDataset, List[Incident]],
    weather: Optional[WeatherConditions] = None,
    routing_service: Optional[AbstractRoutingService] = None,
    quad_speed_factor: float = 2.6,
    standard_speed_factor: float = 1.15
) -> SimulationResults:
    """
    Uruchamia pełną symulację DES dla zadanej dyslokacji ratowników i zbioru wypadków.
    
    :param allocation: Słownik bazy -> BaseStaffing lub int/dict (zawodowi, ochotnicy, quady).
    :param benchmark_incidents: Obiekt BenchmarkDataset lub lista obiektów Incident.
    :param weather: Warunki atmosferyczne (śnieg, wiatr, widoczność).
    :param routing_service: Opcjonalny własny serwis trasowania (domyślnie: GorceTrailRoutingService).
    :return: Obiekt SimulationResults z czasem reakcji i wskaźnikiem dopasowania J.
    """
    # 1. Klonowanie zdarzeń (nie modyfikujemy oryginalnego zbioru benchmarkowego)
    if isinstance(benchmark_incidents, BenchmarkDataset):
        incidents = benchmark_incidents.clone().incidents
    else:
        incidents = [
            Incident(
                incident_id=orig.incident_id,
                target_node=orig.target_node,
                priority=orig.priority,
                required_rescuers=orig.required_rescuers,
                rescue_duration=orig.rescue_duration,
                created_at=orig.created_at,
                incident_type=orig.incident_type,
                description=orig.description
            )
            for orig in benchmark_incidents
        ]

    # 2. Tworzenie środowiska SimPy i serwisu trasowania
    env = simpy.Environment()
    if routing_service is not None:
        routing = routing_service
    else:
        weather_cond = weather or WeatherConditions(snow_cm=5.0, wind_kmh=20.0)
        routing = GorceTrailRoutingService(default_weather=weather_cond)

    # 3. Elastyczne powoływanie ratowników zgodnie ze specyfikacją BaseStaffing
    rescuers: List[Rescuer] = []
    rescuer_counter = 1

    normalized_allocation: Dict[str, BaseStaffing] = {}

    for base_node, spec_raw in allocation.items():
        if base_node not in GORCE_TRAIL_NODES and (hasattr(routing, "graph") and base_node not in routing.graph):
            continue

        staffing = BaseStaffing.from_any(spec_raw)
        normalized_allocation[base_node] = staffing

        # A. Ratownicy zawodowi (start natychmiast, tempo standardowe)
        for _ in range(staffing.professionals):
            r = Rescuer(
                env=env,
                agent_id=f"GOPR_Zawodowy_{base_node[:6]}_{rescuer_counter}",
                base_node=base_node,
                routing_service=routing,
                speed_factor=standard_speed_factor,
                is_volunteer=False
            )
            rescuers.append(r)
            rescuer_counter += 1

        # B. Ochotnicy (czas mobilizacji 5 min z domu/bazy)
        for _ in range(staffing.volunteers):
            r = Rescuer(
                env=env,
                agent_id=f"GOPR_Ochotnik_{base_node[:6]}_{rescuer_counter}",
                base_node=base_node,
                routing_service=routing,
                speed_factor=1.05,
                is_volunteer=True
            )
            rescuers.append(r)
            rescuer_counter += 1

        # C. Quady / skutery śnieżne (wysoka prędkość, brak opóźnienia)
        for _ in range(staffing.quads):
            r = Rescuer(
                env=env,
                agent_id=f"GOPR_Quad_{base_node[:6]}_{rescuer_counter}",
                base_node=base_node,
                routing_service=routing,
                speed_factor=quad_speed_factor,
                is_volunteer=False
            )
            rescuers.append(r)
            rescuer_counter += 1

    dispatcher = Dispatcher(env=env, rescuers=rescuers, routing_service=routing)

    # 4. Proces wprowadzający zdarzenia na osi czasu DES
    def incident_scheduler():
        for inc in incidents:
            wait_time = inc.created_at - env.now
            if wait_time > 0:
                yield env.timeout(wait_time)
            dispatcher.handle_incident(inc)

    env.process(incident_scheduler())

    # 5. Czas trwania symulacji: moment ostatniego wezwania + bufor 240 minut
    max_created = max((inc.created_at for inc in incidents), default=0.0)
    sim_until = max_created + 240.0

    env.run(until=sim_until)

    # 6. Agregacja metryk
    response_times = [inc.response_time for inc in incidents if inc.response_time is not None]
    critical_times = [
        inc.response_time for inc in incidents
        if inc.priority == Priority.CRITICAL and inc.response_time is not None
    ]

    resolved_count = sum(1 for inc in incidents if inc.is_resolved)
    unresolved_count = len(incidents) - resolved_count

    mean_resp = float(np.mean(response_times)) if response_times else 999.0
    median_resp = float(np.median(response_times)) if response_times else 999.0
    p95_resp = float(np.percentile(response_times, 95)) if response_times else 999.0
    p95_crit = float(np.percentile(critical_times, 95)) if critical_times else mean_resp

    return SimulationResults(
        allocation=normalized_allocation,
        total_incidents=len(incidents),
        resolved_count=resolved_count,
        unresolved_count=unresolved_count,
        response_times=response_times,
        critical_response_times=critical_times,
        mean_response_time=round(mean_resp, 2),
        median_response_time=round(median_resp, 2),
        p95_response_time=round(p95_resp, 2),
        p95_critical_response_time=round(p95_crit, 2)
    )
