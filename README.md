# Berater für KI-Agenten  
### Interaktive Empfehlung von Bosch-Use-Cases und technischen Agenten-Frameworks

---

## Projektbeschreibung

Der **Berater für KI-Agenten** ist ein modular aufgebautes Multi-Agenten-System zur strukturierten Auswahl von KI-Agenten-Architekturen und Frameworks.  
Das System unterstützt Entwickler:innen und Teams dabei, basierend auf konkreten Anforderungen eine fundierte Entscheidung zwischen bestehenden Bosch-Use-Cases oder technischen Frameworks (z. B. LangChain, LangGraph, n8n, Google ADK etc.) zu treffen.

Die Beratung kombiniert:

- deterministisches Framework-Scoring  
- semantische Dokumentenanalyse  
- strukturierte Multi-Agent-Orchestrierung  
- interaktive Benutzerführung (Formular & Chat)

---

## Zielsetzung

Ziel des Projekts ist die Entwicklung eines nachvollziehbaren, modularen Entscheidungsprozesses für KI-Agenten-Architekturen.  
Dabei werden sowohl funktionale Anforderungen als auch Erfahrungslevel und Lernpräferenzen berücksichtigt.

Das System soll:

- reproduzierbare Framework-Bewertungen ermöglichen  
- dokumentationsbasierte Analyse durchführen  
- iterative Qualitätskontrolle unterstützen  
- sowohl Einsteiger:innen als auch Expert:innen bedienen  

---

## Systemarchitektur

Das Projekt besteht aus drei zentralen Ebenen:

1. **Frontend (Streamlit UI)**
2. **Backend (FastAPI)**
3. **Multi-Agenten-Pipeline**

---

## Multi-Agenten-Workflow

Die Empfehlung erfolgt über eine klar strukturierte Agenten-Kette.

### Agentenübersicht

| Agent | Aufgabe |
|--------|----------|
| RequirementsAgent | Strukturierung und Normalisierung der Nutzereingaben |
| ProfilerAgent | Ableitung eines Nutzerprofils (Erfahrung, Lernmodus) |
| UseCaseAnalyzerAgent | Matching mit bestehenden Bosch-Use-Cases |
| FrameworkAnalyzerAgent | Kontextanalyse aus Framework-Dokumentation |
| ScoringAgent | Deterministische Bewertung der Frameworks |
| DecisionAgent | Generierung der strukturierten Empfehlung |
| ControlAgent | Qualitätsprüfung & Iterationssteuerung |
| AdvisorAgent | Sprachliche Finalisierung der Ausgabe |

---

## Entscheidungslogik

1. Anforderungen werden normalisiert  
2. Nutzerprofil wird erstellt  
3. Bosch-Use-Case-Matching wird geprüft  
4. Falls erforderlich: Framework-Pfad  
5. Framework-Analyse + Scoring  
6. Qualitätsprüfung (Threshold & Kontextprüfung)  
7. Iteration bei Bedarf  
8. Generierung der finalen Empfehlung  

---

## Framework-Scoring

Das Framework-Scoring ist vollständig **deterministisch implementiert** und basiert auf einer Capability-Matrix.

### Bewertungsdimensionen

- RAG-Fähigkeit  
- Tool-Integration  
- Workflow-Orchestrierung  
- Multi-Agent-Unterstützung  
- Enterprise-Tauglichkeit  
- Low-Code-Fähigkeit  
- Ecosystem  
- Observability  
- Datenschutz / On-Premise  
- Einsteigerfreundlichkeit  

Die Bewertungslogik befindet sich in:

services/scoring_peer.py

---

### Gewichtungsmechanismus

Die Gewichtung wird dynamisch bestimmt anhand von:

•⁠  ⁠Agententyp  
•⁠  ⁠gesetzten Prioritäten  
•⁠  ⁠Use-Case-Text (abgeleitete Flags)  
•⁠  ⁠Erfahrungslevel  

Die Scores werden relativ normalisiert:

	⁠Bestes Framework = 100 %

---

## Dokumentenanalyse & ChromaDB

Framework-Dokumentationen werden automatisiert erfasst und gespeichert.

### Ingestion

Die Datei:

