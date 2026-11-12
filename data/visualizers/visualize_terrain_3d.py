#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skrypt generujący trójwymiarową wizualizację terenu (HTML WebGL oraz PNG).
Lokalizacja: data/visualizers/visualize_terrain_3d.py
Uruchomienie:
    python data/visualizers/visualize_terrain_3d.py
    python data/visualizers/visualize_terrain_3d.py --show
"""

import sys
import argparse
from pathlib import Path

# Dołączenie głównego folderu projektu do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.mappers.terrain_mapper import TerrainGraphMapper
from data.visualizers.terrain_visualizer import (
    plot_3d_matplotlib,
    export_3d_interactive_html,
    get_graph_step_meters
)


def main():
    parser = argparse.ArgumentParser(
        description="Trójwymiarowa wizualizacja i interaktywna mapa 3D terenu z grafu."
    )
    parser.add_argument(
        "--graph",
        type=str,
        default=None,
        help="Ścieżka do pliku GraphML (domyślnie: data/trails/gorce_terrain_grid.graphml)"
    )
    parser.add_argument(
        "--output-html",
        type=str,
        default=None,
        help="Ścieżka do wyjściowego pliku HTML (domyślnie: data/trails/gorce_terrain_3d.html)"
    )
    parser.add_argument(
        "--output-png",
        type=str,
        default=None,
        help="Ścieżka do wyjściowego pliku PNG (domyślnie: data/trails/gorce_3d_terrain.png)"
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Otwiera interaktywne okno 3D na pulpicie (Matplotlib)"
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Wyłącza generowanie pliku HTML"
    )

    args = parser.parse_args()

    graph_path = Path(args.graph) if args.graph else PROJECT_ROOT / "data" / "trails" / "gorce_terrain_grid.graphml"
    output_html_path = Path(args.output_html) if args.output_html else PROJECT_ROOT / "data" / "trails" / "gorce_terrain_3d.html"
    output_png_path = Path(args.output_png) if args.output_png else PROJECT_ROOT / "data" / "trails" / "gorce_3d_terrain.png"

    print("=" * 80)
    print(" WIZUALIZACJA I EKSPLORACJA MAPY 3D TERENU (VISUALIZER)")
    print("=" * 80)
    print(f" Plik wejściowy grafu:      {graph_path}")
    print(f" Plik modelu 3D HTML:       {output_html_path}")
    print(f" Plik renderu 3D PNG:       {output_png_path}")
    print("=" * 80)

    if not graph_path.is_file():
        print(f"\n [BŁĄD] Nie znaleziono pliku grafu: {graph_path}")
        print(" Najpierw zbuduj graf z pobranych punktów:")
        print(" -> python data/mappers/build_terrain_graph.py")
        sys.exit(1)

    mapper = TerrainGraphMapper(metric_crs="EPSG:2180")

    # 1. Odczyt grafu
    G = mapper.load_graph(str(graph_path))

    area_name = G.graph.get("area_name", "Gorce - Park Narodowy")
    step_meters = get_graph_step_meters(G)

    # 2. Renderowanie statycznego wykresu 3D do pliku PNG
    print("\n[1/2] Generowanie renderu rzeźby terenu (Matplotlib 3D -> PNG)...")
    plot_3d_matplotlib(
        graph=G,
        save_path=str(output_png_path),
        show=args.show,
        title=f"Rzeźba Terenu 3D - {area_name} (siatka co {step_meters:.0f}m)"
    )

    # 3. Eksport interaktywnego modelu 3D WebGL (Three.js) do pliku HTML
    if not args.no_html:
        print("\n[2/2] Generowanie interaktywnego modelu 3D WebGL (Three.js -> HTML)...")
        export_3d_interactive_html(
            graph=G,
            output_html_path=str(output_html_path),
            title=f"Model Rzeźby Terenu 3D - {area_name}"
        )

    print("\n" + "=" * 80)
    print(" WIZUALIZACJA UKOŃCZONA SUKCESEM!")
    print("=" * 80)
    print(f" 1. Statyczny obraz 3D:    {output_png_path}")
    if not args.no_html:
        print(f" 2. Interaktywna mapa 3D:  {output_html_path}")
        print("    -> Kliknij dwukrotnie w plik HTML lub otwórz w przeglądarce (Chrome, Edge, Firefox)")
        print("    -> Możesz obracać model myszką o 360°, przybliżać i włączać siatkę krawędzi!")
    print("=" * 80)


if __name__ == "__main__":
    main()
