"""
Podpakiet rescuer (routing zespołów ratowniczych na grafie terenu):
- terrain_routing.py: TerrainRoutingService (fizyka kroku ratownika wg Campbell & Sullivan + przyszły A*)
"""

from src.routing.rescuer.terrain_routing import TerrainRoutingService

__all__ = ["TerrainRoutingService"]
