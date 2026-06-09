# DREAMteam

DREAMteam is a prototype of an intelligent AI assistant for building compatible project teams based on the analysis of candidates' personality traits.

The project focuses on an IT team-building use case. It supports HR teams and project leaders in making faster, more structured decisions when selecting candidates for project groups. Instead of evaluating candidates only individually, DREAMteam analyzes personality profiles, role fit, and team-level compatibility to recommend project team compositions.

## Product Vision

Modern recruitment processes often focus on CV screening, technical skills, and individual interviews. These methods are useful, but they do not fully explain how candidates may collaborate, communicate, handle stress, or adapt to changing project conditions.

DREAMteam aims to support a more holistic team selection process. The system uses an AI-powered chatbot to ask candidates neutral interview questions, estimate their Big Five personality profile, and then simulate how different team compositions may perform across project scenarios.

The final goal is to help organizations:

- reduce mismatched team decisions,
- improve collaboration quality,
- shorten the time needed to form project teams,
- support HR and managers with more transparent AI-assisted recommendations.

## System Scope

The solution can be adapted to different industries, but this prototype focuses on IT project teams.

Each recommended team should include six core roles:

- Project Manager
- Product Owner
- Frontend Developer
- Backend Developer
- QA Engineer
- DevOps Engineer

Each role has a different responsibility profile and therefore benefits from a different combination of technical skills, working style, and personality traits.


## Personality Model

DREAMteam uses the Big Five personality model as the basis for candidate personality analysis. The model describes personality through five major dimensions:

- Openness
- Conscientiousness
- Extraversion
- Agreeableness
- Neuroticism

### Openness

Measures imagination, curiosity, interest in new experiences, ideas, culture, and aesthetics.

High openness may indicate creativity, curiosity, and comfort with new ideas. Low openness may indicate preference for familiar, traditional, or clearly defined approaches.

### Conscientiousness

Measures preference for an organized and disciplined approach to work and life.

High conscientiousness may indicate reliability, planning, consistency, long-term goal orientation, and achievement focus. Lower conscientiousness may indicate a more spontaneous, flexible, or less rule-driven working style.

### Extraversion

Measures the tendency to seek stimulation from the external world and express positive emotions.

High extraversion may indicate sociability, energy, talkativeness, and comfort in group settings. Lower extraversion may indicate preference for individual focus, calm environments, or smaller interactions.

### Agreeableness

Measures focus on maintaining positive relationships and cooperation.

High agreeableness may indicate empathy, trust, cooperation, and willingness to adapt to others. Lower agreeableness may indicate a more independent, direct, or competitive style.

### Neuroticism

Measures tendency to experience stress, nervousness, mood changes, and negative emotions.

High neuroticism may indicate higher sensitivity to stress and pressure. Low neuroticism may indicate calmness, confidence, and emotional stability.

## Team Recommendation Logic

The application combines several steps:

1. The chatbot asks the candidate for basic information and the role they are applying for.
2. The chatbot asks neutral personality-oriented questions.
3. The LLM estimates Big Five scores from 0 to 1.
4. Candidate results are stored in a local SQLite database.
5. The team recommendation service forms candidate combinations with all required roles.
6. A heuristic score is used to reduce the number of team combinations sent to the LLM.
7. The LLM evaluates selected teams against project benchmarks.
8. The system returns the top recommended teams and stores team simulation results for reporting.

## Project Benchmarks

Team performance is evaluated against project scenarios such as:

- Stable Project: predictable, low-stress work with clear requirements.
- Production Crisis: urgent system failure requiring prioritization and crisis communication.
- Iterative Project: controlled change across multiple development phases.
- Demanding Client: unstable requirements and conflicting priorities.
- Distributed Team: remote-only collaboration and asynchronous communication.
- Legacy System: maintenance work with technical debt and regression risk.
- Deadline Cut: reduced timeline and scope prioritization.
- Quality Audit: continuous review and quality discipline.
- Knowledge Gap: missing expertise and learning under uncertainty.
- Team Conflict: diverging opinions and collaboration tension.
- Innovation Challenge: ambiguous problem requiring a unique solution.

## Requirements

- Python 3.12+
- uv
- Ollama
- SQLite

## Setup (uv)

Create the virtual environment and install dependencies:

```bash
uv venv
uv sync
```

Run the app:

```bash
uv run uvicorn app:app --reload
```

## Model and data

### Chatbot requirements

Before running the chatbot, make sure Ollama is installed and the model is available:

```bash
ollama pull llama3
ollama serve
```

If Ollama is already running, `ollama serve` may return:

```text
address already in use
```

This usually means the local Ollama server is already available at:

```text
http://127.0.0.1:11434
```

## Database

The project uses a local SQLite database during development. The local database file should not be committed to GitHub.

Recommended `.gitignore` entries:

```gitignore
api/dreamteam
*.db
*.db-journal
*.sqlite
*.sqlite3
```

The database schema should be stored separately as SQL files, for example:

```text
database/schema.sql
database/seed_demo.sql
```

## Development Scripts

Manual helper scripts can be stored in:

```text
scripts/
```

For example:

```bash
uv run python scripts/run_team_simulation.py
```
