# FIRETRUST — Technical & Scientific Blueprint
**NASA Space Apps Challenge 2026 · Harmonization of MODIS and VIIRS Hot Spots**
**Version:** 0.1 · 14 novembre 2026 · Blueprint (proposition, aucun résultat expérimental prétendu)

## 0. Vision
> What if the biggest spike on your fire calendar came from a better satellite — not from more fires?

**FIRETRUST** transforme l'historique MODIS (Terra/Aqua) et VIIRS (S-NPP/NOAA-20/NOAA-21) en un calendrier mensuel d'activité des **points chauds détectés**, harmonisé, spatialement consultable, avec statistiques d'anomalie et preuves de fiabilité.

**Promesse démontrable :** comparer des séries sur une échelle VIIRS de référence et visualiser l'incertitude de cette conversion. Ne jamais prétendre reconstruire le nombre exact d'incendies ni la surface brûlée à partir des détections FIRMS.

**Utilisateurs :** analyste en protection civile, gestionnaire d'espace naturel, scientifique, responsable local.

## 1. Exigences du challenge et différenciation
| Exigence du challenge | Livraison vérifiable |
|---|---|
| Historique MODIS+VIIRS | Série mensuelle depuis novembre 2000 dans au moins une région pilote |
| Harmonisation | Modèles comparés; indicateurs de performance sur années tenues à l'écart |
| Calendrier de brûlage | heatmap mois×année, unités et provenance clairement libellées |
| Zone d'intérêt | sélection sur carte, polygone et coordonnées (au moins un mode fonctionnel) |
| Dates / anomalies | filtres et comparaison à la médiane mensuelle historique |
| CSV exportable | détections filtrées, métriques, métadonnées de méthode |
| Présentation | démo fonctionnelle, dépôt de code, preuve de validité, limites |

**Innovations ciblées :**
1. **Sensor Illusion Lab** — avant/après harmonisation, source de chaque segment, effet apparent d'un changement de capteur, bande d'incertitude.
2. **Evidence Ledger / Data Coverage Honesty** — distinction entre `0 détecté`, `pas observé`, `couverture inconnue`, `données préliminaires`; si seules les listes FIRMS de détections existent, marquer « couverture inconnue », jamais « aucun feu ».
3. **Counterfactual Satellite Lens** (extension si validée) — estimer ce que la mission de référence VIIRS aurait compté, avec plage d'incertitude, pour une période observée avec MODIS ; **estimation statistique**, pas vérité terrain ni causalité prouvée.
4. **Decision Brief** — description transparente des anomalies, zones/saisons à surveiller, limites et exports, sans prescriptions d'urgence automatiques.

## 2. Sources et contraintes de données
- NASA FIRMS archive officielle : https://firms.modaps.eosdis.nasa.gov/download/
- Documentation API : https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html
- Description des champs VIIRS : https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html
- NASA FIRMS carte / avertissements : https://firms.modaps.eosdis.nasa.gov/map2/
- Challenge : https://www.spaceappschallenge.org/2026/challenges/modis-and-viirs-hot-spots/

**Chronologies archive (consultées 14/11/2026) :** MODIS C6.1 depuis novembre 2000; VIIRS S-NPP depuis janvier 2012 jusqu'au 2 novembre 2026; NOAA-20 depuis avril 2018; NOAA-21 depuis mars 2023 selon page archive actuelle. Conserver chaque source et sa version de traitement, vérifier les dates réelles des fichiers acquis.

**Champs de base** : `latitude, longitude, acq_date, acq_time (UTC), satellite, instrument, confidence, frp (MW), scan, track, daynight, version` ; `type` peut être présent dans les produits standard et absent des NRT. Ne pas comparer directement les valeurs numériques de `confidence` MODIS (0–100) aux classes VIIRS (`l/n/h`). Ne pas traiter les FRP des deux capteurs comme identiques sans étude dédiée. Documenter filtres, valeurs manquantes, version, traitement.

**Sources supplémentaires conditionnelles** : produit de masque des pixels d'observation (swath/L2 ou gridded fire-mask, pour nuages et absence de couverture), autres produits NASA de surface brûlée (MCD64A1 et VNP64A1) comme **triangulation**, pas comme étiquette parfaite. Les hotspots ne donnent pas la surface brûlée de manière fiable.

