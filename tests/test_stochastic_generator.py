import json
import tempfile
from pathlib import Path
from typing import Optional, Union, Dict
import numpy as np
import simpy
import pytest

from src.core.incident import Incident, Priority
from src.core.dispatcher import Dispatcher
from src.core.rescuer import Rescuer, RescuerState
from src.routing.mock_routing import MockRoutingService
from src.routing.gorce_trails_network import GORCE_TRAIL_NODES
from src.core.stochastic_interface import (
    IncidentTypeSpec,
    AbstractArrivalProcess,
    AbstractIncidentTypeSampler,
    AbstractSpatialSampler
)
from src.core.stochastic_generator import (
    GOPRHistoricalRiskModel,
    PoissonArrivalProcess,
    ConstantArrivalProcess,
    GOPRTriageSampler,
    NodeNetworkSpatialSampler,
    get_next_incident_delay,
    sample_incident_category,
    sample_incident_location,
    StochasticIncidentGenerator,
    stochastic_incident_stream
)


def test_poisson_arrival_delays_peak_vs_off_peak():
    """
    Weryfikacja procesu Poissona:
    - w godzinach szczytu (10:00-16:00, np. t=180 min przy starcie o 8:00 -> godzina 11:00)
      średni czas między zgłoszeniami powinien wynosić ~60 minut.
    - poza szczytem (np. t=600 min -> godzina 18:00)
      średni czas między zgłoszeniami powinien wynosić ~240 minut.
    """
    rng = np.random.default_rng(seed=42)
    sample_size = 8000

    # 1. Test w godzinach szczytu (godzina 11:00 -> sim_time = 180 min)
    peak_delays = [
        get_next_incident_delay(sim_time_minutes=180.0, start_hour=8.0, rng=rng)
        for _ in range(sample_size)
    ]
    peak_mean = np.mean(peak_delays)
    assert 57.0 < peak_mean < 63.0

    # 2. Test poza szczytem (godzina 20:00 -> sim_time = 720 min)
    off_peak_delays = [
        get_next_incident_delay(sim_time_minutes=720.0, start_hour=8.0, rng=rng)
        for _ in range(sample_size)
    ]
    off_peak_mean = np.mean(off_peak_delays)
    assert 228.0 < off_peak_mean < 252.0


def test_incident_category_proportions_and_triangular_bounds():
    """
    Weryfikacja mieszanego strumienia urazów:
    - proporcje: ~40% LOW, ~30% HIGH, ~10% CRITICAL, ~20% SEARCH,
    - ograniczenia rozkładów trójkątnych dla każdej kategorii,
    - wymóg 2 ratowników dla zgłoszeń HIGH (nosze alpejskie).
    """
    rng = np.random.default_rng(seed=123)
    sample_size = 10000

    counts = {"LOW": 0, "HIGH": 0, "CRITICAL": 0, "SEARCH": 0}

    for _ in range(sample_size):
        info = sample_incident_category(rng=rng)
        code = info["category_code"]
        duration = info["duration"]
        required = info["required_rescuers"]
        counts[code] += 1

        if code == "LOW":
            assert 10.0 <= duration <= 25.0
            assert required == 1
            assert info["priority"] == Priority.LOW
        elif code == "HIGH":
            assert 20.0 <= duration <= 45.0
            assert required == 2  # Nosze alpejskie
            assert info["priority"] == Priority.HIGH
        elif code == "CRITICAL":
            assert 25.0 <= duration <= 60.0
            assert required == 1
            assert info["priority"] == Priority.CRITICAL
        elif code == "SEARCH":
            assert 30.0 <= duration <= 120.0
            assert required == 1
            assert info["priority"] == Priority.MEDIUM

    assert 0.375 < (counts["LOW"] / sample_size) < 0.425
    assert 0.275 < (counts["HIGH"] / sample_size) < 0.325
    assert 0.080 < (counts["CRITICAL"] / sample_size) < 0.120
    assert 0.175 < (counts["SEARCH"] / sample_size) < 0.225


def test_location_sampling_and_gopr_empirical_loading():
    """
    Weryfikacja losowania lokalizacji:
    1. Domyślne wagi trafiają w poprawne węzły Gorców.
    2. Wczytanie empirycznych danych GOPR (ze słownika i JSON) prawidłowo ustawia prawdopodobieństwa.
    """
    rng = np.random.default_rng(seed=999)

    # 1. Losowanie domyślne
    node = sample_incident_location(incident_type="TRAUMA", rng=rng)
    assert node in GORCE_TRAIL_NODES

    # 2. Model ze zliczeniami GOPR: 90% Turbacz, 10% Kiczora
    custom_counts = {
        "Schronisko_Turbacz": 90,
        "Kiczora": 10,
        "Hala_Dluga": 0
    }
    model = GOPRHistoricalRiskModel.from_counts(trail_counts=custom_counts)
    probs = model.get_probabilities(incident_type="TRAUMA")

    assert pytest.approx(probs["Schronisko_Turbacz"], 0.001) == 0.90
    assert pytest.approx(probs["Kiczora"], 0.001) == 0.10
    assert probs.get("Hala_Dluga", 0.0) == 0.0

    draws = [sample_incident_location(risk_model=model, rng=rng) for _ in range(2000)]
    turbacz_ratio = draws.count("Schronisko_Turbacz") / len(draws)
    assert 0.87 < turbacz_ratio < 0.93
    assert "Hala_Dluga" not in draws

    # 3. Zapis i odczyt z pliku JSON
    with tempfile.TemporaryDirectory() as tmp_dir:
        json_path = Path(tmp_dir) / "gopr_risk.json"
        model.to_json(json_path)

        loaded_model = GOPRHistoricalRiskModel.from_json(json_path)
        loaded_probs = loaded_model.get_probabilities()
        assert pytest.approx(loaded_probs["Schronisko_Turbacz"], 0.001) == 0.90


