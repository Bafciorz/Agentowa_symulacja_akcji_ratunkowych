# ROZDZIELENIE ZADAŃ NA NAJBLIŻSZE 2 TYGODNIE (SPRINT 1)
## Cel Sprintu: Przejście z determinizmu na stochastykę i zbudowanie agenta WiSAR

---

## 1. ZADANIA DLA JAKUBA BAFII
**Rola:** Architektura DES, Generator Stochastyczny i Modelowanie Urazów  
**Docelowy plik:** `src/core/stochastic_generator.py`  
**Plik testowy:** `tests/test_stochastic_generator.py`

### Co masz konkretnie zrobić w ciągu najbliższych 2 tygodni:
- [x] **Krok 1: Generator napływu wezwań (Proces Poissona)**  
  Napisz funkcję `get_next_incident_delay(sim_time_minutes: float) -> float`.  
  Czasy między kolejnymi zgłoszeniami mają być losowane z rozkładu wykładniczego (`np.random.exponential`). W godzinach szczytu turystycznego (10:00–16:00) wezwania pojawiają się średnio co 60 minut, a poza szczytem rzadziej (np. średnio co 240 minut).
- [x] **Krok 2: Mieszany strumień urazów (kontuzje + zaginięcia)**  
  Stwórz funkcję losującą kategorię wezwania według realistycznych wag GOPR:
  * **40% Drobne kontuzje (`LOW`):** skręcenia kostki, stłuczenia, odwodnienie $\to$ 1 ratownik pieszy, czas opatrywania losowany z rozkładu trójkątnego: `triangular(10, 15, 25)` minut.
  * **30% Poważne urazy (`HIGH`):** złamania nóg, urazy kręgosłupa $\to$ wymóg **2 ratowników i noszy alpejskich**, czas akcji na miejscu: `triangular(20, 30, 45)` minut.
  * **10% Stany krytyczne (`CRITICAL`):** nagłe zatrzymanie krążenia (NZK), głęboka hipotermia $\to$ natychmiastowe wysłanie defibrylatora AED, czas reanimacji: `triangular(25, 40, 60)` minut.
  * **20% Zaginięcia w terenie (`SEARCH`):** zgłoszenie zaginięcia turysty $\to$ przejście do procedury poszukiwawczej.
- [x] **Krok 3: Ważone losowanie lokalizacji wypadku na grafie**  
  Napisz funkcję wybierającą węzeł wypadku z grafu `GORCE_TRAIL_NODES`. Węzły o dużym natężeniu ruchu (Schronisko Turbacz, Hala Długa, Kiczora) powinny mieć większą wagę losowania niż odległe doliny.
- [x] **Krok 4: Testy jednostkowe**  
  Stwórz test w `tests/test_stochastic_generator.py`, sprawdzający czy generator generuje poprawne obiekty `Incident` z prawidłowymi atrybutami i bez błędów.

---

## 2. ZADANIA DLA WIKTORA BUKOWSKIEGO
**Rola:** Modelowanie Zachowania Zaginionego w Terenie (WiSAR / SAR)  
**Docelowy plik:** `src/sar/lost_person.py` *(folder `src/sar/` jest już utworzony w repozytorium)*  
**Plik testowy:** `tests/test_lost_person.py`

### Co masz konkretnie zrobić w ciągu najbliższych 2 tygodni:
- [ ] **Krok 1: Struktura klasy `LostPerson`**  
  Stwórz klasę `LostPerson` reprezentującą zaginionego turystę.  
  Pola: `current_node`, `lkp_node` (Last Known Point), `lost_delay_min` (czas od zagubienia do zgłoszenia), `speed_factor` (np. `0.5–0.7x`, wolniejszy marsz zdezorientowanej osoby), `energy` / `body_temperature` (stan wychłodzenia), `is_mobile` (czy jeszcze ma siły iść), `is_found` (flaga znalezienia).
