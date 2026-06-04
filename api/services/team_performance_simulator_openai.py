import json
import itertools
import uuid
import os
import sqlite3
import logging
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from api.data.project_benchmarks import PROJECT_BENCHMARKS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("uvicorn.error")
LOCAL_TIMEZONE = ZoneInfo("Europe/Warsaw")


def env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


OPENAI_URL = os.getenv(
    "OPENAI_URL",
    "https://api.openai.com/v1/chat/completions",
)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_TIMEOUT = env_int("OPENAI_TIMEOUT", 120)
TEAM_SIMULATION_WORKERS = max(1, env_int("TEAM_SIMULATION_WORKERS", 4))

DATABASE_PATH = PROJECT_ROOT / os.getenv("DATABASE_PATH", "api/dreamteam")

REQUIRED_ROLES = [
    "Project Manager",
    "Product Owner",
    "Backend Developer",
    "Frontend Developer",
    "QA Engineer",
    "DevOps Engineer",
]

TEAM_VECTOR_KEYS = [
    "performance_score",
    "collaboration_score",
    "communication_score",
    "delivery_score",
    "risk_score",
]

TEAM_SCORE_EXTRA_COLUMNS = {
    "project_name": "TEXT",
    "generation_id": "TEXT",
    "generation_created_at": "TEXT",
    "team_vector": "TEXT",
    "rank_position": "INTEGER",
}


