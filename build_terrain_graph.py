import sys
import argparse
from pathlib import Path

# Dodanie katalogu projektu do ścieżki Pythona
sys.path.append(str(Path(__file__).resolve().parent))

from src.routing.terrain_graph import TerrainGridGraphBuilder
from src.routing.terrain_visualizer import plot_3d_matplotlib, export_3d_interactive_html


def main():
    parser = argparse.ArgumentParser(description="Generator i wizualizator siatki 3D terenu Parku Narodowego.")
    parser.add_argument("--area", type=str, default="Gorczański Park Narodowy, Poland", help="Nazwa obszaru/parku")
    parser.add_argument("--step", type=float, default=350.0, help="Rozdzielczość siatki w metrach (np. 200, 350)")
    parser.add_argument("--show-3d", action="store_true", help="Otwiera interaktywne okno 3D Matplotlib")
    parser.add_argument("--no-html", action="store_true", help="Wyłącza generowanie pliku HTML WebGL")
    args = parser.parse_args()

    print("=" * 75)
    print(" GENEROWANIE I WIZUALIZACJA MAPY 3D PARKU NARODOWEGO (2D/3D MESH)")
    print("=" * 75)

    base_dir = Path(__file__).resolve().parent / "data" / "trails"
    base_dir.mkdir(parents=True, exist_ok=True)

    output_graphml = base_dir / "gorce_terrain_grid.graphml"
    output_png = base_dir / "gorce_3d_terrain.png"
    output_html = base_dir / "gorce_terrain_3d.html"

    # 1. Budowa lub załadowanie grafu
    builder = TerrainGridGraphBuilder(metric_crs="EPSG:2180")
    graph = builder.build(
        area_name=args.area,
        step_meters=args.step,
        save_graphml_path=str(output_graphml)
    )

    # 2. Statystyki
    nodes = list(graph.nodes(data=True))
    edges = list(graph.edges(data=True))
    elevations = [data["z"] for _, data in nodes]
    slopes = [data["slope_degrees"] for _, _, data in edges]

    print("\n" + "=" * 75)
    print(" PODSUMOWANIE MAPY TERENU")
    print("=" * 75)
    print(f"Liczba węzłów (punktów terenu): {len(nodes):,}")
    print(f"Liczba krawędzi (kierunków marszu): {len(edges):,}")
    print(f"Zakres wysokości n.p.m. (z): min = {min(elevations):.1f} m, max = {max(elevations):.1f} m")
    print(f"Maksymalne nachylenie terenu pod górę: +{max(slopes):.2f}°")
    print(f"Maksymalne nachylenie terenu w dół:     {min(slopes):.2f}°")

    # 3. Generowanie statycznego renderu 3D (PNG) i ewentualne okno interaktywne
    print("\n[Wizualizacja 3D Matplotlib]:")
    plot_3d_matplotlib(
        graph=graph,
        save_path=str(output_png),
        show=args.show_3d,
        title=f"Model Rzeźby Terenu 3D - {args.area}"
    )

    # 4. Eksport interaktywnego modelu 3D (HTML/WebGL do przeglądarki)
    if not args.no_html:
        print("\n[Wizualizacja 3D WebGL / HTML]:")
        export_3d_interactive_html(
            graph=graph,
            output_html_path=str(output_html),
            title=f"Interaktywny Model 3D - {args.area}"
        )

    print("\n" + "=" * 75)
    print(" WYGENEROWANE PLIKI:")
    print(f" 1. Graf matematyczny:    {output_graphml}")
    print(f" 2. Wizualizacja 3D (PNG): {output_png}")
    if not args.no_html:
        print(f" 3. Interaktywna mapa 3D:  {output_html} (otwórz w przeglądarce!)")
    print("=" * 75)


if __name__ == "__main__":
    main()