- [ ] **Krok 2: Algorytm ruchu zaginionego w oparciu o profil wysokościowy DEM**  
  Zaimplementuj metodę `choose_next_node(graph)` oraz krok przejścia po krawędziach:
  * Zaginiony sprawdza sąsiednie węzły w grafie Gorców i ich wysokości n.p.m. ($z$ w `GORCE_TRAIL_NODES` lub grafie DEM).
  * **55–60% szans:** Schodzi w dół zbocza (wybiera sąsiedni węzeł o niższym $z$ – podążanie za grawitacją w stronę dolin potoków).
  * **25–30% szans:** Idzie po ścieżce/grani (losowy sąsiedni węzeł o zbliżonej wysokości).
  * **10–20% szans (rośnie wraz z czasem na mrozie):** Zostaje w miejscu (brak sił, przeczekiwanie, postępująca hipotermia).
- [ ] **Krok 3: Model czasu przed zgłoszeniem + proces SimPy "na żywo"**  
  W rzeczywistości zgłoszenie o zaginięciu wpływa np. po **30–120 minutach** od momentu zagubienia, a w tym czasie zaginiony już się przemieszcza. Aby nie psuć głównego zegara SimPy ani `BenchmarkDataset`, zaimplementuj to w **2 fazach**:
  1. **`simulate_pre_report_movement(delay_min, graph, routing_service)` (przed startem akcji):**  
     W chwili przyjęcia zgłoszenia ($t_{\text{report}}$) puszczasz na obiekcie `LostPerson` krótką wewnętrzną pętlę po czasie `delay_min` (np. 60 min). Dzięki temu już na starcie akcji ratunkowej zaginiony nie stoi w punkcie LKP (np. na Turbaczu), tylko zdążył zejść o 1–2 węzły w stronę dolin!
  2. **`wander_process(env, graph, routing_service)` (ruch równoległy w SimPy podczas akcji):**  
     Po zgłoszeniu uruchamiamy `env.process(lost_person.wander_process(...))`. Zaginiony w każdym kroku wywołuje `yield env.timeout(t_edge)` (liczone przez `routing_service.get_edge_travel_time` z jego `speed_factor`) i aktualizuje `current_node`, dopóki `is_mobile == True` oraz `not is_found`.
- [ ] **Krok 4: Spadek formy zaginionego w warunkach zimowych**  
  Dodaj prosty model wychłodzenia zależny od `WeatherConditions`: z upływem minut na śniegu/wietrze spada energia zaginionego, aż przy wyczerpaniu ustawia `is_mobile = False` (siada pod drzewem i czeka na odnalezienie).
- [ ] **Krok 5: Testy jednostkowe**  
  Stwórz test w `tests/test_lost_person.py` weryfikujący:
  * czy `simulate_pre_report_movement` przesuwa zaginionego po sąsiednich węzłach grafu w ramach zadanego czasu,
  * czy zaginiony nie wyskakuje poza graf i preferuje schodzenie w dół ($z_{\text{next}} < z_{\text{curr}}$),
  * czy po ustawieniu `is_found = True` proces `wander_process` w SimPy bezpiecznie się zatrzymuje.

> 💡 **Notatka integracyjna na koniec (dla połączenia z Ratownikiem / Dyspozytorem):**  
> * W incydencie typu `SEARCH` pole `incident.target_node` będzie oznaczać wyłącznie **LKP** (punkt znany dyspozytorowi), natomiast prawdziwą ukrytą pozycją będzie `lost_person.current_node`.  
> * W `src/core/rescuer.py` jest już przygotowany stan `RescuerState.SEARCHING` – w kolejnym kroku (Sprint 2) ratownik po dotarciu do LKP przejdzie w ten stan i zacznie przeszukiwać sąsiednie węzły (najpierw te niżej położone – najwyższe POA), aż trafi na `rescuer.current_node == lost_person.current_node`.

---

## 3. ZADANIA DLA TOMASZA CHMIELOWSKIEGO
**Rola:** Optymalizacja Symulacyjna i Architektura Grafu (Przeniesienie Obliczeń na Krawędzie)  
**Docelowe pliki:** `src/routing/gorce_trails_network.py` (lub krawędzie grafu), `src/optimization/base_optimizer.py`  
**Plik testowy:** `tests/test_optimizer.py`, `tests/test_gorce_trails.py`

