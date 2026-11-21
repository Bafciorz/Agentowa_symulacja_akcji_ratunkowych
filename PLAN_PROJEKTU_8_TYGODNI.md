# HARMONOGRAM I PLAN ROZWOJU PROJEKTU (8 TYGODNI)
## Symulacja Górskich Akcji Ratowniczych GOPR w Pasmie Gorców
**Przedmiot:** Symulacja Systemów Dyskretnych (Semestr V, AGH Kraków)  
**Zespół wykonawców:**  
- **Wiktor Bukowski**
- **Jakub Bafia**
- **Tomasz Chmielowski**

---

## 1. Cel i Kluczowe Założenia Projektu
Projekt modeluje całościowe funkcjonowanie systemu ratownictwa górskiego GOPR (Grupa Podhalańska) w rejonie Pasma Gorców (rejon Turbacza, Kiczory, Starych Wierchów, Doliny Kamienicy).

System łączy trzy filary:
1. **Discrete Event Simulation (DES w SimPy):** Asynchroniczna obsługa osi czasu, kolejek i dysponowania zasobów.
2. **Agent-Based Modeling (ABM na grafie szlaków):** Autonomiczni ratownicy piesi, quady/skutery śnieżne, ochotnicy z czasem mobilizacji oraz poszkodowani/zaginieni turystycy.
3. **Realistyczna fizyka terenu (GIS/DEM):** Rzeczywiste szlaki PTTK, asymetryczna prędkość marszu na stoku (Campbell-Sullivan / Lorentz) oraz warunki zimowe (śnieg, porywy wiatru).

### Mieszany charakter wezwań operacyjnych:
System obsługuje dwa uzupełniające się typy wezwań:
- **Zdarzenia stacjonarne o znanej lokalizacji (70–80% zgłoszeń):**  
  Typowe kontuzje turystyczne (skręcenia kostki `LOW`, złamania wymagające transportu w noszach i min. 2 ratowników `HIGH` z barierą `simpy.AllOf`) oraz nagłe stany bezpośredniego zagrożenia życia (zatrzymanie krążenia NZK `CRITICAL` wyzwalające wywłaszczenie zadań `simpy.Interrupt`).
- **Zdarzenia poszukiwawcze o nieznanej lokalizacji (20–30% zgłoszeń – WiSAR):**  
  Osoby zaginione w rejonie grzbietowym lub wiatrołomach (wyznaczanie sektorów prawdopodobieństwa POA, przeszukiwanie tyralierą, modelowanie zachowania zaginionego wg Koestera).

---

## 2. Harmonogram Działań Tydzień po Tygodniu (8 Tygodni)

Całość prac zaplanowano w 4 dwutygodniowych sprintach. Zasadniczy kod i badania zamykamy w **6. tygodniu**, pozostawiając ostatnie 2 tygodnie jako bezpieczny bufor na raport i przygotowanie do obrony.

```
[Sprint 1: Tydz. 1-2] ──► [Sprint 2: Tydz. 3-4] ──► [Sprint 3: Tydz. 5-6] ──► [Sprint 4: Tydz. 7-8]
  Stochastyka & WiSAR       Integracja & Pętla MC     Eksperymenty & Dashboard   Raport LaTeX & Obrona
```

---

### SPRINT 1 (Tygodnie 1 – 2): Fundamenty Stochastyki i Model Zaginionego
> **Cel:** Zastąpienie sztywnych danych generatorami losowymi i stworzenie logiki agenta zaginionego.

* **Tydzień 1:**
  * Utworzenie modułu `stochastic_generator.py` (proces Poissona dla napływu wezwań, wagi ryzyka na węzłach grafu Gorców).
  * Stworzenie klasy `LostPerson` (model ruchu zaginionego w terenie: schodzenie w dół dolin, błądzenie po grani, bezruch).
  * Przeniesienie obliczania odległości 2D/3D, deniwelacji i czasów bazowych bezpośrednio na krawędzie grafu (`G[u][v]`) wraz z flagą przejezdności dla quada.
  * Zdefiniowanie wektora zmiennych decyzyjnych dla optymalizacji (rozmieszczenie ratowników, ochotników i sprzętu w bazach).
