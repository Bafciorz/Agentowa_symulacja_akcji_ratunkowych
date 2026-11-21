import tempfile
from pathlib import Path
import pytest

from src.core.incident import Priority
from src.metrics.simulation_runner import (
    BenchmarkDataset,
    generate_benchmark_dataset,
    save_benchmark_to_json,
    load_benchmark_from_json,
    run_simulation_evaluation,
    SimulationResults
)


def test_benchmark_dataset_class_features():
    """
    Weryfikacja obiektowych możliwości klasy BenchmarkDataset:
    - generowanie, długość, iteracja, indeksowanie,
    - metryki zbioru: total_duration_hours, priority_breakdown,
    - klonowanie,
    - zapis i odczyt z pliku JSON.
    """
    dataset = BenchmarkDataset.generate(num_incidents=30, seed=123)

    # Protokół kolekcji
    assert len(dataset) == 30
    assert dataset[0].incident_id == "BENCH_001"
    assert sum(1 for _ in dataset) == 30

    # Metadane i analizy
    assert dataset.total_duration_hours > 0.0
    breakdown = dataset.priority_breakdown
    assert isinstance(breakdown, dict)
    assert sum(breakdown.values()) == 30

    # Klonowanie (głęboka kopia obiektów Incident)
    cloned = dataset.clone()
    assert len(cloned) == 30
    cloned[0].is_resolved = True
    assert dataset[0].is_resolved is False  # Oryginał nie może zostać zmutowany!

    # Zapis i odczyt z JSON
    with tempfile.TemporaryDirectory() as tmp_dir:
        json_path = Path(tmp_dir) / "bench_dataset.json"
        dataset.save_to_json(json_path)

        loaded = BenchmarkDataset.load_from_json(json_path)
        assert len(loaded) == 30
        assert loaded.seed == 123
        assert loaded[0].incident_id == "BENCH_001"
        assert loaded.priority_breakdown == dataset.priority_breakdown


def test_benchmark_generation_and_reproducibility():
    """
    Weryfikacja generowania wzorcowego zbioru 100 wypadków (Common Random Numbers):
    - liczba zdarzeń: dokładnie 100,
    - czasy zgłoszeń są ściśle rosnące (oś czasu SimPy),
    - determinizm z ziarna (seed=42): dwa wywołania dają identyczne zdarzenia.
    """
    bench1 = generate_benchmark_dataset(num_incidents=100, seed=42)
    bench2 = generate_benchmark_dataset(num_incidents=100, seed=42)

    assert len(bench1) == 100
    assert len(bench2) == 100

    # Sprawdzenie monotoniczności czasu
    for i in range(len(bench1) - 1):
        assert bench1[i].created_at < bench1[i + 1].created_at

    # Sprawdzenie pełnej powtarzalności (Common Random Numbers)
    for inc1, inc2 in zip(bench1, bench2):
        assert inc1.incident_id == inc2.incident_id
        assert inc1.target_node == inc2.target_node
        assert inc1.priority == inc2.priority
        assert inc1.created_at == inc2.created_at


def test_benchmark_json_serialization():
    """Weryfikacja zapisu i odczytu zbioru benchmarkowego z pliku JSON."""
    incidents = generate_benchmark_dataset(num_incidents=20, seed=99)

    with tempfile.TemporaryDirectory() as tmp_dir:
        json_path = Path(tmp_dir) / "benchmark_20.json"
        save_benchmark_to_json(incidents, json_path)

        loaded = load_benchmark_from_json(json_path)
        assert len(loaded) == 20

        for orig, reloaded in zip(incidents, loaded):
            assert orig.incident_id == reloaded.incident_id
            assert orig.target_node == reloaded.target_node
            assert orig.priority == reloaded.priority
            assert orig.created_at == reloaded.created_at
            assert orig.rescue_duration == reloaded.rescue_duration


def test_run_simulation_evaluation_metrics():
    """
    Weryfikacja uruchomienia symulacji dla zadanej dyslokacji baz:
    sprawdzamy wyliczenie średnich czasów reakcji i funkcji kosztu J.
    """
    incidents = BenchmarkDataset.generate(num_incidents=5, seed=7, peak_mean=10.0, off_peak_mean=15.0)

    allocation = {
        "Schronisko_Turbacz": 2,
        "Stare_Wierchy": 1,
        "Kowaniec_NowyTarg": 1
    }

    results = run_simulation_evaluation(allocation=allocation, benchmark_incidents=incidents)

    assert isinstance(results, SimulationResults)
    assert results.total_incidents == 5
    assert results.resolved_count > 0
    assert len(results.response_times) > 0
    assert results.mean_response_time > 0.0

    fitness = results.compute_fitness()
    assert fitness > 0.0

    summary = results.summary_dict()
    assert "fitness_score_J" in summary
    assert "mean_response_time_min" in summary


def test_allocation_comparison_sensitivity():
    """
    Weryfikacja wrażliwości silnika:
    sprawdzamy, czy obsadzenie głównego węzła na Turbaczu (gdzie jest najwięcej wypadków)
    daje lepszy (niższy) czas reakcji niż obsadzenie wyłącznie odległej bazy dolnej.
    """
    incidents = BenchmarkDataset.generate(num_incidents=6, seed=123, peak_mean=12.0)

    good_alloc = {"Schronisko_Turbacz": 3}
    res_good = run_simulation_evaluation(allocation=good_alloc, benchmark_incidents=incidents)

    poor_alloc = {"Kowaniec_NowyTarg": 1}
    res_poor = run_simulation_evaluation(allocation=poor_alloc, benchmark_incidents=incidents)

    assert res_good.mean_response_time < res_poor.mean_response_time
    assert res_good.compute_fitness() < res_poor.compute_fitness()
