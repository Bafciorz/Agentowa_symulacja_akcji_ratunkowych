from typing import List

import simpy

from src.core.incident import Incident, Priority
from src.core.rescuer import Rescuer, RescuerState
from src.routing.routing_interface import AbstractRoutingService


class Dispatcher:
    def __init__(
            self,
            env: simpy.Environment,
            rescuers: List[Rescuer],
            routing_service: AbstractRoutingService
    ):
        self.env = env
        self.rescuers = rescuers

        self.routing_service = routing_service
        self.pending_incidents : List[Incident] = []
        for r in self.rescuers:
            r.dispatcher = self

    def handle_incident(self, incident: Incident) -> None:
        """Główna metoda wywoływana, gdy wpływa nowe zgłoszenie."""
        incident.init_events(self.env)

        # 1. Sprawdzamy ilu ratowników jeszcze potrzeba do tego wypadku
        needed = incident.required_rescuers - len(incident.assigned_rescuers)
        if needed <= 0:
            return

        print(
            f"[{self.env.now:.1f} min] [DYSPOZYTOR] Zgłoszenie: {incident.incident_id} w węźle {incident.target_node} "
            f"({incident.priority.name}, wymaganych: {incident.required_rescuers}).")

        # 2. Szukamy dostępnych ratowników (w bazie IDLE lub powracających RETURNING)
        available = [r for r in self.rescuers if r.state in [RescuerState.IDLE, RescuerState.RETURNING]]

        if available:
            # Sortujemy ratowników według najkrótszego czasu dotarcia (ETA)
            available.sort(key=lambda r: self.routing_service.get_travel_time(r.current_node, incident.target_node,
                                                                              r.speed_factor))
            to_dispatch = available[:needed]
            for rescuer in to_dispatch:
                self._dispatch_rescuer(rescuer, incident)
            needed = incident.required_rescuers - len(incident.assigned_rescuers)

        # 3. Jeśli nadal brakuje ratowników, a priorytet jest wysoki -> triage / wywłaszczenie
        if needed > 0 and incident.priority >= Priority.HIGH:
            if self._try_preemption(incident):
                needed -= 1

        # 4. Jeśli nadal brakuje ratowników -> zgłoszenie trafia do kolejki oczekujących
        if needed > 0:
            if incident not in self.pending_incidents:
                print(f"[{self.env.now:.1f} min] [DYSPOZYTOR] Zgłoszenie {incident.incident_id} "
                      f"wymaga jeszcze {needed}/{incident.required_rescuers} ratowników. Trafia do kolejki.")
                self.pending_incidents.append(incident)
                self.pending_incidents.sort(key=lambda inc: int(inc.priority), reverse=True)
        else:
            if incident in self.pending_incidents:
                self.pending_incidents.remove(incident)

    def _find_fastest_rescuer(self, candidates: List[Rescuer], target_node) -> Rescuer:
        return min(
            candidates,
            key=lambda r: self.routing_service.get_travel_time(r.current_node, target_node, r.speed_factor)
        )

    def _dispatch_rescuer(self, rescuer: Rescuer, incident: Incident):
        if rescuer.state == RescuerState.RETURNING and rescuer.process and rescuer.process.is_alive:
            rescuer.process.interrupt(f"Przekierowanie z powrotu do {incident.incident_id}")
            rescuer.assign_incident(incident)
        else:
            rescuer.assign_incident(incident)

    def _try_preemption(self, critical_incident: Incident) -> bool:
        candidates = [
            r for r in self.rescuers
            if r.state == RescuerState.EN_ROUTE
               and r.current_incident
               and r.current_incident.priority < critical_incident.priority
        ]
        if not candidates:
            return False
        victim_rescuer = min(candidates, key=lambda r: r.current_incident.priority)
        old_incident = victim_rescuer.current_incident
        print(f"[{self.env.now:.1f} min] [TRIAGE PREEMPTION] Wywłaszczenie {victim_rescuer.agent_id}! "
              f"Porzuca {old_incident.incident_id} ({old_incident.priority.name}) "
              f"-> Przekierowany do {critical_incident.incident_id} ({critical_incident.priority.name})!")
        self.pending_incidents.append(old_incident)
        self.pending_incidents.sort(key=lambda inc: inc.priority, reverse=True)
        if victim_rescuer.process and victim_rescuer.process.is_alive:
            victim_rescuer.process.interrupt(f"Triage: {critical_incident.incident_id}")
            victim_rescuer.assign_incident(critical_incident)
            return True
        return False

    def notify_rescuer_available(self, rescuer: Rescuer) -> bool:
        """
        Wywoływane automatycznie przez ratownika, gdy skończył akcję lub wrócił do bazy.
        Jeśli w kolejce czeka wypadek, natychmiast przydziela mu nowe zadanie.
        """
        # Czyścimy z kolejki wypadki już rozwiązane
        self.pending_incidents = [inc for inc in self.pending_incidents if not inc.is_resolved]
        if not self.pending_incidents:
            return False

        # Sortujemy kolejkę po priorytecie (najważniejsze pierwsze)
        self.pending_incidents.sort(key=lambda inc: int(inc.priority), reverse=True)

        for incident in list(self.pending_incidents):
            if rescuer.agent_id in incident.assigned_rescuers:
                continue

            needed = incident.required_rescuers - len(incident.assigned_rescuers)
            if needed > 0:
                print(f"[{self.env.now:.1f} min] [DYSPOZYTOR] Ratownik {rescuer.agent_id} pobiera z kolejki "
                      f"zgłoszenie {incident.incident_id} ({incident.priority.name}) "
                      f"[{len(incident.assigned_rescuers) + 1}/{incident.required_rescuers} ratowników]!")
                self._dispatch_rescuer(rescuer, incident)

                if len(incident.assigned_rescuers) >= incident.required_rescuers:
                    self.pending_incidents.remove(incident)
                return True

        return False