* **Tydzień 2:**
  * Dobór rozkładów prawdopodobieństwa dla czasów zaopatrywania urazów (rozkłady trójkątne / log-normalne w zależności od priorytetu Triage).
  * Napisanie testów jednostkowych w `pytest` weryfikujących poprawność generowania losowych scenariuszy i ruchu zaginionego.
  * **Kamień Milowy 1:** Działający generator stochastyczny oraz w pełni przetestowany agent zaginionego poruszający się po grafie.

---

### SPRINT 2 (Tygodnie 3 – 4): Integracja WiSAR, Pętla Monte Carlo i Szkielet Optymalizacji
> **Cel:** Połączenie modułów w jedną wielowątkową machinę symulacyjną.

* **Tydzień 3:**
  * Rozszerzenie logiki dyspozytora o obsługę poszukiwań: podział ratowników między standardowe kontuzje a sektory poszukiwawcze WiSAR (sektory o najwyższym POA).
  * Zbudowanie modułu `batch_runner.py` zdolnego do automatycznego uruchamiania $N$ symulacji w pętli z uśrednianiem metryk.
* **Tydzień 4:**
  * Połączenie modułu optymalizacyjnego z symulatorem SimPy (algorytm proponuje dyslokację zasobów $\to$ symulacja weryfikuje czasy dotarcia $\to$ sprzężenie zwrotne).
  * Implementacja dylematu dyspozytora: obsługa wywłaszczania ratowników z poszukiwań w razie nagłego wypadku krytycznego na szlaku.
  * **Kamień Milowy 2:** Symulator potrafi wykonać serię 50 powtórzeń bez błędów, a algorytm optymalizacyjny poprawnie ocenia konfiguracje baz.

---

### SPRINT 3 (Tygodnie 5 – 6): Kampania Eksperymentalna i Dashboard
> **Cel:** Wygenerowanie wyników badawczych, wykresów oraz stworzenie aplikacji demonstracyjnej. ZAMKNIĘCIE KODU.

* **Tydzień 5 (Główne badania Monte Carlo):**
  * Uruchomienie pełnych serii badawczych (po 100–300 replikacji) dla kluczowych scenariuszy:
    * *Badanie 1:* Stan obecny dyslokacji baz vs stan po optymalizacji algorytmem.
    * *Badanie 2:* Warunki optymalne (lato) vs załamanie pogody (zima, śnieg 20 cm, wiatr).
    * *Badanie 3:* Wpływ dostępności zmotoryzowanego sprzętu (quad z przyczepą transportową).
  * Zbieranie metryk: średni czas dotarcia (Response Time), 95-percentyl czasu oczekiwania, współczynnik obciążenia ratowników (% dyżuru w akcji).
* **Tydzień 6 (Wizualizacja i Dashboard):**
  * Wygenerowanie wykresów statystycznych (histogramy czasów, box-ploty, wykresy zbieżności optymalizatora).
  * Zbudowanie prostego, estetycznego dashboardu w **Streamlit** (suwaki pogody, wybór scenariusza, odpalenie symulacji na żywo, wykresy wyników).
  * **Kamień Milowy 3:** **100% ZAKOŃCZENIA PRAC PROGRAMISTYCZNYCH.** Wszystkie wyniki i wykresy są gotowe.

---

### SPRINT 4 (Tygodnie 7 – 8): Raport Końcowy, Slajdy i Obrona
> **Cel:** Bezstresowe domknięcie dokumentacji, raport w LaTeX i próba prezentacji przed zaliczeniem.

* **Tydzień 7:**
  * Spisanie obszernego raportu końcowego w LaTeX (`raport_koncowy.tex`) na bazie dotychczasowego szablonu:
    * Metodologia stochastyczna i procesy Poissona,
    * Moduł WiSAR i algorytmy przeszukiwania,
    * Sformułowanie problemu optymalizacyjnego i wyniki algorytmu,
    * Twarde dane statystyczne z eksperymentów Monte Carlo i wykresy.
