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

    # 5. Dynamiczny scenariusz dyżuru górskiego w Gorcach
    def gorce_duty_scenario():
        print(f"\n[{env.now:.1f} min] >>> ROZPOCZĘCIE DYŻURU OPERACYJNEGO W GORCACH <<<\n")

        # ZDARZENIE 1 (t=0.0): Złamanie ręki na szlaku czerwonym (Polana Gabrowska)
        # 1 ratownik, priorytet LOW
        inc1 = Incident(
            incident_id="W01_Zlamanie_Gabrowska",
            target_node="Polana_Gabrowska",
            priority=Priority.LOW,
            required_rescuers=1,
            rescue_duration=15.0,
            created_at=env.now
        )
        incidents.append(inc1)
        dispatcher.handle_incident(inc1)

        # ZDARZENIE 2 (t=6.0): Wypadek zespołowy na Kiczorze (upadek ze skały)
        # Wymagane nosze alpejskie i 2 ratowników! Priorytet HIGH
        yield env.timeout(6.0)
        print(f"\n[{env.now:.1f} min] >>> ALARM: CIĘŻKI WYPADEK NA KICZORZE (WYMAGANE NOSZE ALPEJSKIE) <<<")
        inc2 = Incident(
            incident_id="W02_Nosze_Kiczora",
            target_node="Kiczora",
            priority=Priority.HIGH,
            required_rescuers=2,
            rescue_duration=20.0,
            created_at=env.now
        )
        incidents.append(inc2)
        dispatcher.handle_incident(inc2)

        # ZDARZENIE 3 (t=12.0): Zdarzenie krytyczne - Nagłe Zatrzymanie Krążenia (NZK) na Hali Długiej!
        # Priorytet CRITICAL -> Dyspozytor musi podjąć decyzję o procedurze TRIAGE (wywłaszczeniu)
        yield env.timeout(6.0)
        print(f"\n[{env.now:.1f} min] >>> ALARM KRYTYCZNY: ZATRZYMANIE KRĄŻENIA (NZK / AED) - PROCEDURA TRIAGE! <<<")
        inc_crit = Incident(
            incident_id="W03_NZK_Hala_Dluga",
            target_node="Hala_Dluga",
            priority=Priority.CRITICAL,
            required_rescuers=1,
            rescue_duration=20.0,
            created_at=env.now
        )
        incidents.append(inc_crit)
        dispatcher.handle_incident(inc_crit)

        # ZDARZENIE 4 (t=18.0): Turysta zgubił się w wiatrołomach w Dolinie Kamienicy poza szlakiem
        # Trudny teren pozaszlakowy (wiatrołomy, zwalone pnie świerkowe)
        yield env.timeout(6.0)
        print(f"\n[{env.now:.1f} min] >>> ZGŁOSZENIE: POSZUKIWANIE POZA SZLAKIEM (WIATROŁOMY KAMIENICY) <<<")
        inc4 = Incident(
            incident_id="W04_Zaginiecie_Wiatrolomy",
            target_node="Dolina_Kamienicy_Wiatrolomy",
            priority=Priority.MEDIUM,
            required_rescuers=1,
            rescue_duration=25.0,
            created_at=env.now
        )
        incidents.append(inc4)
        dispatcher.handle_incident(inc4)

    env.process(gorce_duty_scenario())

    # 6. Uruchomienie zegara symulacji na 180 minut (3-godzinny dyżur)
    env.run(until=180.0)

    # 7. Raport końcowy z przebiegu dyżuru
    print("\n" + "=" * 85)
    print("                     PODSUMOWANIE DYŻURU GOPR GORCE")
    print("=" * 85)
    print(f"Łączny czas trwania dyżuru: {env.now:.1f} minut")
    print(f"Liczba zgłoszeń w kolejce oczekujących dyspozytora: {len(dispatcher.pending_incidents)}")

    print("\nStatus poszkodowanych na szlakach:")
    for inc in incidents:
        loc_name = GORCE_TRAIL_NODES.get(inc.target_node, {}).get("name", inc.target_node)
        if inc.is_resolved:
            status = "ROZWIĄZANY (Udzielono pomocy medycznej)"
        elif any(r.state.name == "ON_SCENE" and r.current_incident == inc for r in dispatcher.rescuers):
            assigned = [r.agent_id for r in dispatcher.rescuers if r.current_incident == inc]
            status = f"W TRAKCIE AKCJI NA MIEJSCU (Ratownicy: {', '.join(assigned)})"
        elif len(inc.assigned_rescuers) >= inc.required_rescuers:
            status = f"W TRAKCIE DOJAZDU (Ratownicy w drodze: {', '.join(inc.assigned_rescuers)})"
        elif len(inc.assigned_rescuers) > 0:
            status = f"CZĘŚCIOWO OBSADZONY (W drodze: {', '.join(inc.assigned_rescuers)}, czeka na wsparcie)"
        else:
            status = "OCZEKUJE W KOLEJCE DYSPOZYTORA"

        print(f" - [{inc.priority.name:8s}] {inc.incident_id:26s} | Miejsce: {loc_name:30s} -> {status}")

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