### Co masz konkretnie zrobić w ciągu najbliższych 2 tygodni:
- [ ] **Krok 1: Przeniesienie obliczania odległości i czasów na krawędzie grafu (Edge-Level Precalculation)**  
  Przenieś logikę wyliczania geometrii i czasów bezpośrednio do atrybutów krawędzi grafu (`G[u][v]` w `gorce_trails_network.py`):
  * Każda krawędź grafu powinna mieć statycznie wyliczone i zapisane w słowniku:
    * `distance_2d` [m] (odległość w rzucie poziomym),
    * `elevation_change` [m] (różnica wysokości $\Delta z$),
    * `distance_3d` [m] (rzeczywista długość trójwymiarowa $\sqrt{d_{2d}^2 + \Delta z^2}$),
    * `base_travel_time_min` (bazowy czas przejścia wyliczony ze wzoru Campbella-Sullivana/Lorentza),
    * `vehicle_accessible: bool` (flaga przejezdności dla quada/skutera – `True` dla dróg i szlaków, `False` dla trudnych wiatrołomów).
  * **Dlaczego to kluczowe:** Dzięki temu trasowanie Dijkstry i algorytm optymalizacyjny nie muszą przeliczać trygonometrii w locie przy każdym kroku agenta — odczyt z krawędzi grafu jest natychmiastowy (skraca czas masowych symulacji z sekund do milisekund).
- [ ] **Krok 2: Sformułowanie przestrzeni decyzyjnej optymalizatora**  
  Zdefiniuj wektor zmiennych decyzyjnych reprezentujący obsadę baz GOPR w Gorcach:
  * Dostępne punkty bazowe:
    1. `Schronisko_Turbacz` (Stacja Główna),
    2. `Stare_Wierchy` (Podstacja Zachodnia),
    3. `Kowaniec_NowyTarg` (Baza Dolna / Quady),
    4. `Przelecz_Knurowska` (Punkt Wschodni).
  * Zmienne decyzyjne: ile ratowników zawodowych, ilu ochotników i jaki sprzęt (quad/nosze) przydzielić do każdej z tych 4 baz przy stałym łącznym limicie (np. max 6 zawodowych, 8 ochotników, 2 quady).
- [ ] **Krok 3: Definicja funkcji celu (Fitness Function)**  
  Napisz funkcję kosztu, która będzie minimalizowana:
  $$J = \overline{T}_{\text{response}} + w_1 \cdot P_{95}(\text{Triage}) + w_2 \cdot \text{Kary\_za\_przekroczenie\_budzetu}$$
  gdzie celem jest zminimalizowanie średniego czasu dotarcia do wypadków oraz 95-percentyla czasu dla wezwań krytycznych.
- [ ] **Krok 4: Szkielet algorytmu optymalizacyjnego**  
  Napisz wstępny algorytm (np. prosty algorytm genetyczny lub przeszukiwanie losowe / symulowane wyżarzanie), który generuje próbne konfiguracje obsady baz i ocenia je za pomocą funkcji testowej.
- [ ] **Krok 5: Testy jednostkowe**  
  Stwórz testy weryfikujące poprawność atrybutów na krawędziach grafu oraz ograniczeń zasobowych w optymalizatorze.

---

## 4. WSPÓLNA CHECKLISTA NA KONIEC SPRINTU 1 (ZA 2 TYGODNIE)

Po 2 tygodniach spotykacie się na 15 minut i sprawdzacie:
1. Czy `pytest tests/` przechodzi ze wszystkimi nowymi testami (generator Jakuba, ruch zaginionego Wiktora, optymalizator Tomasza)?
2. Czy potraficie z gałęzi scalić kod do `main` bez konfliktów?
3. Jeśli tak $\to$ **Sprint 1 zakończony sukcesem**, ruszacie do Sprintu 2 (łączenie poszukiwań z dyspozytorem i pętla masowych symulacji Monte Carlo).
