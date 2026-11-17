#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skrypt budujący graf rzeźby terenu z lokalnych punktów pomiarowych (OFFLINE)
z integracją szlaków turystycznych i wag czasowych Toblera.
Lokalizacja: data/mappers/build_terrain_graph.py
Uruchomienie:
    python data/mappers/build_terrain_graph.py
"""

import sys
import argparse
from pathlib import Path

# Dołączenie głównego folderu projektu do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.mappers.terrain_mapper import TerrainGraphMapper


def main():
    parser = argparse.ArgumentParser(
        description="Budowa grafu rzeźby terenu z punktów wysokościowych i szlaków (GraphML)."
    )
    parser.add_argument(
        "--points-file",
        type=str,
        default=None,
        help="Ścieżka do pliku JSON z punktami (domyślnie: data/dem/terrain_points.json)"
    )
    parser.add_argument(
        "--trails-file",
        type=str,
        default=None,
        help="Ścieżka do pliku GeoJSON ze szlakami (domyślnie: data/trails/gorce_trails.geojson)"
    )
    parser.add_argument(
        "--trail-buffer",
        type=float,
        default=None,
        help="Szerokość strefy buforowej szlaku w metrach (domyślnie: 35% kroku siatki, min. 25m)"
    )
    parser.add_argument(
        "--off-trail-friction",
        type=float,
        default=4.0,
        help="Współczynnik oporu poruszania się poza szlakiem (domyślnie: 4.0)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Ścieżka do wyjściowego pliku GraphML (domyślnie: data/trails/gorce_terrain_grid.graphml)"
    )

    args = parser.parse_args()

    points_path = Path(args.points_file) if args.points_file else PROJECT_ROOT / "data" / "dem" / "terrain_points.json"
    trails_path = Path(args.trails_file) if args.trails_file else PROJECT_ROOT / "data" / "trails" / "gorce_trails.geojson"
    output_graph_path = Path(args.output) if args.output else PROJECT_ROOT / "data" / "trails" / "gorce_terrain_grid.graphml"

    print("=" * 80)
    print(" BUDOWA GRAFU TERENU ZE SZLAKAMI (MAPPER - 100% OFFLINE)")
    print("=" * 80)
    print(f" Plik wejściowy z punktami: {points_path}")
    print(f" Plik wejściowy szlaków:    {trails_path}")
    print(f" Plik docelowy grafu:       {output_graph_path}")
    print(f" Opór poza szlakiem:        {args.off_trail_friction}x")
    print("=" * 80)

    if not points_path.is_file():
        print(f"\n [BŁĄD] Nie znaleziono pliku: {points_path}")
        print(" Najpierw uruchom pobieranie danych wysokościowych:")
        print(" -> python data/downloaders/download_terrain_data.py --step 100")
        sys.exit(1)

    trails_file_arg = None
    if trails_path.is_file():
        trails_file_arg = str(trails_path)
    else:
        print(f"\n[!] Nie odnaleziono pliku szlaków: {trails_path}")
        print("    Graf zostanie utworzony bez warstwy szlaków (wszystkie krawędzie jako teren pozaszlakowy).")
        print("    Aby uwzględnić szlaki turystyczne, uruchom najpierw:")
        print("    -> python data/downloaders/download_trails_data.py\n")

    mapper = TerrainGraphMapper(metric_crs="EPSG:2180")

    # 1. Odczyt punktów
    points, metadata = mapper.load_terrain_points(str(points_path))

    # 2. Budowa topologii z uwzględnieniem szlaków i oporu terenu
    G = mapper.build_network_graph(
        points,
        metadata=metadata,
        trails_path=trails_file_arg,
        trail_buffer_meters=args.trail_buffer,
        off_trail_friction=args.off_trail_friction
    )

    # 3. Zapis do GraphML
    mapper.save_graph(G, str(output_graph_path))

    # 4. Zestawienie statystyk
    nodes = list(G.nodes(data=True))
    edges = list(G.edges(data=True))
    elevations = [d["z"] for _, d in nodes]
    slopes = [d["slope_degrees"] for _, _, d in edges]
    dists_3d = [d["distance_3d"] for _, _, d in edges]
    trail_nodes = sum(1 for _, d in nodes if d.get("is_trail"))
    trail_edges = sum(1 for _, _, d in edges if d.get("is_trail"))
    travel_times = [d.get("travel_time_min", 0.0) for _, _, d in edges]

    print("\n" + "=" * 80)
    print(" STATYSTYKI WYGENEROWANEGO GRAFU:")
    print("=" * 80)
    print(f" Liczba węzłów (punktów w siatce):   {len(nodes):,}")
    print(f"  * W tym na szlakach:               {trail_nodes:,}")
    print(f" Liczba krawędzi (ścieżek marszu):  {len(edges):,}")
    print(f"  * W tym krawędzie szlaków:        {trail_edges:,}")
    print(f" Średnia łączność węzła:            {len(edges)/len(nodes):.2f} krawędzi/węzeł")
    print(f" Zakres wysokości terenu n.p.m.:    min = {min(elevations):.1f} m, max = {max(elevations):.1f} m")
    print(f" Różnica wysokości (deniwelacja):   {max(elevations) - min(elevations):.1f} m")
    print(f" Maksymalne podejście pod górę:     +{max(slopes):.1f}°")
    print(f" Maksymalne zejście w dół:          {min(slopes):.1f}°")
    print(f" Średnia długość krawędzi 3D:       {sum(dists_3d)/len(dists_3d):.1f} m")
    if travel_times:
        print(f" Średni czas pokonania krawędzi:    {sum(travel_times)/len(travel_times):.2f} min")
    print(f"\n Plik grafu zapisany w: {output_graph_path}")
    print(" Następny krok: uruchom wizualizację mapy 3D (szlaki zaznaczone na czerwono):")
    print(" -> python data/visualizers/visualize_terrain_3d.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