## 3. Définition statistique et protocole d'harmonisation
### 3.1 Unité d'analyse
- Grille commune indexée H3 de résolution fixe (par exemple r=7), enregistrer les surfaces réelles des cellules, ou grille en projection égale-surface.
- Compter `active_cell_days` = somme des paires uniques (cellule, date) ayant au moins une détection acceptée. Calculer séparément par capteur / satellite / jour-nuit. Ce n'est pas le nombre d'incendies distincts.
- Table quotidienne puis agrégation mensuelle et annuelle ; la conversion mois local/UTC doit être définie explicitement et rester constante, idéalement calendrier mensuel en UTC pour le MVP.
- Éviter le double comptage lors d'un agrégat multi-satellites: union des cellules-jours, pas somme naïve des satellites; pour calibrer, conserver également les séries individuelles par satellite.

### 3.2 Baselines (ne jamais sauter)
- B0 : concaténation brute, clairement identifiée comme **non harmonisée**.
- B1 : rapport régional/saisonnier `r_{b,m} = sum_t V_{b,m,t} / max(sum_t M_{b,m,t},epsilon)` ; appliquer retrait vers un rapport global/saisonnier pour régions peu renseignées, gérer les zéros.
- B2 (principal) : régression binomiale négative avec lien log / approche Tweedie pour prédire les comptages VIIRS à partir des comptages MODIS et caractéristiques observables au même moment ; caractéristiques candidates = biome, mois, couverture si connue, satellite, fraction jour/nuit, géométrie de scan. Résultats >=0; comparaison stricte aux baselines. Une simple régression linéaire non contrainte est insuffisante (risque de valeurs négatives).
- B3 option : LightGBM avec objectif Poisson/Tweedie et calibration des intervalles sur un jeu séparé, seulement si amélioration objective.

Formule possible pour B2 :

`Y^V_{g,m} ~ NegBin(mu_{g,m}, k)`

`log(mu_{g,m}) = beta_0 + f(log(1+M_{g,m}), biome_g, month_m, sat_g, quality_{g,m})`

C'est la **prédiction du comptage sur l'échelle d'un capteur de référence**. Pas une mesure directe de feux réels. Si M=0, un modèle peut estimer V>0 mais l'intervalle devra être large si l'information est faible ; ne jamais inventer une observation certaine.

### 3.3 Protocole temporel
- Choisir une mission VIIRS de référence **fixe** (par exemple S-NPP pour les années communes) pour éviter de confondre augmentation du nombre de satellites et augmentation des feux.
- Construire des jeux d'entraînement / validation / test **par années entières**, pas en tirage aléatoire de lignes voisines. Exemple : train 2012–2019; validation 2020–2021; test 2022–2024, sous réserve de la disponibilité et des problèmes orbitaux constatés. Justifier toute exclusion.
- Évaluer séparément Terra vs Aqua, puis la continuité après l'arrêt S-NPP avec NOAA-20/21 et modèle de passage inter-VIIRS; ne pas appeler leur union « VIIRS continu » sans standardisation de couverture.
- Évaluer aussi sur une deuxième région à conditions écologiques différentes. Attention aux données de test géographiquement voisines.
- Pour les intervalles : bootstrap en blocs d'années ou validation conformale adaptée aux données dépendantes ; rapporter leur couverture observée, ne pas afficher un `95 %` garanti sans preuve.

### 3.4 Mesures de succès
- `MAE = mean |Y - Yhat|`, sur années test et régions test;
- `WAPE = sum |Y-Yhat| / max(sum |Y|,epsilon)` ; le ratio peut être instable si le comptage total est faible, donc rapporter aussi MAE;
- Biais signé moyen, concordance des mois de pic, stabilité des tendances annuelles, diagnostics par biome et taille de région;
- Intervalles : couverture empirique et largeur moyenne sur test;
- Statistiques séparées pour le mode NRT et standard, car elles ne sont pas équivalentes.

### 3.5 Anomalies
Pour chaque zone `g`, année `y`, mois `m`:

`H_(g,y,m)` = mesure harmonisée; `B_(g,m) = median_{y'≠y} H_(g,y',m)`.

`Delta = H - B`, `relative_change = Delta/max(B,epsilon)` *uniquement si B dépasse un seuil justifié* ; sinon afficher Delta/percentile.

`robust_z = (H-B)/(1.4826 * MAD + epsilon)` si effectif et variation historiques suffisants. Pour mois courant incomplet, comparaison aux périodes historiques tronquées aux mêmes jours; sinon comparer seulement des mois terminés.

**Ne pas produire un « taux de risque d'incendie »** à partir de ces seules données. Une anomalie de hotspots n'est pas une prédiction de danger futur.

## 4. Evidence Ledger — statut des observations
Champ `coverage_status` (période, cellule) :
- `observed`: démontré par un produit de masque d'observation / géométrie et qualité du swath;
- `unobserved`: absence de couverture démontrée;
- `unknown`: aucune information de couverture exploitable, en particulier liste FIRMS de seuls hotspots;
- `partial`: couverture partielle;

