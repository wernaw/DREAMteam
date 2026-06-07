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
- SQLite
- OpenAI API key
- Internet connection for communication with the OpenAI API

## Setup (uv)

Run all commands from the project root directory.

Create the virtual environment and install the dependencies:

```bash
uv venv
uv sync
```

Create a `.env` file in the project root. At minimum, configure the OpenAI API
and credentials used to access the candidate and recruiter views:

```dotenv
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini
OPENAI_URL=https://api.openai.com/v1/chat/completions

JWT_SECRET_KEY=replace_with_a_random_secret
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

CANDIDATE_USERNAME=candidate
CANDIDATE_PASSWORD_HASH=your_bcrypt_password_hash
RECRUITER_USERNAME=recruiter
RECRUITER_PASSWORD_HASH=your_bcrypt_password_hash

DATABASE_PATH=api/dreamteam
```

The password hash can be generated with the helper script in `scripts/`.

Run the application and explicitly load the `.env` file:

```bash
uv run --env-file .env uvicorn api.app:app --reload
```

The application will be available at:

```text
http://127.0.0.1:8000
```

## Model and data

### LLM integration

The current application uses the OpenAI Chat Completions API. The default model
is `gpt-4o-mini`, and it can be changed with the `OPENAI_MODEL` environment
variable.

The model is used in two main stages:

- to conduct an adaptive candidate interview and estimate Big Five personality
  scores,
- to simulate, evaluate, and rank candidate team compositions against project
  benchmarks.

The application requests structured JSON responses and uses a low temperature
of `0.2` to improve consistency.

### Previous local model tests

During the prototyping and testing phase, the project also used the `llama3`
model running locally through Ollama. Some legacy service modules related to
this experiment remain in the repository, but they are not used by the current
FastAPI application. Ollama is therefore not required to run the current
version.

### Tested heuristic and LLM approach

A hybrid recommendation approach combining a deterministic heuristic with an
LLM was also tested during development. Its goal was to reduce the number of
expensive model calls when the number of possible team combinations increased.

The tested pipeline worked as follows:

1. Candidates were grouped by the six required project roles.
2. A simple heuristic ranked candidates and team combinations using Big Five
   scores. Conscientiousness, agreeableness, openness, extraversion, and lower
   neuroticism contributed to the preliminary score.
3. Only the highest-ranked team combinations were sent to the LLM.
4. The LLM evaluated these teams against project benchmarks and produced the
   final performance ranking.

This approach reduced the number of combinations evaluated by the LLM, which
could lower execution time and API cost. Its main limitation was that the
manually selected heuristic weights could reject an unconventional but
potentially effective team before the behavioral simulation stage.

The current application keeps a lighter version of this idea: candidates are
preselected separately within each role using a heuristic score, all
combinations of the selected candidates are then simulated by the LLM, and the
final ranking is based on the aggregated simulation results. The older
team-level heuristic experiment remains in the repository as a legacy service
module.

## Database

The project uses a local SQLite database. Its default path is `api/dreamteam`
and can be changed with the `DATABASE_PATH` environment variable. SQLite was
selected for the prototype because it requires no separate database server and
allows the application, test data, and simulation results to run locally.

The database contains three main tables:

### `projects`

Stores projects available during candidate interviews:

- project identifier,
- unique project name,
- creation timestamp.

### `candidate_personality_scores`

Stores candidate data produced by the interview process:

- first name and surname,
- selected project and project role,
- five Big Five scores: openness, conscientiousness, extraversion,
  agreeableness, and neuroticism,
- complete conversation history serialized as JSON text.

### `team_score`

Stores generated team evaluations:

- identifiers of team members serialized as JSON,
- overall performance score,
- project name and ranking position,
- generation identifier and timestamp,
- team vector containing performance, collaboration, communication, delivery,
  and risk metrics,
- simulation details serialized as JSON, including strengths, risks, benchmark
  analyses, confidence, uncertainty, and individual simulation runs.

The application data flow is:

1. The candidate completes the chatbot interview.
2. The LLM-generated Big Five scores and conversation history are stored in
   `candidate_personality_scores`.
3. The recruiter generates teams for a selected project.
4. Candidate records are read from the database and used to create team
   combinations.
5. LLM simulation results and ranking metadata are stored in `team_score`.
6. The recruiter views use the stored candidate and team data to present
   results and comparisons.

Some structured values are currently stored as JSON text rather than normalized
relational tables. This keeps the prototype schema simple and flexible, but
makes advanced SQL analysis and validation more difficult. A production
version could separate simulation runs, benchmark results, and team membership
into dedicated related tables.

For development and demonstration purposes, the SQLite database is
intentionally included in the repository. It contains only fictional test
records created for application testing. The names, candidate profiles,
interview results, and team evaluations do not represent real people or real
recruitment decisions.

If the application is extended to process real candidate data, the database
must be removed from version control and treated as sensitive
recruitment-related information. Appropriate access control, data
anonymization, retention rules, and privacy safeguards should then be applied.

## Development Scripts

Manual helper scripts can be stored in:

```text
scripts/
```

For example:

```bash
uv run python scripts/run_team_simulation.py
```
