import sys
from pathlib import Path

# Dodanie katalogu głównego do ścieżki Pythona, aby importy z 'src' działały bez problemu
sys.path.append(str(Path(__file__).resolve().parent))

import simpy
from src.core.incident import Incident, Priority
from src.core.rescuer import Rescuer
from src.routing.mock_routing import MockRoutingService


def main():
    print("=" * 70)
    print(" START TESTU AGENTA RATOWNIKA (GOPR SIMULATION)")
    print("=" * 70)

    # 1. Tworzymy wirtualne środowisko SimPy (zegar startuje w t=0.0)
    env = simpy.Environment()

    # 2. Tworzymy serwis trasowania (nasz mock: 3 minuty na krawędź)
    routing = MockRoutingService(default_edge_time=3.0)

    # 3. Tworzymy ratownika zawodowego w bazie (węzeł 0)
    rescuer = Rescuer(
        env=env,
        agent_id="GOPR_Ratownik_1",
        base_node=0,
        routing_service=routing,
        speed_factor=1.0,
        is_volunteer=False
    )

    # 4. Tworzymy wypadek: Złamanie na węźle 4 (akcja medyczna: 25 minut)
    incident = Incident(
        incident_id="W01_Zlamanie_Nogi",
        target_node=4,
        priority=Priority.MEDIUM,
        rescue_duration=25.0,
        created_at=env.now
    )

    print(f"\n[Stan początkowy] Pozycja: {rescuer.current_node}, Status: {rescuer.state.value}\n")

    # 5. Przypisujemy wypadek ratownikowi (startuje proces _mission_lifecycle w SimPy)
    rescuer.assign_incident(incident)

    # 6. Uruchamiamy symulację na 120 minut wirtualnego czasu
    env.run(until=120.0)

    print("\n" + "=" * 70)
    print(" PODSUMOWANIE TESTU")
    print("=" * 70)
    print(f"Końcowy czas symulacji: {env.now:.1f} min")
    print(f"Końcowa pozycja ratownika: węzeł {rescuer.current_node} (baza)")
    print(f"Końcowy status ratownika: {rescuer.state.value}")
    print(f"Czy wypadek rozwiązany: {incident.is_resolved}")
    print("=" * 70)


if __name__ == "__main__":
    main()
