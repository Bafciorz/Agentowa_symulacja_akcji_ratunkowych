import sys
from pathlib import Path

# Dodanie katalogu głównego do ścieżki Pythona, aby importy z 'src' działały bez problemu
sys.path.append(str(Path(__file__).resolve().parent))

import simpy
from src.core.dispatcher import Dispatcher
from src.core.incident import Incident, Priority
from src.core.rescuer import Rescuer
from src.routing.mock_routing import MockRoutingService


def main():
    print("=" * 80)
    print("      SYMULACJA SYSTEMÓW DYSKRETNYCH: AKCJE RATUNKOWE GOPR (DES + ABM)")
    print("      Scenariusz: Koordynacja zespołowa (simpy.AllOf), Triage & Kolejka")
    print("=" * 80)

    # 1. Zegar symulacji zdarzeń dyskretnych (start w t=0.0 min)
    env = simpy.Environment()

    # 2. Serwis trasowania (węzły szlaków, 3 min/krawędź)
    routing = MockRoutingService(default_edge_time=3.0)

    # 3. Rozmieszczenie ratowników w 2 stacjach GOPR:
    # - Baza 0: Stacja Centralna (np. Rabka-Zdrój)
    # - Baza 3: Stacja Sezonowa (np. Schronisko Turbacz)
    rescuer_1 = Rescuer(env, "GOPR_Alfa", base_node=0, routing_service=routing, speed_factor=1.0)
    rescuer_2 = Rescuer(env, "GOPR_Brawo", base_node=3, routing_service=routing, speed_factor=1.2)
    rescuer_vol = Rescuer(env, "GOPR_Ochotnik", base_node=0, routing_service=routing, speed_factor=0.9, is_volunteer=True)

    rescuers = [rescuer_1, rescuer_2, rescuer_vol]

    # 4. Centralny dyspozytor
    dispatcher = Dispatcher(env, rescuers, routing_service=routing)

    # Lista incydentów do podsumowania
    incidents = []

    # 5. Scenariusz dyżuru górskiego generowany w czasie symulacji:
    def mountain_duty_scenario():
        print(f"\n[{env.now:.1f} min] >>> START DYŻURU GOPR W GORCACH <<<\n")

        # ZDARZENIE 1 (t=0.0): Skręcenie kostki (LOW) na szlaku, węzeł 5
        inc1 = Incident("W01_Skrecenie_Kostki", target_node=5, priority=Priority.LOW, required_rescuers=1, rescue_duration=15.0)
        incidents.append(inc1)
        dispatcher.handle_incident(inc1)

        # ZDARZENIE 2 (t=4.0): Wypadek zespołowy (HIGH) - upadek z wysokości, wymagane nosze alpejskie (2 ratowników)
        yield env.timeout(4.0)
        print(f"\n[{env.now:.1f} min] >>> ALARM: WYPADEK ZESPOŁOWY (WYMAGANE NOSZE) <<<")
        inc2 = Incident("W02_Upadek_Nosze", target_node=8, priority=Priority.HIGH, required_rescuers=2, rescue_duration=25.0)
        incidents.append(inc2)
        dispatcher.handle_incident(inc2)

        # ZDARZENIE 3 (t=7.0): Zdarzenie krytyczne (CRITICAL) - Nagłe Zatrzymanie Krążenia (RKO) w węźle 4!
        # Brak wolnych ratowników -> Dyspozytor musi podjąć decyzję o TRIAGE (wywłaszczeniu)
        yield env.timeout(3.0)
        print(f"\n[{env.now:.1f} min] >>> ALARM KRYTYCZNY: ZATRZYMANIE KRĄŻENIA (RKO) - PROCEDURA TRIAGE <<<")
        inc_crit = Incident("W03_Zawal_RKO", target_node=4, priority=Priority.CRITICAL, required_rescuers=1, rescue_duration=20.0)
        incidents.append(inc_crit)
        dispatcher.handle_incident(inc_crit)

    env.process(mountain_duty_scenario())

    # 6. Uruchomienie symulacji na 120 minut wirtualnego czasu
    env.run(until=120.0)

    # 7. Raport końcowy z przebiegu akcji
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


if __name__ == "__main__":
    main()