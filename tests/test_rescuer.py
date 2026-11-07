import simpy
from src.core.incident import Incident, Priority
from src.core.rescuer import Rescuer, RescuerState
from src.routing.mock_routing import MockRoutingService


def test_rescuer_full_lifecycle():
    # 1. Środowisko i routing
    env = simpy.Environment()
    routing = MockRoutingService(default_edge_time=3.0)

    # 2. Ratownik stacjonarny w bazie (węzeł 0)
    rescuer = Rescuer(
        env=env,
        agent_id="GOPR_Test_1",
        base_node=0,
        routing_service=routing,
        speed_factor=1.0,
        is_volunteer=False
    )

    # 3. Wypadek na węźle 4 (akcja: 25 min)
    incident = Incident(
        incident_id="W01_Test",
        target_node=4,
        priority=Priority.MEDIUM,
        rescue_duration=25.0
    )

    # 4. Przypisanie zadania (zwraca proces SimPy)
    mission_process = rescuer.assign_incident(incident)

    # 5. Uruchamiamy symulację dokładnie do zakończenia tej misji:
    env.run(until=mission_process)

    # 6. Asercje matematyczne czasu i stanów:
    # Dojście (0 -> 4) = 4 krawędzie * 3.0 min = 12.0 min
    # Akcja na miejscu = 25.0 min
    # Powrót (4 -> 0) = 4 krawędzie * 3.0 min = 12.0 min
    # Łącznie: 12 + 25 + 12 = 49.0 min
    assert env.now == 49.0
    assert incident.is_resolved is True
    assert rescuer.current_node == 0
    assert rescuer.state == RescuerState.IDLE


def test_volunteer_mobilization():
    env = simpy.Environment()
    routing = MockRoutingService(default_edge_time=3.0)

    # Ratownik ochotnik (dodatkowe 5 minut mobilizacji)
    volunteer = Rescuer(
        env=env,
        agent_id="GOPR_Ochotnik",
        base_node=0,
        routing_service=routing,
        speed_factor=1.0,
        is_volunteer=True
    )

    incident = Incident(
        incident_id="W02_Test_Ochotnik",
        target_node=2,
        priority=Priority.LOW,
        rescue_duration=10.0
    )

    mission_process = volunteer.assign_incident(incident)
    env.run(until=mission_process)

    # Mobilizacja = 5 min
    # Dojście (0 -> 2) = 2 * 3.0 = 6 min
    # Akcja = 10 min
    # Powrót (2 -> 0) = 2 * 3.0 = 6 min
    # Łącznie: 5 + 6 + 10 + 6 = 27.0 min
    assert env.now == 27.0
    assert volunteer.state == RescuerState.IDLE
    assert incident.is_resolved is True