Champ indépendant `processing_status`: `standard | nrt | rt | unknown`.

Champ indépendant `model_status`: `validated | low_support | extrapolated | unavailable`.

**INTERDIT :** transformer mécaniquement un mois sans ligne FIRMS en « zéro feu ». Le calendrier peut afficher « 0 hotspot enregistré — couverture inconnue ». Les statuts ne doivent pas être fusionnés en un pourcentage trompeur.

## 5. Architecture recommandée
```
NASA FIRMS CSV / API + (optionnel) swath fire masks
                 |
       Python ingest (streaming)
  schema + provenance + tests + QA
                 |
       Parquet partitionné (immutable)
       capteur / année / pays ou région
                 |
     DuckDB transforms + H3 geocells
                 |
  daily-cell / monthly-cell preaggregates
                 |
       calibration offline / job
      + metrics + model registry
                 |
        FastAPI read-only
       /calendar /series /map
       /sensor-lab /evidence /export
                 |
 React/Next.js + TypeScript + MapLibre
  deck.gl layer + ECharts/visx calendar
```
**Hackathon** : priorité à DuckDB + Parquet préagrégés; PostGIS seulement si filtrage polygonal spatial lourd et multiutilisateur. Redis optionnel. Eviter une base PostgreSQL sans besoin démontré.

### 5.1 Tables logiques
- `raw_observations`: `source_uid`, `satellite`, `sensor`, `lat`, `lon`, `acquired_utc`, `frp`, `confidence_raw`, `processing_version`, `quality_tier`, `type_raw`, `source_uri`, `ingested_at`.
- `cell_day_sensor`: `(grid_id, utc_day, satellite, daynight)`, `detection_count`, `active_flag`, `frp_sum_raw`, `support_qa`.
- `cell_month_reference`: `(grid_id, month, reference_sensor, model_version)`, `activity_estimate`, `lower`, `upper`, `coverage_status`, `quality`, `n_active_cell_days`.
- `model_validation`: `model_id`, `train_period`, `test_period`, `region`, `baseline`, `MAE`, `WAPE`, `coverage`, `notes`.
- `source_manifest`: fichier source, hash, date d'acquisition, type de traitement, nombre de lignes, version, licence/attribution.

### 5.2 API minimale
- `POST /api/v1/areas/validate` — polygone GeoJSON; limite surface, sommets, coordonnées valides.
- `GET /api/v1/calendar?area_id=&start=&end=&model=` — matrice mensuelle + provenance/flags.
- `GET /api/v1/timeseries?area_id=&aggregation=month&view=raw|harmonized`.
- `GET /api/v1/sensor-comparison?area_id=&start=&end=` — séries et baselines, pas de faux alignement temporel.
- `GET /api/v1/anomalies?area_id=&month=` — médiane, delta, rang, incertitude.
- `GET /api/v1/tiles/{z}/{x}/{y}` — points/clusters/hexagones selon zoom, ou fichiers PMTiles statiques.
- `GET /api/v1/exports/csv?area_id=&start=&end=&mode=raw|aggregate` — données + colonnes de provenance.
- `GET /api/v1/method` — description versionnée et métriques de validation.

Gestion des requêtes : cache clé `hash(geometry|range|aggregation|model_version|data_snapshot)`, pagination/streaming exports, pas de chargement de tout le CSV global pour une requête. Appliquer limites de taux / taille d'export.

### 5.3 Objectifs de performance (à mesurer, PAS résultats acquis)
- Calendrier préagrégé d'une zone pilote, p95 < 500 ms côté API, machine de démo identifiée.
- Navigation carte et changement de filtre sans blocage du thread principal.
- Charges initiales légères via agrégats et tiles; pas d'envoi de millions de points au navigateur.
- Traiter le dataset par lots; tests d'idempotence d'ingestion et absence de doublons.
- Trace de benchmarks reproductibles : volume, RAM, CPU, machine, taux de cache, p50/p95.

## 6. Frontend : direction artistique et expérience
**Langage visuel** : « mission control × atlas scientifique », très lisible, sobre, haut de gamme. Palette : fond ardoise profond `#0D1521`, cartes `#162233`, texte clair `#F7F6F2`, bleu pétrole `#25B2A2` (harmonisé), ambre `#F4A340` (brut/attention), corail `#EA6653` (activité), gris clair pour inconnu. Palette accessible; ne jamais coder l'incertitude par couleur seule (icône, motif, libellé).

