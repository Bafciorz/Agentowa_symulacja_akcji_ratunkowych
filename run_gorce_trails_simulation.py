#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SYMULACJA SYSTEMÓW DYSKRETNYCH: AKCJE RATUNKOWE GOPR (DES + ABM)
Scenariusz prezentacyjny dla prowadzącego:
- Rzeczywista sieć szlaków Gorców (GSB, szlak żółty, zielony, teren pozaszlakowy)
- Fizyka marszu Campbell & Sullivan (asymetryczna krzywa Lorentza dla podejść/zejść)
- Warunki atmosferyczne WeatherConditions (śnieg, wiatr, widoczność)
- Wieloratownicza koordynacja z barierą simpy.AllOf (nosze)
- Procedura wywłaszczenia Triage (nagłe zatrzymanie krążenia)
- Automatyczny eksport interaktywnej mapy akcji do pliku HTML (Leaflet / OpenTopoMap)
"""

import sys
from pathlib import Path

# Dodanie katalogu głównego do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import simpy
from src.core.dispatcher import Dispatcher
from src.core.incident import Incident, Priority
from src.core.rescuer import Rescuer
from src.core.stochastic_generator import (
    StochasticIncidentGenerator,
    stochastic_incident_stream
)
from src.routing import (
    GorceTrailRoutingService,
    WeatherConditions,
    GORCE_TRAIL_NODES
)


def main():
    print("=" * 85)
    print("     SYMULACJA AGENTOWA GOPR GORCE (DES SimPy + GIS Campbell-Sullivan)")
    print("     Scenariusz Pokazowy: Główne Szlaki, Triage, Zespół Noszowy i Mapa Topo")
    print("=" * 85)

    # 1. Środowisko zdarzeń dyskretnych SimPy
    env = simpy.Environment()

    # 2. Zimowe/jesienne warunki atmosferyczne w Gorcach
    weather = WeatherConditions(
        rain_mm_h=0.0,
        snow_cm=8.0,        # 8 cm pokrywy śnieżnej (redukcja tempa o 20%)
        wind_kmh=35.0,      # Porywisty wiatr na grani (redukcja o 12%)
        visibility_m=300.0  # Umiarkowana mgła
    )
    print(f"[*] Warunki pogodowe: Śnieg: {weather.snow_cm} cm | Wiatr: {weather.wind_kmh} km/h | Mnożnik pogody: {weather.env_modifier:.2f}x")

    # 3. Serwis trasowania po szlakach Gorców
    routing = GorceTrailRoutingService(default_weather=weather)

    # 4. Rozmieszczenie ratowników w bazach GOPR:
    # W Stacji Centralnej na Turbaczu stacjonuje 2 ratowników dyżurnych (zespół stacjonarny).
    # W dolnej stacji Kowaniec stacjonuje patrol zmotoryzowany (quad gąsienicowy / skuter śnieżny).
    # Na Starych Wierchach stacjonuje ratownik ochotnik.
    rescuer_alfa = Rescuer(
        env,
        agent_id="GOPR_Alfa",
        base_node="Schronisko_Turbacz",
        routing_service=routing,
        speed_factor=1.15,
        is_volunteer=False
    )
    rescuer_brawo = Rescuer(
        env,
        agent_id="GOPR_Brawo",
        base_node="Schronisko_Turbacz",
        routing_service=routing,
        speed_factor=1.10,
        is_volunteer=False
    )
    rescuer_quad = Rescuer(
        env,
        agent_id="GOPR_Quad",
        base_node="Kowaniec_NowyTarg",
        routing_service=routing,
        speed_factor=2.6,  # Pojazd gąsienicowy / skuter śnieżny GOPR do szybkiego wjazdu na grań
        is_volunteer=False
    )
    rescuer_ochotnik = Rescuer(
        env,
        agent_id="GOPR_Ochotnik",
        base_node="Stare_Wierchy",
        routing_service=routing,
        speed_factor=1.05,
        is_volunteer=True
    )

    rescuers = [rescuer_alfa, rescuer_brawo, rescuer_quad, rescuer_ochotnik]
    dispatcher = Dispatcher(env, rescuers, routing_service=routing)

    incidents = []

    # 5. Stochastyczny generator napływu wezwań (Proces Poissona + Wagi Węzłów + Triage)
    # Start o 10:00 (szczyt turystyczny), średni czas między zgłoszeniami: 40 min na potrzeby demonstracji
    generator = StochasticIncidentGenerator(
        seed=42,
        start_hour=10.0,
        peak_mean=40.0,
        off_peak_mean=120.0
    )

    print(f"\n[{env.now:.1f} min] >>> ROZPOCZĘCIE DYŻURU OPERACYJNEGO GOPR W GORCACH (STOCHASTIC DES) <<<")
    print(f"[*] Generator wezwań: Niejednorodny proces Poissona (NHPP), seed=42")
    print(f"[*] Dyspozytor Triage: Aktywny (wywłaszczanie CRITICAL, koordynacja noszy AllOf)\n")

    # Uruchomienie dynamicznego strumienia zdarzeń
    env.process(
        stochastic_incident_stream(
            env=env,
            dispatcher=dispatcher,
            generator=generator,
            run_until=240.0,
            collected_incidents=incidents
        )
    )

    # 6. Uruchomienie zegara symulacji na 300 minut (5 godzin dyżuru z buforem powrotu)
    env.run(until=300.0)

    # 7. Raport końcowy z przebiegu dyżuru
    print("\n" + "=" * 85)
    print("                     PODSUMOWANIE DYŻURU GOPR GORCE")
    print("=" * 85)
    print(f"Łączny czas trwania dyżuru: {env.now:.1f} minut")
    print(f"Liczba zarejestrowanych zgłoszeń: {len(incidents)}")
    print(f"Liczba zgłoszeń w kolejce oczekujących dyspozytora: {len(dispatcher.pending_incidents)}")

    resolved_incidents = [inc for inc in incidents if inc.is_resolved]
    response_times = [inc.response_time for inc in incidents if inc.response_time is not None]

    print(f"Skuteczność pomocy: {len(resolved_incidents)}/{len(incidents)} wypadków w pełni zaopatrzonych")
    if response_times:
        import numpy as np
        mean_t = np.mean(response_times)
        p95_t = np.percentile(response_times, 95)
        print(f"Średni czas dotarcia do poszkodowanego (Mean Response Time): {mean_t:.1f} min")
        print(f"95-percentyl czasu dotarcia (P95 Response Time): {p95_t:.1f} min")

    print("\nRejestr zdarzeń ratunkowych na szlakach Gorców:")
    for inc in incidents:
        loc_name = GORCE_TRAIL_NODES.get(inc.target_node, {}).get("name", inc.target_node)
        resp_str = f"{inc.response_time:.1f} min" if inc.response_time is not None else "W drodze / Kolejka"
        if inc.is_resolved:
            status = f"[ROZWIĄZANY] (Czas dotarcia: {resp_str})"
        elif any(r.state.name == "ON_SCENE" and r.current_incident == inc for r in dispatcher.rescuers):
            assigned = [r.agent_id for r in dispatcher.rescuers if r.current_incident == inc]
            status = f"[W TRAKCIE AKCJI] (Ratownicy: {', '.join(assigned)}, dotarcie: {resp_str})"
        elif len(inc.assigned_rescuers) >= inc.required_rescuers:
            status = f"[W TRAKCIE DOJAZDU] (Ratownicy w drodze: {', '.join(inc.assigned_rescuers)})"
        elif len(inc.assigned_rescuers) > 0:
            status = f"[CZĘŚCIOWO OBSADZONY] (W drodze: {', '.join(inc.assigned_rescuers)}, czeka na wsparcie)"
        else:
            status = "[OCZEKUJE W KOLEJCE]"

        print(f" - [{inc.priority.name:8s}] {inc.incident_id:28s} | {loc_name:30s} -> {status}")
        print(f"   Opis: {inc.description} (Wymaganych: {inc.required_rescuers}, Czas akcji: {inc.rescue_duration} min)")

    print("\nKońcowy stan ratowników:")
    for r in dispatcher.rescuers:
        typ = "Ochotnik" if r.is_volunteer else "Zawodowy"
        loc_name = GORCE_TRAIL_NODES.get(r.current_node, {}).get("name", r.current_node)
        print(f" - {r.agent_id:15s} ({typ:8s}) | Pozycja: {loc_name:30s} | Status: {r.state.value}")

    # 8. Generowanie interaktywnej mapy HTML Leaflet
    map_file = PROJECT_ROOT / "gorce_rescue_map.html"
    routing.generate_interactive_map(str(map_file), incidents=incidents)
    print("\n" + "=" * 85)
    print(f"[MAPA] Interaktywna mapa topograficzna akcji została pomyślnie wygenerowana:")
    print(f"       -> {map_file}")
    print("       Otwórz ten plik podwójnym kliknięciem w przeglądarce, aby pokazać prowadzącemu")
    print("       poziomice Gorców, przebieg szlaków, bazy GOPR oraz lokalizacje wypadków!")
    print("=" * 85)


if __name__ == "__main__":
    main()
