import os
import json
import math
from pathlib import Path
from typing import Optional

import numpy as np
import networkx as nx
import scipy.spatial


def get_graph_step_meters(graph: nx.DiGraph) -> float:
    """
    Pobiera lub automatycznie wylicza krok siatki (step_meters) z grafu.
    """
    if "step_meters" in graph.graph:
        try:
            val = float(graph.graph["step_meters"])
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass

    # Automatyczna detekcja na podstawie minimalnej dodatniej odległości krawędzi
    edge_dists = [
        float(d["distance_2d"])
        for _, _, d in graph.edges(data=True)
        if d.get("distance_2d", 0) > 0
    ]
    if edge_dists:
        return float(min(edge_dists))

    return 100.0


def plot_3d_matplotlib(
    graph: nx.DiGraph,
    save_path: Optional[str] = None,
    show: bool = False,
    view_elevation: float = 35.0,
    view_azimuth: float = -60.0,
    title: str = "Trójwymiarowy Model Rzeźby Terenu"
):
    """
    Renderuje trójwymiarowy model terenu (3D surface) za pomocą Matplotlib.
    Umożliwia zapis do pliku PNG lub wyświetlenie interaktywnego okna 3D (plt.show()).
    """
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D
    import matplotlib.tri as mtri

    nodes = list(graph.nodes(data=True))
    if not nodes:
        raise ValueError("Graf nie zawiera węzłów do wizualizacji.")

    xs = np.array([float(d["x"]) for _, d in nodes])
    ys = np.array([float(d["y"]) for _, d in nodes])
    zs = np.array([float(d["z"]) for _, d in nodes])

    # Metryczne współrzędne do precyzyjnego maskowania krawędzi
    xm = np.array([float(d.get("x_metric", d["x"])) for _, d in nodes])
    ym = np.array([float(d.get("y_metric", d["y"])) for _, d in nodes])

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")

    # Triangulacja Delaunaya w rzucie geograficznym
    triang = mtri.Triangulation(xs, ys)
    step_meters = get_graph_step_meters(graph)
    max_edge_metric = step_meters * 1.55  # Maksymalna dopuszczalna długość boku (przekątna siatki ~1.414 * krok)

    tri_xm = xm[triang.triangles]
    tri_ym = ym[triang.triangles]
    d01 = np.hypot(tri_xm[:, 1] - tri_xm[:, 0], tri_ym[:, 1] - tri_ym[:, 0])
    d12 = np.hypot(tri_xm[:, 2] - tri_xm[:, 1], tri_ym[:, 2] - tri_ym[:, 1])
    d20 = np.hypot(tri_xm[:, 0] - tri_xm[:, 2], tri_ym[:, 0] - tri_ym[:, 2])

    # Maskujemy trójkąty rozpięte na krawędziach dalszych niż przekątna siatki
    triang.set_mask((d01 > max_edge_metric) | (d12 > max_edge_metric) | (d20 > max_edge_metric))

    # Renderowanie ciągłej powierzchni stoku
    surf = ax.plot_trisurf(
        triang, zs,
        cmap="terrain",
        edgecolor="none",
        alpha=0.92,
        antialiased=True
    )

    cbar = fig.colorbar(surf, shrink=0.55, aspect=12, pad=0.1)
    cbar.set_label("Wysokość n.p.m. [m]", fontsize=11)

    ax.set_title(title, fontsize=13, fontweight="bold", pad=15)
    ax.set_xlabel("Długość geograficzna [°E]", labelpad=10)
    ax.set_ylabel("Szerokość geograficzna [°N]", labelpad=10)
    ax.set_zlabel("Wysokość [m n.p.m.]", labelpad=10)

    # Kąt obserwacji
    ax.view_init(elev=view_elevation, azim=view_azimuth)

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f" -> Zapisano render 3D (PNG) w: {save_path}")

    if show:
        print(" -> Otwieranie interaktywnego okna 3D Matplotlib (obracaj myszką)...")
        plt.show()

    plt.close(fig)