def test_stochastic_incident_generation_object():
    """
    Weryfikacja klasy fasady StochasticIncidentGenerator:
    tworzenie gotowego obiektu Incident z właściwymi metadanymi.
    """
    gen = StochasticIncidentGenerator(seed=777)
    inc = gen.generate_incident(sim_time_minutes=95.0)

    assert isinstance(inc, Incident)
    assert inc.created_at == 95.0
    assert inc.target_node in GORCE_TRAIL_NODES
    assert inc.priority in [Priority.LOW, Priority.HIGH, Priority.CRITICAL, Priority.MEDIUM]
    assert inc.required_rescuers in [1, 2]
    assert inc.rescue_duration > 0
    assert inc.incident_type in ["MINOR_INJURY", "MAJOR_TRAUMA", "CRITICAL_CARDIAC", "SEARCH"]
    assert len(inc.description) > 0


def test_simpy_integration_stochastic_stream():
    """
    Test integracyjny z silnikiem SimPy:
    sprawdzamy, czy dynamiczny strumień zdarzeń Poissona samoistnie
    tworzy wypadki i przekazuje je do dyspozytora w czasie symulacji.
    """
    env = simpy.Environment()
    routing = MockRoutingService(default_edge_time=5.0)

    r1 = Rescuer(env, "GOPR_1", base_node=0, routing_service=routing)
    r2 = Rescuer(env, "GOPR_2", base_node=0, routing_service=routing)
    dispatcher = Dispatcher(env, [r1, r2], routing_service=routing)

    generator = StochasticIncidentGenerator(seed=42, start_hour=11.0, peak_mean=15.0, off_peak_mean=30.0)

    collected: list = []
    env.process(
        stochastic_incident_stream(
            env=env,
            dispatcher=dispatcher,
            generator=generator,
            max_incidents=5,
            collected_incidents=collected
        )
    )

    env.run(until=180.0)

    assert len(collected) >= 2
    assert all(inc.created_at <= 180.0 for inc in collected)


# ==============================================================================
# NOWE TESTY ABSTRAKCJI (STRATEGY PATTERN & DEPENDENCY INJECTION)
# ==============================================================================

def test_constant_arrival_process():
    """Weryfikacja podstawienia alternatywnej strategii czasu (deterministyczny ConstantArrivalProcess)."""
    const_proc = ConstantArrivalProcess(interval_minutes=45.0)
    gen = StochasticIncidentGenerator(arrival_process=const_proc)

    # Niezależnie od godziny symulacji, czas oczekiwania wynosi dokładnie 45 minut
    assert gen.get_next_delay(sim_time_minutes=0.0) == 45.0
    assert gen.get_next_delay(sim_time_minutes=300.0) == 45.0
    assert gen.get_next_delay(sim_time_minutes=900.0) == 45.0


def test_custom_incident_type_registration():
    """
    Weryfikacja rozszerzalności kategoryzacji Triage:
    rejestrujemy nowy rodzaj wypadku (np. ukąszenie żmii) i sprawdzamy, czy generator go wytwarza.
    """
    triage = GOPRTriageSampler()
    snake_bite_spec = IncidentTypeSpec(
        name="SNAKE_BITE",
        category_code="VIPER",
        priority=Priority.HIGH,
        required_rescuers=1,
        duration_sampler=lambda _: 35.0,
        description="Ukąszenie przez żmiję zygzakowatą (podanie surowicy)"
    )
    triage.register_type(snake_bite_spec, weight=1.0)  # 100% szans na ten uraz

    gen = StochasticIncidentGenerator(type_sampler=triage, seed=55)
    incident = gen.generate_incident(sim_time_minutes=15.0)

    assert incident.incident_type == "SNAKE_BITE"
    assert incident.priority == Priority.HIGH
    assert incident.required_rescuers == 1
    assert incident.rescue_duration == 35.0
    assert "żmiję" in incident.description


def test_custom_spatial_sampler_injection():
    """
    Weryfikacja wstrzyknięcia niestandardowej strategii przestrzennej (AbstractSpatialSampler).
    """
    class MockSummitSampler(AbstractSpatialSampler):
        def sample_location(self, incident_type: str = "TRAUMA", rng: Optional[np.random.Generator] = None) -> str:
            return "Turbacz_Szczyt"

        def get_probabilities(self, incident_type: str = "TRAUMA") -> Dict[str, float]:
            return {"Turbacz_Szczyt": 1.0}

    gen = StochasticIncidentGenerator(spatial_sampler=MockSummitSampler(), seed=11)
    incident = gen.generate_incident(sim_time_minutes=50.0)

    assert incident.target_node == "Turbacz_Szczyt"
