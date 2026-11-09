#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PROGRAM 2: Budowa grafu rzeźby terenu i lokalny zapis do pliku GraphML.

Funkcjonalność:
- Działa w 100% OFFLINE (nie wymaga połączenia z internetem ani zewnętrznych API).
- Wczytuje przygotowane wcześniej punkty pomiarowe z pliku data/dem/terrain_points.json.
- Buduje skierowany graf przestrzenny (networkx.DiGraph) z 8-kierunkowym sąsiedztwem w siatce.
- Wylicza parametry fizyczne i topograficzne dla każdej krawędzi:
    * distance_2d: odległość w rzucie poziomym [m]
    * distance_3d: rzeczywista długość marszu w przestrzeni 3D [m]
    * elevation_change: przewyższenie dz [m] (+ pod górę, - w dół)
    * slope_degrees: kąt nachylenia stoku w stopniach [-90° do +90°]
    * slope_ratio: tangens kąta stoku (dz / d2d)
    * grade_pct: nachylenie terenu wyrażone w procentach [%]
- Zapisuje graf do uniwersalnego formatu data/trails/gorce_terrain_grid.graphml.
"""

import sys
import argparse
from pathlib import Path

# Dodanie katalogu projektu do sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from src.routing.terrain_graph import TerrainGridGraphBuilder


def main():
    parser = argparse.ArgumentParser(
        description="Program 2: Budowa grafu rzeźby terenu z lokalnych punktów pomiarowych i zapis do GraphML."
    )
    parser.add_argument(
        "--points-file",
        type=str,
        default="data/dem/terrain_points.json",
        help="Ścieżka do pliku wejściowego JSON z punktami terenu (wygenerowanego przez Program 1)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/trails/gorce_terrain_grid.graphml",
        help="Ścieżka do pliku wyjściowego GraphML dla gotowego grafu terenu"
    )

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    points_path = project_root / args.points_file
    output_graph_path = project_root / args.output

    print("=" * 80)
    print(" PROGRAM 2: BUDOWA GRAFU TERENU (OFFLINE)")
    print("=" * 80)
    print(f" Plik wejściowy z danymi: {points_path}")
    print(f" Plik docelowy grafu:     {output_graph_path}")
    print("=" * 80)

    if not points_path.is_file():
        print(f"\n [BŁĄD] Nie znaleziono pliku: {points_path}")
        print(" Najpierw uruchom Program 1, aby pobrać i zapisać dane terenu:")
        print(" -> python 1_download_terrain_data.py --step 100")
        sys.exit(1)

    builder = TerrainGridGraphBuilder(metric_crs="EPSG:2180")

    # Krok 1: Wczytanie punktów pomiarowych z pliku JSON
    points, metadata = builder.load_terrain_points(str(points_path))

    # Krok 2: Konstrukcja sieci połączeń i obliczenie nachyleń krawędzi
    G = builder.build_network_graph(points, metadata=metadata)

    # Krok 3: Zapis gotowego grafu do formatu GraphML
    builder.save_graph(G, str(output_graph_path))

    # Krok 4: Zestawienie statystyk topograficznych
    nodes = list(G.nodes(data=True))
    edges = list(G.edges(data=True))
    elevations = [d["z"] for _, d in nodes]
    slopes = [d["slope_degrees"] for _, _, d in edges]
    dists_3d = [d["distance_3d"] for _, _, d in edges]

    print("\n" + "=" * 80)
    print(" STATYSTYKI WYGENEROWANEGO GRAFU TERENU:")
    print("=" * 80)
    print(f" Liczba węzłów (punktów w siatce):   {len(nodes):,}")
    print(f" Liczba krawędzi (ścieżek marszu):  {len(edges):,}")
    print(f" Średnia łączność węzła:            {len(edges)/len(nodes):.2f} krawędzi/węzeł")
    print(f" Zakres wysokości terenu n.p.m.:    min = {min(elevations):.1f} m, max = {max(elevations):.1f} m")
    print(f" Różnica wysokości (deniwelacja):   {max(elevations) - min(elevations):.1f} m")
    print(f" Maksymalne podejście pod górę:     +{max(slopes):.1f}°")
    print(f" Maksymalne zejście w dół:          {min(slopes):.1f}°")
    print(f" Średnia długość krawędzi 3D:       {sum(dists_3d)/len(dists_3d):.1f} m")
    print(f"\n Plik grafu został pomyślnie zapisany w: {output_graph_path}")
    print(" Możesz teraz uruchomić Program 3 (wizualizacja mapy 3D):")
    print(f" -> python 3_visualize_terrain_3d.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
