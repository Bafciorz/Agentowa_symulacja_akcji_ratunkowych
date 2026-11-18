#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SYMULACJA SYSTEMÓW DYSKRETNYCH: AKCJE RATUNKOWE GOPR (DES + ABM)
Główny punkt wejścia do symulacji.
Domyślnie uruchamia pełny scenariusz na szlakach Gorców z mapą Leaflet 3D/Topo.
Użycie:
    python run_simulation.py          # Uruchamia scenariusz górski ze szlakami Gorców
    python run_simulation.py --mock   # Uruchamia prosty scenariusz numeryczny (0..8)
"""

import sys
import argparse
from pathlib import Path

# Dodanie katalogu głównego do ścieżki Pythona
sys.path.append(str(Path(__file__).resolve().parent))

import simpy
from src.core.dispatcher import Dispatcher
from src.core.incident import Incident, Priority
from src.core.rescuer import Rescuer
from src.routing.mock_routing import MockRoutingService
import run_gorce_trails_simulation


def run_simple_mock_simulation():
    print("=" * 80)
    print("      SYMULACJA DYSKRETNA GOPR - PROSTY MODEL TESTOWY (WĘZŁY 0..8)")
    print("=" * 80)

    env = simpy.Environment()
    routing = MockRoutingService(default_edge_time=3.0)

    rescuer_1 = Rescuer(env, "GOPR_Alfa", base_node=0, routing_service=routing, speed_factor=1.0)
    rescuer_2 = Rescuer(env, "GOPR_Brawo", base_node=3, routing_service=routing, speed_factor=1.2)
    rescuer_vol = Rescuer(env, "GOPR_Ochotnik", base_node=0, routing_service=routing, speed_factor=0.9, is_volunteer=True)

    rescuers = [rescuer_1, rescuer_2, rescuer_vol]
    dispatcher = Dispatcher(env, rescuers, routing_service=routing)
    incidents = []

    def mountain_duty_scenario():
        print(f"\n[{env.now:.1f} min] >>> START PROSTEJ SYMULACJI DYŻURU <<<\n")

        inc1 = Incident("W01_Skrecenie_Kostki", target_node=5, priority=Priority.LOW, required_rescuers=1, rescue_duration=15.0)
        incidents.append(inc1)
        dispatcher.handle_incident(inc1)

        yield env.timeout(4.0)
        print(f"\n[{env.now:.1f} min] >>> ALARM: WYPADEK ZESPOŁOWY (WYMAGANE NOSZE) <<<")
        inc2 = Incident("W02_Upadek_Nosze", target_node=8, priority=Priority.HIGH, required_rescuers=2, rescue_duration=25.0)
        incidents.append(inc2)
        dispatcher.handle_incident(inc2)

        yield env.timeout(3.0)
        print(f"\n[{env.now:.1f} min] >>> ALARM KRYTYCZNY: ZATRZYMANIE KRĄŻENIA (RKO) - PROCEDURA TRIAGE <<<")
        inc_crit = Incident("W03_Zawal_RKO", target_node=4, priority=Priority.CRITICAL, required_rescuers=1, rescue_duration=20.0)
        incidents.append(inc_crit)
        dispatcher.handle_incident(inc_crit)

    env.process(mountain_duty_scenario())
    env.run(until=120.0)

    print("\n" + "=" * 80)
    print("                    PODSUMOWANIE DYŻURU GOPR")
    print("=" * 80)
    print(f"Łączny czas trwania dyżuru: {env.now:.1f} minut")
    print(f"Liczba zgłoszeń w kolejce oczekujących: {len(dispatcher.pending_incidents)}")

    print("\nStatus poszkodowanych:")
    for inc in incidents:
        status = "ROZWIĄZANY (Udzielono pomocy)" if inc.is_resolved else "OCZEKUJE W KOLEJCE"
        print(f" - [{inc.priority.name:8s}] {inc.incident_id:22s} -> Status: {status}")

    print("\nKońcowy stan ratowników:")
    for r in dispatcher.rescuers:
        typ = "Ochotnik" if r.is_volunteer else "Zawodowy"
        print(f" - {r.agent_id:15s} ({typ:8s}) | Pozycja: węzeł {r.current_node} | Status: {r.state.value}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Symulacja akcji ratunkowych GOPR (DES + ABM)")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Uruchom prosty model testowy na węzłach numerycznych (0..8)"
    )
    args = parser.parse_args()

    if args.mock:
        run_simple_mock_simulation()
    else:
        # Domyślnie uruchamiamy pełny, efektowny scenariusz na szlakach Gorców
        run_gorce_trails_simulation.main()


if __name__ == "__main__":
    main()
