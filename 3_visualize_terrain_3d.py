#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PROGRAM 3: Trójwymiarowa wizualizacja i interaktywna mapa 3D terenu.

Funkcjonalność:
- Działa w 100% OFFLINE (wczytuje wygenerowany graf z pliku GraphML).
- Generuje interaktywny model 3D WebGL (plik HTML) z silnikiem Three.js:
    * Swobodny obrót myszą o 360°, przesuwanie (pan) i przybliżanie (zoom).
    * Ciągła powierzchnia rzeźby terenu z realistycznym cieniowaniem wysokościowym (dolina -> las -> polany -> skały).
    * Opcja włączenia siatki krawędzi (Wireframe).
    * Dynamiczny panel informacyjny (HUD) z parametrami rzeźby i statystykami.
- Generuje render 3D (plik PNG) przy użyciu Matplotlib Triangulation.
- Opcjonalnie otwiera interaktywne okno pulpitu 3D Matplotlib (--show).
"""

import sys
import argparse
from pathlib import Path

# Dodanie katalogu projektu do sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from src.routing.terrain_graph import TerrainGridGraphBuilder
from src.routing.terrain_visualizer import plot_3d_matplotlib, export_3d_interactive_html, get_graph_step_meters


def main():
    parser = argparse.ArgumentParser(
        description="Program 3: Trójwymiarowa wizualizacja i interaktywna mapa 3D terenu z grafu."
    )
    parser.add_argument(
        "--graph",
        type=str,
        default="data/trails/gorce_terrain_grid.graphml",
        help="Ścieżka do pliku wejściowego GraphML (wygenerowanego przez Program 2)"
    )
    parser.add_argument(
        "--output-html",
        type=str,
        default="data/trails/gorce_terrain_3d.html",
        help="Ścieżka do pliku wyjściowego interaktywnej mapy 3D (HTML WebGL)"
    )
    parser.add_argument(
        "--output-png",
        type=str,
        default="data/trails/gorce_3d_terrain.png",
        help="Ścieżka do pliku wyjściowego renderu 3D (PNG)"
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

    project_root = Path(__file__).resolve().parent
    graph_path = project_root / args.graph
    output_html_path = project_root / args.output_html
    output_png_path = project_root / args.output_png

    print("=" * 80)
    print(" PROGRAM 3: WIZUALIZACJA I EKSPLORACJA MAPY 3D TERENU")
    print("=" * 80)
    print(f" Plik wejściowy grafu:      {graph_path}")
    print(f" Plik modelu 3D HTML:       {output_html_path}")
    print(f" Plik renderu 3D PNG:       {output_png_path}")
    print("=" * 80)

    if not graph_path.is_file():
        print(f"\n [BŁĄD] Nie znaleziono pliku grafu: {graph_path}")
        print(" Najpierw uruchom Program 2, aby zbudować graf terenu:")
        print(" -> python 2_build_terrain_graph.py")
        sys.exit(1)

    builder = TerrainGridGraphBuilder(metric_crs="EPSG:2180")

    # Krok 1: Wczytanie grafu z pliku GraphML
    G = builder.load_graph(str(graph_path))

    area_name = G.graph.get("area_name", "Gorce - Park Narodowy")
    step_meters = get_graph_step_meters(G)

    # Krok 2: Renderowanie statycznego wykresu 3D do pliku PNG
    print("\n[1/2] Generowanie renderu rzeźby terenu (Matplotlib 3D -> PNG)...")
    plot_3d_matplotlib(
        graph=G,
        save_path=str(output_png_path),
        show=args.show,
        title=f"Rzeźba Terenu 3D - {area_name} (siatka co {step_meters:.0f}m)"
    )

    # Krok 3: Eksport interaktywnego modelu 3D WebGL (Three.js) do pliku HTML
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
        print("    -> Kliknij dwukrotnie w plik HTML lub otwórz go w przeglądarce (Chrome, Edge, Firefox)")
        print("    -> Możesz obracać model terenu myszką o 360°, przybliżać i włączać siatkę krawędzi!")
    print("=" * 80)


if __name__ == "__main__":
    main()
