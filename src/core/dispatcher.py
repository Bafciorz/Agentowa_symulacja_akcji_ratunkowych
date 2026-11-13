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



    def handle_incident(self, incident: Incident) -> None:
        """
        główna metoda wywoływana gdy wpływa nowe zgłoszenie
        :param incident:
        :return:
        """

        available_rescuers = [
            r for r in self.rescuers if r.state in [RescuerState.IDLE, RescuerState.RETURNING]
        ]

        if available_rescuers:
            best_rescuer = self._find_fastest_rescuer(available_rescuers, incident.target_node)
            self._dispatch_rescuer(best_rescuer, incident)
            return

        if incident.priority >= Priority.HIGH:
            preempted = self._try_preemption(incident)
            if preempted:
                return
        print(f"[{self.env.now:.1f} min] [DYSPOZYTOR] Brak wolnych ratowników! "
              f"Zgłoszenie {incident.incident_id} trafia do kolejki oczekujących.")
        self.pending_incidents.append(incident)
        self.pending_incidents.sort(key=lambda inc: inc.priority, reverse=True)

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