"""
Moduł Routing:
- routing_interface.py: Kontrakt AbstractRoutingService (get_edge_travel_time, get_path, get_total_time, get_travel_time)
- terrain_routing.py: Rzeczywista implementacja fizyki pojedynczego kroku (get_edge_travel_time) na grafie DEM (Lorentz + WiSAR)
- gorce_trails_network.py: Rzeczywista sieć szlaków Gorców ze zintegrowanym trasowaniem Dijkstry i mapą Leaflet
- mock_routing.py: Serwis testowy do prostych unit-testów
- weather_conditions.py: Modyfikatory meteorologiczne
"""

from src.routing.routing_interface import AbstractRoutingService
from src.routing.mock_routing import MockRoutingService
from src.routing.weather_conditions import WeatherConditions
from src.routing.gorce_trails_network import (
    GorceTrailRoutingService,
    build_gorce_trails_graph,
    GORCE_TRAIL_NODES
)

try:
    from src.routing.terrain_routing import TerrainRoutingService
except ImportError:
    TerrainRoutingService = None

__all__ = [
    "AbstractRoutingService",
    "MockRoutingService",
    "TerrainRoutingService",
    "WeatherConditions",
    "GorceTrailRoutingService",
    "build_gorce_trails_graph",
    "GORCE_TRAIL_NODES",
]