def export_3d_interactive_html(
    graph: nx.DiGraph,
    output_html_path: str,
    title: str = "Interaktywny Model Terenu 3D"
):
    """
    Eksportuje siatkę terenu do samodzielnego pliku HTML z grafiką 3D WebGL (Three.js).
    Plik można otworzyć w dowolnej przeglądarce (Chrome, Edge, Opera, Firefox)
    z płynnym obracaniem 360°, przybliżaniem (zoom) i inspektorem wysokości.
    """
    nodes = list(graph.nodes(data=True))
    if not nodes:
        raise ValueError("Graf nie zawiera węzłów.")

    # Wyciągnięcie współrzędnych metrycznych i wysokości
    xs = np.array([float(d.get("x_metric", d["x"])) for _, d in nodes])
    ys = np.array([float(d.get("y_metric", d["y"])) for _, d in nodes])
    zs = np.array([float(d["z"]) for _, d in nodes])

    lons = np.array([float(d["x"]) for _, d in nodes])
    lats = np.array([float(d["y"]) for _, d in nodes])

    # Normalizacja współrzędnych do środka sceny 3D
    cx = (xs.min() + xs.max()) / 2.0
    cy = (ys.min() + ys.max()) / 2.0
    cz_min = zs.min()
    cz_max = zs.max()

    scale = max(xs.max() - xs.min(), ys.max() - ys.min())
    if scale == 0:
        scale = 1.0

    # Przeskalowane punkty (X, Y na płaszczyźnie, Z jako pion w Three.js)
    # W Three.js oś Y to pion, a Z to głębokość
    norm_x = ((xs - cx) / scale) * 100.0
    norm_z = -((ys - cy) / scale) * 100.0  # Y z mapy staje się Z sceny
    norm_y = ((zs - cz_min) / scale) * 100.0 * 2.2  # Lekka przesada pionowa dla czytelności rzeźby

    # Triangulacja Delaunaya w 2D z odrzuceniem sztucznych mostów poza granicami parku
    step_meters = get_graph_step_meters(graph)
    max_edge_metric = step_meters * 1.55  # Przekątna siatki wynosi sqrt(2)*krok = 1.414*krok

    tri = scipy.spatial.Delaunay(np.column_stack([norm_x, norm_z]))

    valid_faces = []
    for simplex in tri.simplices:
        p0, p1, p2 = simplex
        d01 = math.hypot(xs[p1] - xs[p0], ys[p1] - ys[p0])
        d12 = math.hypot(xs[p2] - xs[p1], ys[p2] - ys[p1])
        d20 = math.hypot(xs[p0] - xs[p2], ys[p0] - ys[p2])
        if d01 <= max_edge_metric and d12 <= max_edge_metric and d20 <= max_edge_metric:
            valid_faces.extend([int(p0), int(p1), int(p2)])

    faces = valid_faces

    # Przygotowanie danych wierzchołków i realistycznej palety barw
    vertices = []
    vertex_colors = []

    def get_terrain_color(height_norm):
        # Paleta górska: doliny (ciemna zieleń) -> las reglowy -> grzbiety (oliwka/brąz) -> turnie (skała/biel)
        if height_norm < 0.25:
            return [0.18, 0.45, 0.20]  # Doliny
        elif height_norm < 0.55:
            return [0.35, 0.55, 0.22]  # Regiel dolny/górny
        elif height_norm < 0.78:
            return [0.62, 0.52, 0.30]  # Polany i hale szczytowe
        else:
            return [0.78, 0.76, 0.72]  # Partie grzbietowe i skały

    for i in range(len(nodes)):
        vertices.extend([round(float(norm_x[i]), 3), round(float(norm_y[i]), 3), round(float(norm_z[i]), 3)])
        h_norm = (zs[i] - cz_min) / (cz_max - cz_min) if (cz_max - cz_min) > 0 else 0.5
        vertex_colors.extend(get_terrain_color(h_norm))

    data_payload = {
        "vertices": vertices,
        "faces": faces,
        "colors": vertex_colors,
        "stats": {
            "node_count": len(nodes),
            "edge_count": graph.number_of_edges(),
            "step_meters": round(float(step_meters), 1),
            "min_z": round(float(cz_min), 1),
            "max_z": round(float(cz_max), 1),
            "lons": [round(float(l), 4) for l in lons],
            "lats": [round(float(l), 4) for l in lats],
            "zs": [round(float(z), 1) for z in zs]
        }
    }

    html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      overflow: hidden;
      background: radial-gradient(circle at 50% 30%, #1e293b, #0f172a);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #f8fafc;
    }}
    #canvas-container {{
      width: 100vw;
      height: 100vh;
      display: block;
    }}
    #ui-panel {{
      position: absolute;
      top: 20px;
      left: 20px;
      background: rgba(15, 23, 42, 0.88);
      backdrop-filter: blur(10px);
      padding: 18px 22px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.12);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
      max-width: 330px;
      pointer-events: auto;
    }}
    h1 {{
      font-size: 15px;
      margin: 0 0 10px 0;
      font-weight: 700;
      color: #38bdf8;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .stat-row {{
      display: flex;
      justify-content: space-between;
      font-size: 12.5px;
      margin: 5px 0;
      color: #cbd5e1;
    }}
    .stat-val {{
      font-weight: 600;
      color: #f1f5f9;
    }}
    .controls-hint {{
      margin-top: 14px;
      padding-top: 10px;
      border-top: 1px solid rgba(255, 255, 255, 0.1);
      font-size: 11px;
      color: #94a3b8;
      line-height: 1.5;
    }}
    .btn {{
      margin-top: 10px;
      width: 100%;
      background: #0284c7;
      color: white;
      border: none;
      padding: 8px 12px;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 600;
      font-size: 12px;
      transition: background 0.2s;
    }}
    .btn:hover {{
      background: #0369a1;
    }}
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>
  <div id="canvas-container"></div>
  <div id="ui-panel">
    <h1>🏔️ {title}</h1>
    <div class="stat-row">
      <span>Węzły siatki (punkty):</span>
      <span class="stat-val">{data_payload['stats']['node_count']:,}</span>
    </div>
    <div class="stat-row">
      <span>Krawędzie terenu:</span>
      <span class="stat-val">{data_payload['stats']['edge_count']:,}</span>
    </div>
    <div class="stat-row">
      <span>Rozdzielczość (krok):</span>
      <span class="stat-val">{data_payload['stats']['step_meters']} m</span>
    </div>
    <div class="stat-row">
      <span>Wysokość minimalna:</span>
      <span class="stat-val">{data_payload['stats']['min_z']} m n.p.m.</span>
    </div>
    <div class="stat-row">
      <span>Wysokość maksymalna:</span>
      <span class="stat-val">{data_payload['stats']['max_z']} m n.p.m.</span>
    </div>
    <button class="btn" id="toggle-wireframe">Przełącz siatkę krawędzi (Wireframe)</button>
    <div class="controls-hint">
      🖱️ <b>Lewy przycisk:</b> Obrót 3D (360°)<br>
      🖱️ <b>Prawy przycisk:</b> Przesuwanie kamery<br>
      🔍 <b>Rolka myszy:</b> Przybliżanie / oddalanie
    </div>
  </div>

  <script>
    const data = {json.dumps(data_payload)};

    // 1. Inicjalizacja sceny Three.js
    const container = document.getElementById('canvas-container');
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x0f172a, 0.003);

    const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(0, 65, 105);

    const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    container.appendChild(renderer.domElement);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 - 0.02;

    // 2. Oświetlenie
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xfffaed, 0.95);
    sunLight.position.set(60, 100, 40);
    sunLight.castShadow = true;
    scene.add(sunLight);

    const fillLight = new THREE.DirectionalLight(0x93c5fd, 0.35);
    fillLight.position.set(-60, 40, -40);
    scene.add(fillLight);

    // 3. Budowa siatki trójkątów powierzchni 3D
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(data.vertices, 3));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(data.colors, 3));
    geometry.setIndex(data.faces);
    geometry.computeVertexNormals();

    const material = new THREE.MeshLambertMaterial({{
      vertexColors: true,
      side: THREE.DoubleSide,
      wireframe: false
    }});

    const terrainMesh = new THREE.Mesh(geometry, material);
    terrainMesh.receiveShadow = true;
    scene.add(terrainMesh);

    // 4. Punkty węzłów (subtelne podświetlenie wierzchołków)
    const pointsGeom = new THREE.BufferGeometry();
    pointsGeom.setAttribute('position', new THREE.Float32BufferAttribute(data.vertices, 3));
    const pointsMat = new THREE.PointsMaterial({{
      size: 1.2,
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.4
    }});
    const pointsMesh = new THREE.Points(pointsGeom, pointsMat);
    scene.add(pointsMesh);

    // 5. Obsługa przełącznika wireframe
    let isWireframe = false;
    document.getElementById('toggle-wireframe').addEventListener('click', () => {{
      isWireframe = !isWireframe;
      material.wireframe = isWireframe;
    }});

    // 6. Główna pętla renderowania
    function animate() {{
      requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }}
    animate();

    window.addEventListener('resize', () => {{
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    }});
  </script>
</body>
</html>
"""
    Path(output_html_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f" -> Zapisano interaktywny model 3D (HTML/WebGL) w: {output_html_path}")