**Vue 1 / Explorer** : carte mondiale MapLibre, polygone libre / région rapide; chronologie; KPI contextualisés; légende très claire. Carte = activité détectée, pas périmètres de feu.

**Vue 2 / Burning Calendar** : années 2000–2026 en lignes, mois en colonnes; commutateur « activité / anomalie / fiabilité »; tooltip : estimate, intervalle, source, statut, disponibilité. Mode comparaison à la médiane du mois.

**Vue 3 / Sensor Illusion Lab** : brut vs harmonisé + bande d'incertitude; cursors synchronisés; transitions Terra/Aqua, S-NPP, NOAA-20, NOAA-21 annotées; panneau preuve « how it was computed » avec méthode & métriques test.

**Vue 4 / Evidence & Brief** : labels distincts `observé`, `couverture inconnue`, `NRT`, `extrapolé` et rapport narratif piloté par règles; export CSV, PNG (PDF facultatif).

Interaction phare pour démo : « Avez-vous vraiment eu 2× plus de feux, ou 2× plus de détections ? » — bascule synchronisée avec animation discrète, chiffres réels validés. Respecter clavier, contraste et responsive.

## 7. Workflow de réalisation sous forte contrainte de temps
**Gate A — Data** : un échantillon NASA réel, deux séries vérifiées, traçabilité; ne pas avancer en prétendant avoir des données mondiales sans téléchargement.

**Gate B — Science** : baseline ratio, modèle calibré, test années tenues à l'écart, métriques horodatées. Si le modèle B2 ne surpasse pas B1, utiliser B1 et expliquer pourquoi.

**Gate C — Product** : sélectionner zone/date, obtenir calendrier/anomalie, visualiser bruts/corrigés, exporter CSV. Tout fonctionne avec un jeu de données réel fixé.

**Gate D — Distinction** : Evidence Ledger et « Satellite Lens »; ne montrer une couverture comme vérifiée que si les produits complémentaires ont effectivement été intégrés.

**Gate E — Final** : vidéo scénarisée, README, guide de reproduction, démonstration déployée, attribution NASA et déclarations d'utilisation IA; liens accessibles publiquement. Respecter l'heure limite officielle de l'événement local.

## 8. Protocole d'honnêteté scientifique
- Les détections sont des **anomalies thermiques**; elles peuvent inclure végétation, agriculture, volcans et sources fixes. `type` peut aider mais n'est pas universel ni disponible dans tous les produits.
- Les comptes ne correspondent pas à un nombre de feux distincts.
- Le FRP est en MW et n'est pas le nombre de hotspots; ne pas sommer et comparer entre capteurs sans étude de biais.
- Les archives standard diffèrent de NRT; conserver snapshot et affichage de provenance.
- Ne pas extrapoler de statistiques au monde entier depuis une unique zone pilote.
- Pas de prédiction d'incendie ni de « garantie 95 % » sans mesures sur un test indépendant.
- Ne pas employer pour l'alerte critique à la sécurité de personnes; outil d'analyse exploratoire de l'historique.

## 9. Dépôt suggéré
```
firetrust/
  apps/web/                 # React / TS / MapLibre / charts
  services/api/             # FastAPI routes and schemas
  packages/science/         # metrics, calibration, intervals
  pipelines/                # FIRMS ingestion, QC, aggregation
  data/manifests/           # source provenance and hashes
  notebooks/                # public independent validation
  tests/                    # unit, integration, regression
  docs/METHOD.md            # units, baselines, equations
  docs/VALIDATION.md        # true held-out results
  docs/LIMITATIONS.md       # scientific limitations
  docs/DATA_SOURCES.md      # NASA citations and licenses
  docs/DEMO.md              # scripted 2-minute scenario
```

## 10. Evaluation : pourquoi l'approche est compétitive
- **Impact** : un gestionnaire comprend les périodes critiques et les limites des données.
- **Creativity** : interface contrefactuelle « illusion du capteur » + preuve de fiabilité.
- **Validity** : baseline, méthodes physiquement admissibles, validation spatiale/temporelle, uncertainties.
- **Relevance** : cœur du challenge — harmonisation MODIS/VIIRS + calendrier.
- **Presentation** : une histoire visuelle avant/après, puis décision claire.

**Décision critique :** si l'on ne peut pas acquérir les fire masks durant le hackathon, le module Evidence doit explicitement indiquer `coverage unknown`; l'innovation reste la transparence et la traçabilité, pas une couverture artificiellement inférée.

---
Document de planification. Aucune mesure, précision de modèle ou performance technique n'est déclarée comme obtenue tant qu'elle n'est pas reproduite et consignée dans `docs/VALIDATION.md`.