def call_openai(messages, json_format=False):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.2,
    }

    if json_format:
        payload["response_format"] = {"type": "json_object"}

    request = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=OPENAI_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8")
        raise RuntimeError(
            f"OpenAI API returned HTTP {error.code}: {error_body}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError("Could not connect to OpenAI API.") from error

    return data["choices"][0]["message"]["content"].strip()


def get_candidates_from_database(project_name=None):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        cursor = connection.cursor()
        query = """
            SELECT
                id,
                first_name,
                surname,
                role,
                project_name,
                openness,
                conscientiousness,
                extraversion,
                agreeableness,
                neuroticism
            FROM candidate_personality_scores
        """
        params = []

        if project_name:
            query += " WHERE project_name = ?"
            params.append(project_name)

        cursor.execute(query, params)

        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def ensure_team_score_extra_columns(cursor):
    cursor.execute("PRAGMA table_info(team_score)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for column_name, column_type in TEAM_SCORE_EXTRA_COLUMNS.items():
        if column_name not in existing_columns:
            cursor.execute(
                f"ALTER TABLE team_score ADD COLUMN {column_name} {column_type}"
            )


def save_team_score_to_database(team_result):
    team_member_ids = [candidate["id"] for candidate in team_result["team"]]

    simulation_summary = {
        "project_name": team_result.get("project_name"),
        "generation_id": team_result.get("generation_id"),
        "generation_created_at": team_result.get("generation_created_at"),
        "strengths": team_result.get("strengths", []),
        "risks": team_result.get("risks", []),
        "benchmark_analysis": team_result.get("benchmark_analysis", []),
        "summary": team_result.get("summary", ""),
        "confidence_score": team_result.get("confidence_score"),
        "uncertainty_reason": team_result.get("uncertainty_reason", ""),
        "simulation_runs": team_result.get("simulation_runs", []),
    }

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.cursor()
        ensure_team_score_extra_columns(cursor)
        cursor.execute(
            """
            INSERT INTO team_score (
                team_member_ids,
                performance_score,
                summary,
                project_name,
                generation_id,
                generation_created_at,
                team_vector,
                rank_position
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                json.dumps(team_member_ids),
                team_result["performance_score"],
                json.dumps(simulation_summary),
                team_result.get("project_name"),
                team_result.get("generation_id"),
                team_result.get("generation_created_at"),
                json.dumps(team_result.get("team_vector", {})),
                team_result.get("rank_position"),
            ),
        )

        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def group_candidates_by_role(candidates):
    grouped = {role: [] for role in REQUIRED_ROLES}

    for candidate in candidates:
        role = candidate["role"]

        if role in grouped:
            grouped[role].append(candidate)

    return grouped


def candidate_summary(candidate):
    return {
        "id": candidate["id"],
        "name": f"{candidate['first_name']} {candidate['surname']}",
        "role": candidate["role"],
        "project_name": candidate.get("project_name"),
        "personality": {
            "openness": candidate["openness"],
            "conscientiousness": candidate["conscientiousness"],
            "extraversion": candidate["extraversion"],
            "agreeableness": candidate["agreeableness"],
            "neuroticism": candidate["neuroticism"],
        },
    }


def normalize_llm_result(result):
    if "performance_score" in result:
        return result

    possible_keys = [
        "team_evaluation",
        "evaluation",
        "result",
        "team_result",
        "analysis",
    ]

    for key in possible_keys:
        value = result.get(key)

        if isinstance(value, dict) and "performance_score" in value:
            return value

    return result


def clamp_float(value, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum

    return max(minimum, min(number, maximum))


def simulation_score(result, key):
    return round(clamp_float(result.get(key, 0), 0, 1), 3)


def simulation_variation(run_number):
    variations = [
        "baseline delivery with normal collaboration and typical project friction",
        "higher pressure delivery with ambiguity, interruptions, and time constraints",
        "distributed work with asynchronous communication and slower feedback loops",
        "changing requirements that force reprioritization and negotiation",
        "quality-focused delivery with review pressure and defect prevention",
    ]

    return variations[(run_number - 1) % len(variations)]


def simulate_team_performance(
    team, project_benchmarks, run_number=1, simulation_runs=1
):
    team_data = [candidate_summary(candidate) for candidate in team]

    messages = [
        {
            "role": "system",
            "content": """
You are an expert project team simulator and evaluation analyst.

Run one concrete behavioral simulation of how this team works through the provided project benchmarks.
Do not only evaluate the static team composition. Imagine the team making decisions, communicating, reacting to pressure, resolving conflict, adapting to change, and delivering work.

Use the candidate roles and Big Five personality scores as signals, not as deterministic truth. Avoid stereotyping. Explain outcomes through observable team behaviors such as coordination, decision quality, conflict handling, reliability, adaptability, and delivery discipline.

For each benchmark:
- simulate the likely behavior of the team members based on their roles and Big Five personality scores,
- consider collaboration dynamics, communication quality, reliability, stress response, adaptability, stakeholder alignment, quality discipline, and delivery risk,
- decide what happens in this specific run,
- identify the main positive driver and the main risk driver,
- score the outcome for that benchmark.

Scoring rubric:
- collaboration_score: 0.0-0.3 weak cooperation or unresolved conflict; 0.4-0.6 acceptable cooperation with visible friction; 0.7-0.8 good cooperation with minor issues; 0.9-1.0 excellent mutual support and coordination.
- communication_score: 0.0-0.3 unclear, delayed, or conflicting communication; 0.4-0.6 adequate communication with gaps; 0.7-0.8 clear communication with occasional misses; 0.9-1.0 consistently clear, timely, and well-documented communication.
- delivery_score: 0.0-0.3 high probability of missed goals; 0.4-0.6 partial delivery with trade-offs; 0.7-0.8 reliable delivery of core scope; 0.9-1.0 strong delivery discipline and high execution confidence.
- risk_score: 0.0-0.2 low risk; 0.3-0.5 manageable risk; 0.6-0.8 significant risk requiring mitigation; 0.9-1.0 severe team or delivery risk.

Use these weights when deciding performance_score: delivery 35%, collaboration 25%, communication 20%, risk mitigation 20%. Risk mitigation means lower risk increases performance.

This is one simulation run, not an average of all possible outcomes. If multiple runs are requested, each run should represent a different plausible trajectory.

Return only valid JSON.

You must include exactly these top-level keys:
- performance_score
- collaboration_score
- communication_score
- delivery_score
- risk_score
- strengths
- risks
- benchmark_analysis
- summary
- confidence_score
- uncertainty_reason

Do not rename keys.
Do not wrap the JSON inside another object.
Do not include markdown.
Do not include explanations outside JSON.

The performance_score must be a number from 0 to 100.
Higher means the team is more likely to perform well across all simulated benchmarks.
The collaboration_score, communication_score, delivery_score, and confidence_score must be numbers from 0 to 1 where higher is better.
The risk_score must be a number from 0 to 1 where higher means greater team or delivery risk.
The confidence_score reflects how strongly the provided data supports this prediction, not how good the team is.
The uncertainty_reason must briefly name the main limitation of the prediction.
""",
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "simulation_run": run_number,
                    "total_simulation_runs": simulation_runs,
                    "simulation_variation": simulation_variation(run_number),
                    "team": team_data,
                    "project_benchmarks": project_benchmarks,
                    "required_roles": REQUIRED_ROLES,
                    "output_format": {
                        "performance_score": "number from 0 to 100",
                        "collaboration_score": "number from 0 to 1",
                        "communication_score": "number from 0 to 1",
                        "delivery_score": "number from 0 to 1",
                        "risk_score": "number from 0 to 1 where higher means greater risk",
                        "strengths": [
                            "specific strength with evidence from roles, personality signals, or benchmark behavior"
                        ],
                        "risks": [
                            "specific risk with mitigation hint or scenario where it appears"
                        ],
                        "benchmark_analysis": [
                            {
                                "benchmark_name": "string",
                                "score": "number from 0 to 100",
                                "analysis": "2-4 sentences describing what happened, why it happened, and which team behavior drove the score",
                                "positive_driver": "main behavior or role interaction that helped",
                                "risk_driver": "main behavior or role interaction that hurt or could hurt",
                            }
                        ],
                        "summary": "2-4 sentences summarizing overall simulated behavior, key trade-offs, and the most important mitigation",
                        "confidence_score": "number from 0 to 1 indicating prediction confidence",
                        "uncertainty_reason": "brief explanation of the main limitation of this prediction",
                    },
                }
            ),
        },
    ]

    raw_response = call_openai(messages, json_format=True)
    result = json.loads(raw_response)
    result = normalize_llm_result(result)

    return {
        "run_number": run_number,
        "performance_score": round(
            clamp_float(result.get("performance_score", 0), 0, 100), 2
        ),
        "collaboration_score": simulation_score(result, "collaboration_score"),
        "communication_score": simulation_score(result, "communication_score"),
        "delivery_score": simulation_score(result, "delivery_score"),
        "risk_score": simulation_score(result, "risk_score"),
        "strengths": result.get("strengths", []),
        "risks": result.get("risks", []),
        "benchmark_analysis": result.get("benchmark_analysis", []),
        "summary": result.get("summary", ""),
        "confidence_score": simulation_score(result, "confidence_score"),
        "uncertainty_reason": result.get("uncertainty_reason", ""),
    }


def unique_strings(values, limit=6):
    unique_values = []

    for value in values:
        if value and value not in unique_values:
            unique_values.append(value)

    return unique_values[:limit]


def aggregate_benchmark_analysis(simulations):
    benchmarks = {}

    for simulation in simulations:
        for benchmark in simulation.get("benchmark_analysis", []):
            name = benchmark.get("benchmark_name", "Unknown benchmark")
            benchmarks.setdefault(name, {"scores": [], "analyses": []})
            benchmarks[name]["scores"].append(float(benchmark.get("score", 0)))
            benchmarks[name]["analyses"].append(benchmark.get("analysis", ""))

    return [
        {
            "benchmark_name": name,
            "score": round(sum(data["scores"]) / len(data["scores"]), 2),
            "analysis": " | ".join(unique_strings(data["analyses"], limit=3)),
        }
        for name, data in benchmarks.items()
    ]


def average_simulation_score(simulations, key, digits):
    return round(
        sum(simulation[key] for simulation in simulations) / len(simulations),
        digits,
    )


def average_team_vector_scores(simulations):
    return {
        key: average_simulation_score(simulations, key, 3)
        for key in TEAM_VECTOR_KEYS
        if key != "performance_score"
    }


def average_optional_simulation_score(simulations, key, digits):
    return round(
        sum(simulation.get(key, 0) for simulation in simulations) / len(simulations),
        digits,
    )


def aggregate_simulation_items(simulations, key):
    return unique_strings(
        item for simulation in simulations for item in simulation.get(key, [])
    )


def aggregate_simulation_summary(simulations):
    summaries = unique_strings(
        simulation.get("summary", "") for simulation in simulations
    )

    return f"Average of {len(simulations)} simulation runs. " + " ".join(summaries)


def aggregate_uncertainty_reason(simulations):
    reasons = unique_strings(
        simulation.get("uncertainty_reason", "") for simulation in simulations
    )

    return " | ".join(reasons)


def simulation_run_response(simulation):
    return {
        "run_number": simulation["run_number"],
        "performance_score": simulation["performance_score"],
        "collaboration_score": simulation["collaboration_score"],
        "communication_score": simulation["communication_score"],
        "delivery_score": simulation["delivery_score"],
        "risk_score": simulation["risk_score"],
        "summary": simulation.get("summary", ""),
        "confidence_score": simulation.get("confidence_score", 0),
        "uncertainty_reason": simulation.get("uncertainty_reason", ""),
    }


def aggregate_simulations(simulations):
    return {
        "performance_score": average_simulation_score(
            simulations,
            "performance_score",
            2,
        ),
        **average_team_vector_scores(simulations),
        "strengths": aggregate_simulation_items(simulations, "strengths"),
        "risks": aggregate_simulation_items(simulations, "risks"),
        "benchmark_analysis": aggregate_benchmark_analysis(simulations),
        "summary": aggregate_simulation_summary(simulations),
        "confidence_score": average_optional_simulation_score(
            simulations,
            "confidence_score",
            3,
        ),
        "uncertainty_reason": aggregate_uncertainty_reason(simulations),
        "simulation_runs": [simulation_run_response(item) for item in simulations],
    }


def run_team_simulations(team, project_benchmarks, simulation_runs):
    simulations = [
        simulate_team_performance(
            team,
            project_benchmarks,
            run_number=run_number,
            simulation_runs=simulation_runs,
        )
        for run_number in range(1, simulation_runs + 1)
    ]

    return aggregate_simulations(simulations)


def candidate_team_score(candidate):
    return (
        candidate["conscientiousness"]
        + candidate["agreeableness"]
        + candidate["openness"]
        - candidate["neuroticism"]
    )


def validate_role_coverage(grouped_candidates):
    missing_roles = [
        role
        for role, role_candidates in grouped_candidates.items()
        if not role_candidates
    ]

    if missing_roles:
        raise ValueError(f"Missing candidates for roles: {missing_roles}")


def get_role_candidate_lists(grouped_candidates, max_candidates_per_role):
    role_candidate_lists = []

    for role in REQUIRED_ROLES:
        role_candidates = sorted(
            grouped_candidates[role],
            key=candidate_team_score,
            reverse=True,
        )
        role_candidate_lists.append(role_candidates[:max_candidates_per_role])

    return role_candidate_lists


def build_ranked_team(team, selected_benchmarks, simulation_runs, project_name=None):
    simulation = run_team_simulations(team, selected_benchmarks, simulation_runs)

    return {
        "project_name": project_name,
        "performance_score": simulation["performance_score"],
        "collaboration_score": simulation["collaboration_score"],
        "communication_score": simulation["communication_score"],
        "delivery_score": simulation["delivery_score"],
        "risk_score": simulation["risk_score"],
        "team": [candidate_summary(candidate) for candidate in team],
        "strengths": simulation["strengths"],
        "risks": simulation["risks"],
        "benchmark_analysis": simulation["benchmark_analysis"],
        "summary": simulation["summary"],
        "confidence_score": simulation.get("confidence_score", 0),
        "uncertainty_reason": simulation.get("uncertainty_reason", ""),
        "simulation_runs": simulation["simulation_runs"],
    }


def build_ranked_teams(
    role_candidate_lists,
    selected_benchmarks,
    simulation_runs,
    project_name=None,
    parallel_workers=TEAM_SIMULATION_WORKERS,
):
    team_combinations = list(itertools.product(*role_candidate_lists))
    total_teams = len(team_combinations)
    completed_teams = 0
    progress_lock = Lock()
    started_at = time.perf_counter()
    build_team = partial(
        build_ranked_team,
        selected_benchmarks=selected_benchmarks,
        simulation_runs=simulation_runs,
        project_name=project_name,
    )

    logger.info(
        "Team generation started: project=%s teams=%s simulation_runs=%s workers=%s",
        project_name,
        total_teams,
        simulation_runs,
        max(1, min(parallel_workers, total_teams)) if total_teams else 0,
    )

    def build_team_with_progress(team_item):
        nonlocal completed_teams

        team_number, team = team_item
        team_ids = [candidate["id"] for candidate in team]
        team_started_at = time.perf_counter()

        logger.info(
            "Team simulation started: team=%s/%s project=%s candidate_ids=%s",
            team_number,
            total_teams,
            project_name,
            team_ids,
        )

        try:
            team_result = build_team(team)
        except Exception:
            with progress_lock:
                completed_teams += 1
                completed = completed_teams

            logger.exception(
                "Team simulation failed: team=%s/%s completed=%s/%s project=%s candidate_ids=%s",
                team_number,
                total_teams,
                completed,
                total_teams,
                project_name,
                team_ids,
            )
            raise

        duration = time.perf_counter() - team_started_at

        with progress_lock:
            completed_teams += 1
            completed = completed_teams

        logger.info(
            "Team simulation finished: team=%s/%s completed=%s/%s duration=%.1fs elapsed=%.1fs score=%.2f project=%s",
            team_number,
            total_teams,
            completed,
            total_teams,
            duration,
            time.perf_counter() - started_at,
            team_result["performance_score"],
            project_name,
        )

        return team_result

    if parallel_workers <= 1 or len(team_combinations) <= 1:
        return [
            build_team_with_progress(team_item)
            for team_item in enumerate(team_combinations, start=1)
        ]

    worker_count = min(parallel_workers, len(team_combinations))

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(
            executor.map(
                build_team_with_progress,
                enumerate(team_combinations, start=1),
            )
        )


def build_team_vector(team_result):
    return {
        "performance_score": round(team_result.get("performance_score", 0), 2),
        "collaboration_score": round(team_result.get("collaboration_score", 0), 3),
        "communication_score": round(team_result.get("communication_score", 0), 3),
        "delivery_score": round(team_result.get("delivery_score", 0), 3),
        "risk_score": round(team_result.get("risk_score", 0), 3),
    }


def add_team_map_data(ranked_teams):
    for rank, team_result in enumerate(ranked_teams, start=1):
        team_result["rank_position"] = rank
        team_result["team_vector"] = build_team_vector(team_result)


def generation_metadata(project_name):
    now = datetime.now(LOCAL_TIMEZONE)
    created_at = now.isoformat(timespec="seconds")
    timestamp = now.strftime("%Y%m%dT%H%M%S") + "-pl"
    project_part = "".join(
        character if character.isalnum() else "-"
        for character in (project_name or "project").lower()
    ).strip("-")
    generation_id = f"{project_part or 'project'}-{timestamp}-{uuid.uuid4().hex[:8]}"

    return generation_id, created_at


def add_generation_metadata(ranked_teams, project_name):
    generation_id, created_at = generation_metadata(project_name)

    for team_result in ranked_teams:
        team_result["generation_id"] = generation_id
        team_result["generation_created_at"] = created_at


def save_ranked_teams(ranked_teams):
    for team_result in ranked_teams:
        team_score_id = save_team_score_to_database(team_result)
        team_result["team_score_id"] = team_score_id


def top_team_response(team_result):
    return {
        "project_name": team_result.get("project_name"),
        "generation_id": team_result.get("generation_id"),
        "generation_created_at": team_result.get("generation_created_at"),
        "performance_score": team_result["performance_score"],
        "collaboration_score": team_result.get("collaboration_score"),
        "communication_score": team_result.get("communication_score"),
        "delivery_score": team_result.get("delivery_score"),
        "risk_score": team_result.get("risk_score"),
        "team_vector": team_result.get("team_vector", {}),
        "rank_position": team_result.get("rank_position"),
        "simulation_runs": team_result.get("simulation_runs", []),
        "summary": team_result.get("summary", ""),
        "confidence_score": team_result.get("confidence_score"),
        "uncertainty_reason": team_result.get("uncertainty_reason", ""),
        "team_members": [
            {
                "id": candidate["id"],
                "name": candidate["name"],
                "role": candidate["role"],
                "project_name": candidate.get("project_name"),
            }
            for candidate in team_result["team"]
        ],
    }


def team_map_response(team_result):
    return {
        **top_team_response(team_result),
        "team_score_id": team_result.get("team_score_id"),
        "is_top_team": team_result.get("rank_position", 0) <= 3,
    }


def form_and_rank_teams(
    max_candidates_per_role=2,
    save_to_database=True,
    benchmark_limit=2,
    simulation_runs=2,
    project_name=None,
    include_team_map=False,
    parallel_workers=TEAM_SIMULATION_WORKERS,
):
    selected_benchmarks = PROJECT_BENCHMARKS[:benchmark_limit]

    candidates = get_candidates_from_database(project_name=project_name)
    grouped_candidates = group_candidates_by_role(candidates)
    validate_role_coverage(grouped_candidates)

    role_candidate_lists = get_role_candidate_lists(
        grouped_candidates,
        max_candidates_per_role,
    )

    ranked_teams = build_ranked_teams(
        role_candidate_lists,
        selected_benchmarks,
        simulation_runs,
        project_name=project_name,
        parallel_workers=parallel_workers,
    )

    ranked_teams.sort(
        key=lambda team_result: team_result["performance_score"],
        reverse=True,
    )
    add_team_map_data(ranked_teams)
    add_generation_metadata(ranked_teams, project_name)

    if save_to_database:
        save_ranked_teams(ranked_teams)

    top_teams = [top_team_response(team_result) for team_result in ranked_teams[:3]]

    if include_team_map:
        return {
            "teams": top_teams,
            "team_map": [
                team_map_response(team_result) for team_result in ranked_teams
            ],
        }

    return top_teams
