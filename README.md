# Premier League Set-Piece Intelligence & Aerial Mismatch Engine

An end-to-end **First-Team Set-Piece Performance Analysis Platform** built with **Python, DuckDB, StatsBomb Open Data, `mplsoccer`, Streamlit, and `fpdf2`**. Designed to replicate Premier League club set-piece analyst workflows across **pre-match opposition scouting**, **single-match post-match review**, **Hudl Sportscode video integration**, and **automated 2-page matchday PDF briefing generation**.

**[Live Interactive App (Streamlit Cloud)](https://streamlit.app)** · **[GitHub Repository](https://github.com)**

---

## System Architecture

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION & STORAGE                          │
│  StatsBomb Open Data (380 PL Fixtures) ──► DuckDB (pl_setpieces.duckdb)  │
│  • set_piece_kicks (Corners, Attacking Free Kicks, Long Throws)          │
│  • set_piece_events (1st Contact, 2nd Contact, 3rd+ Phase Shots & Goals) │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     ANALYTICS & TACTICAL ENGINES                         │
│  • fulham_pro.py : Hudl HOPS (0.00–1.00) Aerial Duel Calibration,        │
│    Goalkeeper Vulnerability & 7-Archetype Tactical Routine Classifier    │
│  • tactics.py    : Delivery Swing Detection (In/Outswinger/Short/Throw)  │
│  • visuals.py    : mplsoccer Pitch Heatmaps, Phase Chains & Matchups     │
│  • pdf_generator.py : Automated 2-Page Coach & Player Matchday Briefings │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                   INTERACTIVE ANALYST WORKSPACE (app.py)                 │
│  [1] Pre-Match Opposition Scouting   [5] 2-Page Matchday PDF Briefings   │
│  [2] Own Team Review & MW 1–38 Audit [6] Routine Taxonomy & Goal Replay  │
│  [3] Aerial HOPS Mismatch Matrix     [7] League-Wide Set-Piece Table     │
│  [4] Hudl Sportscode .XML Exporter                                       │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Core Modules & Tactical Workflows

### 1. Pre-Match Opposition Scouting & Defensive Vulnerability (`Tab 1`)
* **Event-Chain Set-Piece Modeling:** Links every **Corner**, **Attacking Free Kick**, and **Long Throw** across all 380 Premier League fixtures to its 1st contact, 2nd contact, and 3rd+ phase shots/goals.
* **Delivery & Swing Classification:** Categorizes deliveries into *Inswinger*, *Outswinger*, *Driven / Straight*, *Short Corner*, and *Long Throw* alongside zone-by-zone target heatmaps (`Near Post`, `Central 6-Yard`, `Penalty Spot`, `Far Post`, `Edge of Box`).
* **Goalkeeper & 6-Yard Box Profile:** Evaluates opposition goalkeeper claim/punch activity, 6-yard box aerial dominance, and conceded shot zones.

### 2. Own Team Review & Single-Match Post-Match Audit (`Tab 2`)
* Switches seamlessly between **Full Season / Rolling Form Windows** (`Last 5`, `Last 10`, `All 38`) and **Single-Match Audit Mode (`MW 1` – `MW 38`)**.
* Benchmarks **Attacking 1st-Contact Win %**, **Defensive 1st-Contact Clear %**, and **Expected vs. Actual Goals** with a High-Threat shot/goal pitch filter and 1-click **Post-Match Audit PDF**.

### 3. Hudl HOPS (`0.00–1.00`) Aerial Duel Mismatch Engine (`Tab 3`)
* Calibrates player aerial duel ratings on the standard **`0.00–1.00` HOPS probability scale** (`0.50` = league average) from each club's latest matchday squad.
* Generates side-by-side **1st-Team vs. Opposition Aerial Unit Comparisons** and automatically assigns primary defensive markers to top opposition targets.

### 4. Native Hudl Sportscode `.xml` Exporter (`Tab 4`)
* Exports timeline-ready `.xml` video clip packages with configurable pre-roll/post-roll buffers (`-8s / +12s`) and structured label groups (`Taker`, `Delivery`, `Box Zone`, `Routine`, `Outcome`) for immediate import into Hudl Sportscode timelines.

### 5. Automated 2-Page Coach & Player Matchday PDFs (`Tab 5`)
* Compiles a print-ready **2-page briefing sheet** pairing delivery/conceded pitch maps, primary takers, HOPS aerial rankings, and a 4-point Matchday Action Checklist.

### 6. Tactical Routine Taxonomy & Off-Ball Screen Detector (`Tab 6`)
* Automatically classifies every set piece into **7 tactical archetypes** and ranks efficiency by **Frequency, Shots, Goals, Total xG, and xG / Routine**:
  * *Off-Ball Screen / Lay-Off Routine*
  * *Near-Post Flick-On Routine*
  * *Far-Post Isolation / Back-Post Knockdown*
  * *Short Corner Overload / Angle Shift*
  * *Edge-of-Box D-Arc Cutback*
  * *6-Yard Keeper-Pin & Block*
  * *Standard Central Delivery*

---

## Repository Structure

```text
pl-set-piece-intelligence/
├── app.py                     # Main 7-tab Streamlit analyst interface
├── fulham_pro.py              # HOPS aerial engine, GK metrics & 7-routine classifier
├── visuals.py                 # mplsoccer pitch visualizations & matchup graphics
├── tactics.py                 # Delivery swing & target zone geometry rules
├── pdf_generator.py           # 2-page Coach & Player PDF report builder (fpdf2)
├── sync_premier_league.py     # StatsBomb Open Data ETL pipeline to DuckDB
├── data/
│   └── pl_setpieces.duckdb    # Pre-indexed 380-match relational set-piece database
├── requirements.txt           # Python dependencies for local & Streamlit Cloud
└── README.md                  # Architectural documentation
```

---

## Local Setup

```bash
git clone https://github.com.git
cd pl-set-piece-intelligence
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
