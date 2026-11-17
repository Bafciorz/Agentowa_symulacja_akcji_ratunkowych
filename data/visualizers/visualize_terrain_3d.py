#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skrypt generujący trójwymiarową interaktywną wizualizację terenu (HTML WebGL).
Lokalizacja: data/visualizers/visualize_terrain_3d.py
Uruchomienie:
    python data/visualizers/visualize_terrain_3d.py
"""

import sys
import argparse
from pathlib import Path

# Dołączenie głównego folderu projektu do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.mappers.terrain_mapper import TerrainGraphMapper
from data.visualizers.terrain_visualizer import export_3d_interactive_html


def main():
    parser = argparse.ArgumentParser(
        description="Trójwymiarowa interaktywna mapa 3D (HTML/WebGL) terenu z grafu."
    )
    parser.add_argument(
        "--graph",
        type=str,
        default=None,
        help="Ścieżka do pliku GraphML (domyślnie: data/trails/gorce_terrain_grid.graphml)"
    )
    parser.add_argument(
        "--output",
        "--output-html",
        dest="output_html",
        type=str,
        default=None,
        help="Ścieżka do wyjściowego pliku HTML (domyślnie: data/trails/gorce_terrain_3d.html)"
    )

    args = parser.parse_args()

    graph_path = Path(args.graph) if args.graph else PROJECT_ROOT / "data" / "trails" / "gorce_terrain_grid.graphml"
    output_html_path = Path(args.output_html) if args.output_html else PROJECT_ROOT / "data" / "trails" / "gorce_terrain_3d.html"

    print("=" * 80)
    print(" INTERAKTYWNA WIZUALIZACJA 3D TERENU (HTML / WEBGL)")
    print("=" * 80)
    print(f" Plik wejściowy grafu:  {graph_path}")
    print(f" Plik modelu 3D HTML:   {output_html_path}")
    print("=" * 80)

    if not graph_path.is_file():
        print(f"\n [BŁĄD] Nie znaleziono pliku grafu: {graph_path}")
        print(" Najpierw zbuduj graf z pobranych punktów:")
        print(" -> python data/mappers/build_terrain_graph.py")
        sys.exit(1)

    mapper = TerrainGraphMapper(metric_crs="EPSG:2180")

    # 1. Odczyt grafu
    G = mapper.load_graph(str(graph_path))
    area_name = G.graph.get("area_name", "Rejon Operacyjny GOPR - Gorce")

    # 2. Eksport interaktywnego modelu 3D WebGL (Three.js) do pliku HTML
    print("\n[*] Generowanie interaktywnego modelu 3D WebGL (Three.js -> HTML)...")
    export_3d_interactive_html(
        graph=G,
        output_html_path=str(output_html_path),
        title=f"Model Rzeźby Terenu 3D - {area_name}"
    )

    print("\n" + "=" * 80)
    print(" WIZUALIZACJA UKOŃCZONA SUKCESEM!")
    print("=" * 80)
    print(f" Interaktywna mapa 3D:  {output_html_path}")
    print(" -> Otwórz plik w dowolnej przeglądarce (Chrome, Edge, Firefox).")
    print(" -> Szlaki turystyczne i ich węzły są wyróżnione na CZERWONO.")
    print(" -> Obracaj model myszką, przybliżaj i przełączaj widoczność szlaków oraz siatki.")
    print(" -> Użyj przycisku 'Schowaj' w prawym górnym rogu panelu, aby ukryć okno informacyjne.")
    print("=" * 80)


if __name__ == "__main__":
    main()