* **Tydzień 8:**
  * Przygotowanie prezentacji multimedialnej (10–12 slajdów: problem, architektura SimPy, mapa Gorców, demo Streamlit, wnioski badawcze).
  * Próba generalna wystąpienia (podział ról na obronie, dyscyplina czasu: 10–15 minut).
  * **Oddanie projektu i zaliczenie przedmiotu na ocenę 5.0.**

---

## 3. Długofalowy Podział Odpowiedzialności w Zespole

### 1. Jakub Bafia – Silnik DES, Stochastyka i Eksperymenty Monte Carlo
* **Obszar odpowiedzialności:** Jądro symulacji SimPy, losowość napływu wezwań, modelowanie różnych typów urazów i statystyczna analiza wyników.
* **Główne pliki:**
  * `src/core/stochastic_generator.py`
  * `experiments/batch_runner.py`
  * `experiments/statistical_analysis.py`
* **Definicja ukończenia (DoD):** Generator losuje realistyczne wezwania, pętla Monte Carlo bezawaryjnie przetwarza 300 powtórzeń, a wyniki zawierają średnie i przedziały ufności $95\%$.

### 2. Wiktor Bukowski – Moduł Poszukiwawczy WiSAR i Modelowanie Terenowe
* **Obszar odpowiedzialności:** Logika zachowania zaginionego turysty, przestrzeń poszukiwań poza szlakami i algorytmy przeszukiwania sektorowego.
* **Główne pliki:**
  * `src/wisar/lost_person.py`
  * `src/wisar/search_strategy.py`
  * Integracja misji `SEARCH` w `src/core/dispatcher.py`
* **Definicja ukończenia (DoD):** Zaginiony przemieszcza się po zboczach Gorców wg heurystyk Koestera, dyspozytor wyznacza sektory poszukiwań, a ratownicy przeszukują teren ze zliczaniem prawdopodobieństwa odnalezienia (POD).

### 3. Tomasz Chmielowski – Optymalizacja Symulacyjna, Architektura Krawędzi Grafu i Dashboard
* **Obszar odpowiedzialności:** Przeniesienie obliczeń odległości i czasów bezpośrednio na krawędzie grafu (prekalkulacja wag dla szybkiego routingu), algorytm optymalizujący dyslokację baz GOPR, aplikacja prezentacyjna Streamlit oraz wykresy porównawcze.
* **Główne pliki:**
  * `src/routing/gorce_trails_network.py` (atrybuty krawędzi: odległości 2D/3D, czasy bazowe, flaga `vehicle_accessible`)
  * `src/optimization/base_optimizer.py`
  * `app/streamlit_app.py`
  * `experiments/visualize_results.py`
* **Definicja ukończenia (DoD):** Krawędzie grafu posiadają wprost przypisane odległości i czasy, algorytm optymalizacyjny potrafi znaleźć konfigurację baz skracającą średni czas dotarcia, a aplikacja Streamlit pozwala uruchomić demonstrację na żywo jednym kliknięciem.

---

## 4. Zasady Współpracy w Zespole
1. **Praca na gałęziach (Git Feature Branching):**
   * Każdy członek zespołu rozwija swój moduł na dedykowanej gałęzi:
     * `feature/stochastic-engine` (Jakub)
     * `feature/wisar-module` (Wiktor)
     * `feature/optimizer-dashboard` (Tomasz)
   * Scalanie do gałęzi `main` następuje na koniec każdego sprintu po uprzednim przejściu testów `pytest`.
2. **Krótki cotygodniowy sync (Niedziela, 15 min):**
   * Zwięzła weryfikacja postępów i ustalenie planu na kolejny tydzień.
3. **Podejście iteracyjne:**
   * W pierwszej kolejności wdrażamy prostą, działającą wersję modułu pokrytą testem, a dopiero potem dodajemy szczegóły.
