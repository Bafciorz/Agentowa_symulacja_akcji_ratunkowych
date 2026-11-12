import json
import math
import tempfile
from pathlib import Path
import networkx as nx
import shapely.geometry as geom

from data.downloaders.terrain_downloader import TerrainDownloader
from data.mappers.terrain_mapper import TerrainGraphMapper
from data.visualizers.terrain_visualizer import export_3d_interactive_html, get_graph_step_meters


def test_terrain_grid_graph_generation():
    downloader = TerrainDownloader(metric_crs="EPSG:2180")
    mapper = TerrainGraphMapper(metric_crs="EPSG:2180")

    # Tworzymy testowy poligon 2000m x 2000m w układzie EPSG:2180
    test_poly = geom.Polygon([
        (560000, 190000),
        (562000, 190000),
        (562000, 192000),
        (560000, 192000)
    ])

    # Krok 300m -> powstaną sąsiadujące punkty siatki
    points = downloader.generate_grid_points(test_poly, step_meters=300.0)
    assert len(points) > 1

    # Przypisujemy sztuczne wysokości do testu matematyki
    for i, p in enumerate(points):
        p["z"] = 1000.0 + (p["grid_i"] * 100.0)

    # Budujemy graf za pomocą mappera
    G = mapper.build_network_graph(points)
    assert G.number_of_nodes() == len(points)
    assert G.number_of_edges() > 0

    # Sprawdzamy atrybuty węzłów (x, y, z)
    for _, data in G.nodes(data=True):
        assert "x" in data
        assert "y" in data
        assert "z" in data

    # Sprawdzamy atrybuty krawędzi (odległość, kąt nachylenia)
    for _, _, edge_data in G.edges(data=True):
        assert "distance_2d" in edge_data
        assert "distance_3d" in edge_data
        assert "slope_degrees" in edge_data
        assert "elevation_change" in edge_data
        assert -90.0 <= edge_data["slope_degrees"] <= 90.0
        assert edge_data["distance_3d"] >= edge_data["distance_2d"]


def test_points_and_graph_save_load_lifecycle():
    downloader = TerrainDownloader(metric_crs="EPSG:2180")
    mapper = TerrainGraphMapper(metric_crs="EPSG:2180")

    sample_points = [
        {"grid_i": 0, "grid_j": 0, "x": 20.0, "y": 49.5, "z": 800.0, "x_metric": 560000.0, "y_metric": 190000.0},
        {"grid_i": 0, "grid_j": 1, "x": 20.0, "y": 49.51, "z": 850.0, "x_metric": 560000.0, "y_metric": 190100.0},
        {"grid_i": 1, "grid_j": 0, "x": 20.01, "y": 49.5, "z": 820.0, "x_metric": 560100.0, "y_metric": 190000.0},
        {"grid_i": 1, "grid_j": 1, "x": 20.01, "y": 49.51, "z": 890.0, "x_metric": 560100.0, "y_metric": 190100.0},
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        points_file = tmp_path / "test_points.json"
        graph_file = tmp_path / "test_graph.graphml"
        html_file = tmp_path / "test_model.html"

        # 1. Zapis punktów przez downloader i odczyt przez mapper
        meta = {"area_name": "Test Area", "step_meters": 100.0}
        downloader.save_terrain_points(sample_points, str(points_file), metadata=meta)
        loaded_pts, loaded_meta = mapper.load_terrain_points(str(points_file))
        assert len(loaded_pts) == 4
        assert loaded_meta["area_name"] == "Test Area"

        # 2. Budowa i zapis grafu przez mapper
        G = mapper.build_network_graph(loaded_pts, metadata=loaded_meta)
        mapper.save_graph(G, str(graph_file))

        # 3. Odczyt grafu przez mapper
        loaded_G = mapper.load_graph(str(graph_file))
        assert loaded_G.number_of_nodes() == 4
        assert loaded_G.number_of_edges() > 0

        for _, d in loaded_G.nodes(data=True):
            assert isinstance(d["z"], float)
            assert isinstance(d["x_metric"], float)

        # 4. Detekcja kroku siatki
        step = get_graph_step_meters(loaded_G)
        assert abs(step - 100.0) < 1.0

        # 5. Generowanie HTML 3D przez visualizer
        export_3d_interactive_html(loaded_G, str(html_file), title="Test 3D")
        assert html_file.is_file()
        content = html_file.read_text(encoding="utf-8")
        assert "three.min.js" in content
        assert "Test 3D" in content
