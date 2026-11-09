# Symulacja Akcji Ratunkowych GOPR - Model Terenu i Agentów

## Moduł Topografii i Siatki Terenu 3D (Pipeline 3-etapowy)

Stworzono modularny potok 3 niezależnych programów do pobierania, budowy i wizualizacji mapy 3D terenu Parku Narodowego:

```text
               Krok 1                               Krok 2                             Krok 3
┌─────────────────────────────────┐     ┌────────────────────────────┐     ┌────────────────────────────┐
│ 1_download_terrain_data.py      │     │ 2_build_terrain_graph.py   │     │ 3_visualize_terrain_3d.py  │
│                                 │     │                            │     │                            │
│ - Pobiera granice OSM (GeoJSON) │     │ - Wczytuje JSON (OFFLINE)  │     │ - Wczytuje GraphML (OFFLINE│
│ - Generuje siatkę metryczną     │────>│ - Buduje graf 2D/3D (8 dir)│────>│ - Model 3D WebGL (HTML)   │
│ - Pobiera rzędne DEM bez limitu │     │ - Liczy nachylenia stoku   │     │ - Render 3D (PNG)          │
│ - Zapisuje terrain_points.json  │     │ - Zapisuje .graphml        │     │ - Okno interaktywne 3D     │
└─────────────────────────────────┘     └────────────────────────────┘     └────────────────────────────┘
```

### 1. Pobieranie danych geograficznych (`1_download_terrain_data.py`)
Pobiera granice obszaru z OpenStreetMap oraz rzędne wysokościowe z modelu Copernicus DEM (lub lokalnego rastra NMT GeoTIFF).
* **Brak limitu czasowego**: W razie ograniczeń częstotliwości zapytań (HTTP 429), program automatycznie czeka i ponawia próby, nie tracąc dokładności i nie wpisując sztucznych wartości.
* **Ciągły zapis cache**: Każda partia punktów jest natychmiast utrwalana na dysku w `data/dem/elevation_cache.json`.

```bash
# Pobranie danych Gorczańskiego Parku Narodowego z siatką co 100 metrów:
python 1_download_terrain_data.py --step 100

# Szybki test siatki o mniejszej rozdzielczości (krok 250 m):
python 1_download_terrain_data.py --step 250
```

### 2. Budowa grafu rzeźby terenu (`2_build_terrain_graph.py`)
Działa **w 100% offline**. Wczytuje plik `data/dem/terrain_points.json`, łączy punkty w siatkę o 8-kierunkowym sąsiedztwie i dla każdej krawędzi wylicza:
* `distance_2d` [m] – rzut poziomy
* `elevation_change` [m] – przewyższenie ($dz$)
* `distance_3d` [m] – rzeczywistą długość marszu w przestrzeni 3D
* `slope_degrees` [°] – kąt nachylenia stoku (-90° do +90°)
* `slope_ratio` – tangens kąta stoku
* `grade_pct` [%] – nachylenie procentowe

```bash
python 2_build_terrain_graph.py
```

### 3. Wizualizacja i eksploracja 3D (`3_visualize_terrain_3d.py`)
Działa **w 100% offline**. Wczytuje wygenerowany graf `data/trails/gorce_terrain_grid.graphml` i tworzy:
1. **Interaktywny model 3D WebGL (`gorce_terrain_3d.html`)**: Samodzielny plik HTML do otwarcia w przeglądarce (Chrome, Edge, Firefox). Umożliwia swobodny obrót myszką 360°, płynne przybliżanie rolką, przełączanie siatki krawędzi (Wireframe) oraz wyświetla panel HUD.
2. **Statyczny obraz 3D (`gorce_3d_terrain.png`)**: Trójwymiarowy render stoku z paletą hipsometryczną.

```bash
# Generuje plik HTML i PNG:
python 3_visualize_terrain_3d.py

# Opcjonalnie: otwiera interaktywne okno desktopowe Matplotlib:
python 3_visualize_terrain_3d.py --show
```

---

## Struktura Katalogów Projektu

```text
Agentowa_symulacja_akcji_ratunkowych/
├── 1_download_terrain_data.py # Program 1: Pobieranie granic i DEM do pliku JSON
├── 2_build_terrain_graph.py   # Program 2: Mapowanie punktów na graf i zapis do GraphML
├── 3_visualize_terrain_3d.py  # Program 3: Wizualizacja grafu w postaci mapy 3D (HTML i PNG)
├── config/                    # Pliki konfiguracyjne symulacji (YAML / JSON)
├── data/                      # Dane wejściowe GIS
│   ├── dem/                   # Punkty terenu (terrain_points.json) i cache wysokości
│   └── trails/                # Grafy terenu (.graphml), granice (.geojson) i modele 3D (.html)
├── notebooks/                 # Notatniki Jupyter (.ipynb)
├── src/                       # Kod źródłowy
│   ├── core/                  # Silnik DES + ABM w SimPy (ratownicy, dyspozytor, incydenty)
│   ├── routing/               # Graf terenu (terrain_graph.py) i wizualizator 3D (terrain_visualizer.py)
│   ├── sar/                   # Poszukiwania Search & Rescue
│   └── metrics/               # Metryki efektywności i czasy dotarcia
├── tests/                     # Testy jednostkowe (pytest)
├── environment.yml            # Konfiguracja środowiska Conda
└── README.md                  # Dokumentacja projektu
```