ingest_framework_docs.py

•⁠  ⁠lädt offizielle Framework-Dokumentation  
•⁠  ⁠zerlegt Inhalte in Chunks  
•⁠  ⁠speichert sie in ChromaDB  
•⁠  ⁠ergänzt pro Framework ein strukturiertes Factsheet  

---

### FrameworkAnalyzerAgent

Dieser Agent:

•⁠  ⁠ruft kontextrelevante Dokument-Snippets ab  
•⁠  ⁠integriert Factsheet-Metadaten  
•⁠  ⁠übergibt strukturierte Analyse an die Entscheidungslogik  

---

## Iterative Qualitätskontrolle

Der ControlAgent prüft:

•⁠  ⁠Sind relevante Snippets vorhanden?  
•⁠  ⁠Ist die höchste Übereinstimmung ausreichend?  
•⁠  ⁠Muss eine erneute Analyse mit erweitertem Kontext erfolgen?  

Bei unzureichender Qualität wird der Analyseprozess wiederholt.

---

## Frontend (Streamlit)

Die Benutzeroberfläche bietet:

•⁠  ⁠geführte Schritt-für-Schritt-Beratung  
•⁠  ⁠kachelbasierte Auswahloptionen  
•⁠  ⁠integrierte Chat-Funktion  
•⁠  ⁠dynamische Anzeige von Use-Cases oder Frameworks  
•⁠  ⁠transparente Prozentdarstellung  

Zwei Modi stehen zur Verfügung:

1.⁠ ⁠Formular-Modus  
2.⁠ ⁠Geführter Chat-Modus  

Beide nutzen denselben Backend-Flow.

---

## Use-Case-Matching

Bosch-Use-Cases werden in Chroma gespeichert und über semantische Ähnlichkeit abgeglichen.

Die Bewertung kombiniert:

•⁠  ⁠Similarity-Score  
•⁠  ⁠Prioritäten-Matching  
•⁠  ⁠Erfahrungs-Matching  
•⁠  ⁠Lernpräferenz  

Die finale Darstellung erfolgt relativ normalisiert.

---

## Projektstruktur

backend/
│
├── api.py
├── services/
│   ├── scoring_peer.py
│   ├── tools.py
│   ├── chroma_client.py
│
├── app_agents/
│   ├── requirements_agent.py
│   ├── profiler_agent.py
│   ├── usecase_analyzer_agent.py
│   ├── framework_analyzer_agent.py
│   ├── scoring_agent.py
│   ├── decision_agent.py
│   ├── control_agent.py
│   ├── advisor_agent.py
│
streamlit_ui/
│   └── app.py

---

## Installation

### Voraussetzungen

•⁠  ⁠Python 3.10+
•⁠  ⁠virtuelle Umgebung empfohlen
•⁠  ⁠OpenAI API Key (.env)

### Abhängigkeiten installieren

```bash
pip install -r requirements.txt


- Backend starten
uvicorn api:app --reload --port 8000

- Steamlit starten
streamlit run streamlit_ui/app.py

Erweiterungsmöglichkeiten

Das System ist modular konzipiert und kann erweitert werden durch:
	•	zusätzliche Frameworks
	•	neue Bewertungsdimensionen
	•	alternative Scoring-Strategien
	•	neue Use-Case-Domänen
	•	weitere Analyse-Agenten

⸻

Technologiestack
	•	Python
	•	FastAPI
	•	Streamlit
	•	ChromaDB
	•	OpenAI Agents SDK
	•	Pydantic

⸻

Besonderheiten
	•	klare Trennung zwischen Scoring-Logik und Textgenerierung
	•	reproduzierbare Bewertung
	•	dokumentationsbasierte Analyse
	•	iterative Qualitätskontrolle
	•	Multi-Agent-Orchestrierung

⸻

Zusammenfassung

Der Berater für KI-Agenten implementiert eine strukturierte, nachvollziehbare Architektur zur Entscheidungsunterstützung bei der Auswahl von Agenten-Frameworks.
Durch die Kombination aus deterministischem Scoring, semantischer Dokumentenanalyse und Multi-Agent-Pipeline entsteht ein transparentes und erweiterbares Beratungssystem.