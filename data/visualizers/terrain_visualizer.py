#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Moduł odpowiedzialny za interaktywną trójwymiarową wizualizację siatki terenu (HTML WebGL / Three.js)
z wyróżnieniem szlaków turystycznych (wyraziste, ostre linie czerwone bez zamazywania terenu).
Lokalizacja: data/visualizers/terrain_visualizer.py
"""

import json
import math
from pathlib import Path

import numpy as np
import networkx as nx
import scipy.spatial


def get_graph_step_meters(graph: nx.DiGraph) -> float:
    """Pobiera lub automatycznie wylicza krok siatki (step_meters) z grafu."""
    if "step_meters" in graph.graph:
        try:
            val = float(graph.graph["step_meters"])
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass

    edge_dists = [
        float(d["distance_2d"])
        for _, _, d in graph.edges(data=True)
        if d.get("distance_2d", 0) > 0
    ]
    if edge_dists:
        return float(min(edge_dists))

    return 100.0


def export_3d_interactive_html(
    graph: nx.DiGraph,
    output_html_path: str,
    title: str = "Model Rzeźby Terenu 3D"
):
    """
    Eksportuje siatkę terenu do samodzielnego pliku HTML z grafiką 3D WebGL (Three.js).
    Umożliwia swobodne obracanie 360°, płynny zoom, pan, włączanie siatki wireframe
    oraz zaznaczenie szlaków turystycznych jako wyrazistych czerwonych linii dopasowanych do stoku.
    """
    nodes = list(graph.nodes(data=True))
    if not nodes:
        raise ValueError("Graf nie zawiera węzłów.")

    node_idx = {node_id: idx for idx, (node_id, _) in enumerate(nodes)}

    xs = np.array([float(d.get("x_metric", d["x"])) for _, d in nodes])
    ys = np.array([float(d.get("y_metric", d["y"])) for _, d in nodes])
    zs = np.array([float(d["z"]) for _, d in nodes])

    lons = np.array([float(d["x"]) for _, d in nodes])
    lats = np.array([float(d["y"]) for _, d in nodes])

    cx = (xs.min() + xs.max()) / 2.0
    cy = (ys.min() + ys.max()) / 2.0
    cz_min = zs.min()
    cz_max = zs.max()

    scale = max(xs.max() - xs.min(), ys.max() - ys.min())
    if scale == 0:
        scale = 1.0

    norm_x = ((xs - cx) / scale) * 100.0
    norm_z = -((ys - cy) / scale) * 100.0
    norm_y = ((zs - cz_min) / scale) * 100.0 * 2.2

    step_meters = get_graph_step_meters(graph)
    max_edge_metric = step_meters * 1.55

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

    vertices = []
    vertex_colors = []

    def get_terrain_color(height_norm):
        if height_norm < 0.25:
            return [0.18, 0.42, 0.20]  # Doliny i lasy
        elif height_norm < 0.55:
            return [0.35, 0.55, 0.22]  # Regiel dolny/górny
        elif height_norm < 0.78:
            return [0.62, 0.52, 0.30]  # Polany i hale
        else:
            return [0.78, 0.76, 0.72]  # Grzbiety i skały

    for i in range(len(nodes)):
        vertices.extend([round(float(norm_x[i]), 3), round(float(norm_y[i]), 3), round(float(norm_z[i]), 3)])
        h_norm = (zs[i] - cz_min) / (cz_max - cz_min) if (cz_max - cz_min) > 0 else 0.5
        vertex_colors.extend(get_terrain_color(h_norm))

    # Wyodrębnienie krawędzi szlaków (dokładne linie, subtelne uniesienie +0.035 aby nie nachodziły na trójkąty)
    trail_edge_vertices = []
    trail_edges_count = 0
    seen_undirected_edges = set()

    for u, v, d in graph.edges(data=True):
        is_trail = d.get("is_trail", False)
        if isinstance(is_trail, str):
            is_trail = is_trail.lower() in ["true", "1"]
        if is_trail:
            edge_key = tuple(sorted([u, v]))
            if edge_key in seen_undirected_edges:
                continue
            seen_undirected_edges.add(edge_key)

            trail_edges_count += 1
            if u in node_idx and v in node_idx:
                iu = node_idx[u]
                iv = node_idx[v]
                trail_edge_vertices.extend([
                    round(float(norm_x[iu]), 3), round(float(norm_y[iu]) + 0.035, 3), round(float(norm_z[iu]), 3),
                    round(float(norm_x[iv]), 3), round(float(norm_y[iv]) + 0.035, 3), round(float(norm_z[iv]), 3)
                ])

    # Węzły szlaku (subtelne punkty)
    trail_node_vertices = []
    trail_nodes_count = 0
    for node_id, d in nodes:
        is_trail = d.get("is_trail", False)
        if isinstance(is_trail, str):
            is_trail = is_trail.lower() in ["true", "1"]
        if is_trail:
            trail_nodes_count += 1
            i = node_idx[node_id]
            trail_node_vertices.extend([
                round(float(norm_x[i]), 3),
                round(float(norm_y[i]) + 0.04, 3),
                round(float(norm_z[i]), 3)
            ])

    data_payload = {
        "vertices": vertices,
        "faces": faces,
        "colors": vertex_colors,
        "trail_node_vertices": trail_node_vertices,
        "trail_edge_vertices": trail_edge_vertices,
        "stats": {
            "node_count": len(nodes),
            "edge_count": graph.number_of_edges(),
            "trail_nodes_count": trail_nodes_count,
            "trail_edges_count": trail_edges_count,
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
      background: rgba(15, 23, 42, 0.92);
      backdrop-filter: blur(12px);
      padding: 16px 20px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.15);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
      max-width: 350px;
      pointer-events: auto;
      z-index: 50;
      transition: opacity 0.2s ease, transform 0.2s ease;
    }}
    .panel-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
      gap: 10px;
    }}
    .panel-header h1 {{
      font-size: 14px;
      margin: 0;
      font-weight: 700;
      color: #38bdf8;
      line-height: 1.35;
    }}
    .btn-close {{
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #94a3b8;
      border-radius: 6px;
      padding: 3px 8px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      flex-shrink: 0;
    }}
    .btn-close:hover {{
      background: rgba(239, 68, 68, 0.25);
      color: #fca5a5;
      border-color: rgba(239, 68, 68, 0.4);
    }}
    .stat-row {{
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      margin: 5px 0;
      color: #cbd5e1;
    }}
    .stat-row.trail-stat {{
      color: #fca5a5;
      font-weight: 500;
    }}
    .stat-val {{
      font-weight: 600;
      color: #f1f5f9;
    }}
    .stat-val.red {{
      color: #ff1e42;
    }}
    .separator {{
      height: 1px;
      background: rgba(255, 255, 255, 0.1);
      margin: 10px 0;
    }}
    .btn {{
      margin-top: 8px;
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
    .btn-danger {{
      background: #dc2626;
    }}
    .btn-danger:hover {{
      background: #b91c1c;
    }}
    .btn-secondary {{
      background: rgba(255, 255, 255, 0.12);
      color: #cbd5e1;
    }}
    .btn-secondary:hover {{
      background: rgba(255, 255, 255, 0.20);
      color: #ffffff;
    }}
    #btn-show-panel {{
      display: none;
      position: absolute;
      top: 20px;
      left: 20px;
      background: rgba(15, 23, 42, 0.90);
      backdrop-filter: blur(10px);
      padding: 8px 14px;
      border-radius: 8px;
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #38bdf8;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
      transition: background 0.2s, color 0.2s;
      z-index: 50;
    }}
    #btn-show-panel:hover {{
      background: #0284c7;
      color: #ffffff;
    }}
    .legend-box {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      margin-top: 4px;
      color: #94a3b8;
    }}
    .color-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
    }}
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>
  <div id="canvas-container"></div>

  <button id="btn-show-panel">Pokaż panel</button>

  <div id="ui-panel">
    <div class="panel-header">
      <h1>{title}</h1>
      <button class="btn-close" id="btn-close-panel" title="Schowaj panel">Schowaj</button>
    </div>
    <div class="stat-row">
      <span>Węzły siatki (punkty):</span>
      <span class="stat-val">{data_payload['stats']['node_count']:,}</span>
    </div>
    <div class="stat-row">
      <span>Krawędzie terenu (ogółem):</span>
      <span class="stat-val">{data_payload['stats']['edge_count']:,}</span>
    </div>
    <div class="stat-row">
      <span>Rozdzielczość (krok):</span>
      <span class="stat-val">{data_payload['stats']['step_meters']} m</span>
    </div>
    <div class="stat-row">
      <span>Wysokość min / max:</span>
      <span class="stat-val">{data_payload['stats']['min_z']} / {data_payload['stats']['max_z']} m</span>
    </div>

    <div class="separator"></div>

    <div class="stat-row trail-stat">
      <span>Węzły na szlakach:</span>
      <span class="stat-val red">{data_payload['stats']['trail_nodes_count']:,}</span>
    </div>
    <div class="stat-row trail-stat">
      <span>Odcinki szlaków:</span>
      <span class="stat-val red">{data_payload['stats']['trail_edges_count']:,}</span>
    </div>

    <div class="legend-box">
      <span class="color-dot" style="background: #ff1e42;"></span>
      <span>Czerwone linie: Szlaki turystyczne PTTK</span>
    </div>

    <div class="separator"></div>

    <button class="btn btn-danger" id="toggle-trails">Przełącz linie szlaków (Czerwone)</button>
    <button class="btn btn-secondary" id="toggle-trail-nodes">Pokaż / Ukryj punkty węzłowe</button>
    <button class="btn" id="toggle-wireframe">Przełącz siatkę krawędzi (Wireframe)</button>
  </div>

  <script>
    const data = {json.dumps(data_payload)};

    // 1. Obsługa zwijania / rozwijania panelu
    const panel = document.getElementById('ui-panel');
    const showBtn = document.getElementById('btn-show-panel');
    const closeBtn = document.getElementById('btn-close-panel');

    closeBtn.addEventListener('click', () => {{
      panel.style.display = 'none';
      showBtn.style.display = 'block';
    }});

    showBtn.addEventListener('click', () => {{
      panel.style.display = 'block';
      showBtn.style.display = 'none';
    }});

    // 2. Scena Three.js
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

    // 3. Oświetlenie
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.65);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xfffaed, 0.95);
    sunLight.position.set(60, 100, 40);
    sunLight.castShadow = true;
    scene.add(sunLight);

    const fillLight = new THREE.DirectionalLight(0x93c5fd, 0.35);
    fillLight.position.set(-60, 40, -40);
    scene.add(fillLight);

    // 4. Geometria powierzchni stoku
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

    // 5. Czyste, ostre linie szlaków turystycznych (wyrazista czerwień)
    let trailLinesMesh = null;
    if (data.trail_edge_vertices && data.trail_edge_vertices.length > 0) {{
      const trailLinesGeom = new THREE.BufferGeometry();
      trailLinesGeom.setAttribute('position', new THREE.Float32BufferAttribute(data.trail_edge_vertices, 3));
      const trailLinesMat = new THREE.LineBasicMaterial({{
        color: 0xff1e42, // intensywna czerwień szlaku turystycznego
        linewidth: 2,
        transparent: false,
        depthTest: true
      }});
      trailLinesMesh = new THREE.LineSegments(trailLinesGeom, trailLinesMat);
      scene.add(trailLinesMesh);
    }}

    // 6. Subtelne punkty węzłowe szlaków (domyślnie ukryte, aby nie zasłaniać rzeźby terenu)
    let trailPointsMesh = null;
    if (data.trail_node_vertices && data.trail_node_vertices.length > 0) {{
      const trailPointsGeom = new THREE.BufferGeometry();
      trailPointsGeom.setAttribute('position', new THREE.Float32BufferAttribute(data.trail_node_vertices, 3));
      const trailPointsMat = new THREE.PointsMaterial({{
        size: 0.6,
        color: 0xff4444,
        sizeAttenuation: true,
        transparent: true,
        opacity: 0.85
      }});
      trailPointsMesh = new THREE.Points(trailPointsGeom, trailPointsMat);
      trailPointsMesh.visible = false; // Domyślnie linie są czyste bez plam punktowych
      scene.add(trailPointsMesh);
    }}

    // 7. Przełączanie widoczności szlaków
    let trailsVisible = true;
    const btnToggleTrails = document.getElementById('toggle-trails');
    if (btnToggleTrails) {{
      btnToggleTrails.addEventListener('click', () => {{
        trailsVisible = !trailsVisible;
        if (trailLinesMesh) trailLinesMesh.visible = trailsVisible;
      }});
    }}

    // 8. Przełączanie widoczności punktów węzłowych
    let trailNodesVisible = false;
    const btnToggleNodes = document.getElementById('toggle-trail-nodes');
    if (btnToggleNodes) {{
      btnToggleNodes.addEventListener('click', () => {{
        trailNodesVisible = !trailNodesVisible;
        if (trailPointsMesh) trailPointsMesh.visible = trailNodesVisible;
        btnToggleNodes.innerText = trailNodesVisible ? "Ukryj punkty węzłowe" : "Pokaż punkty węzłowe";
      }});
    }}

    // 9. Przełączanie siatki krawędzi (Wireframe)
    let isWireframe = false;
    document.getElementById('toggle-wireframe').addEventListener('click', () => {{
      isWireframe = !isWireframe;
      material.wireframe = isWireframe;
    }});

    // 10. Pętla renderująca
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
    if trail_nodes_count > 0 or trail_edges_count > 0:
        print(f"    * Zaznaczono wyraziste linie szlaków: {trail_edges_count:,} odcinków (węzły: {trail_nodes_count:,}).")
