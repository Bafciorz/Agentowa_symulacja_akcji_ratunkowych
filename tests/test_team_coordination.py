import simpy

from src.core.incident import Incident, Priority
from src.core.rescuer import Rescuer, RescuerState
from src.core.dispatcher import Dispatcher
from src.routing.mock_routing import MockRoutingService


def test_multi_rescuer_coordination_simpy_allof():
    """
    Weryfikacja bariery simpy.AllOf:
    - Wypadek na węźle 6 wymaga 2 ratowników (nosze).
    - Ratownik A (z bazy 0): 6 krawędzi * 3 min = 18.0 min marszu.
    - Ratownik B (z bazy 2): 4 krawędzie * 3 min = 12.0 min marszu.
    - Czas akcji: 20.0 min.
    """
    env = simpy.Environment()
    routing = MockRoutingService(default_edge_time=3.0)

    rescuer_a = Rescuer(env, "GOPR_Alfa", base_node=0, routing_service=routing)
    rescuer_b = Rescuer(env, "GOPR_Beta", base_node=2, routing_service=routing)
    dispatcher = Dispatcher(env, [rescuer_a, rescuer_b], routing_service=routing)

    incident = Incident(
        incident_id="W_Nosze_Zespol",
        target_node=6,
        priority=Priority.HIGH,
        required_rescuers=2,
        rescue_duration=20.0
    )

    dispatcher.handle_incident(incident)

    # 1. W minucie 15.0: Ratownik B już czeka na miejscu, Ratownik A wciąż idzie
    env.run(until=15.0)
    assert rescuer_b.current_node == 6
    assert rescuer_b.state == RescuerState.ON_SCENE
    assert rescuer_a.state == RescuerState.EN_ROUTE
    assert incident.is_resolved is False

    # 2. W minucie 37.9: Zespół działa razem na miejscu (od 18.0 minuty), akcja jeszcze trwa
    env.run(until=37.9)
    assert rescuer_a.state == RescuerState.ON_SCENE
    assert rescuer_b.state == RescuerState.ON_SCENE
    assert incident.is_resolved is False

    # 3. W minucie 38.1 (18.0 + 20.0 = 38.0 min): Akcja zakończona sukcesem!
    env.run(until=38.1)
    assert incident.is_resolved is True


def test_dispatcher_queue_and_automatic_redeployment():
    """
    Weryfikacja kolejki FIFO: oba wypadki mają ten sam priorytet (LOW),
    więc ratownik najpierw kończy W01, a potem automatycznie podejmuje W02
    bez powrotu do bazy.
    """
    env = simpy.Environment()
    routing = MockRoutingService(default_edge_time=3.0)

    rescuer = Rescuer(env, "GOPR_Alfa", base_node=0, routing_service=routing)
    dispatcher = Dispatcher(env, [rescuer], routing_service=routing)

    # Dwa zgłoszenia o tym samym priorytecie (brak wywłaszczenia triage)
    inc1 = Incident("W01_Kostka", target_node=4, priority=Priority.LOW, rescue_duration=15.0, created_at=0.0)
    inc2 = Incident("W02_Kolano", target_node=6, priority=Priority.LOW, rescue_duration=10.0, created_at=2.0)

    def scenario():
        dispatcher.handle_incident(inc1)
        yield env.timeout(2.0)
        dispatcher.handle_incident(inc2)
        # Zgłoszenie 2 musi trafić do kolejki (brak wolnych ratowników)
        assert len(dispatcher.pending_incidents) == 1

    env.process(scenario())

    # Dojście do W01 (12 min) + Akcja (15 min) = 27.0 min.
    # W minucie 27.1 ratownik zakończył W01 i pobrał W02 prosto z węzła 4 do węzła 6 (2 krawędzie = 6 min)!
    env.run(until=27.1)
    assert inc1.is_resolved is True
    assert rescuer.current_node == 4
    assert rescuer.current_incident == inc2
    assert len(dispatcher.pending_incidents) == 0

    # W minucie 33.1 (27 + 6 = 33): Dotarł na miejsce W02
    env.run(until=33.1)
    assert rescuer.current_node == 6
    assert rescuer.state == RescuerState.ON_SCENE


def test_multi_rescuer_preemption_triage():
    """
    Weryfikacja Triage: wywłaszczenie ratownika ze zgłoszenia LOW do CRITICAL.
    """
    env = simpy.Environment()
    routing = MockRoutingService(default_edge_time=3.0)

    r1 = Rescuer(env, "GOPR_1", base_node=0, routing_service=routing)
    dispatcher = Dispatcher(env, [r1], routing_service=routing)

    inc_low = Incident("W_Kostka", target_node=5, priority=Priority.LOW, rescue_duration=10.0)
    inc_crit = Incident("W_RKO", target_node=3, priority=Priority.CRITICAL, rescue_duration=15.0)

    def scenario():
        dispatcher.handle_incident(inc_low)
        yield env.timeout(4.0)  # po 4 minutach marszu wpływa zatrzymanie krążenia!
        dispatcher.handle_incident(inc_crit)

    env.process(scenario())
    env.run(until=5.0)

    # Ratownik natychmiast przekierowany do RKO, a skręcona kostka wraca do kolejki:
    assert r1.current_incident == inc_crit
    assert len(dispatcher.pending_incidents) == 1
    assert inc_low in dispatcher.pending_incidents
