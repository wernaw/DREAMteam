import json
import itertools
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from api.data.project_benchmarks import PROJECT_BENCHMARKS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

OPENAI_URL = os.getenv(
    "OPENAI_URL",
    "https://api.openai.com/v1/chat/completions",
)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "120"))

DATABASE_PATH = PROJECT_ROOT / os.getenv("DATABASE_PATH", "api/dreamteam")

REQUIRED_ROLES = [
    "Project Manager",
    "Product Owner",
    "Backend Developer",
    "Frontend Developer",
    "QA Engineer",
    "DevOps Engineer",
]


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


def save_team_score_to_database(team_result):
    team_member_ids = [candidate["id"] for candidate in team_result["team"]]

    simulation_summary = {
        "strengths": team_result.get("strengths", []),
        "risks": team_result.get("risks", []),
        "benchmark_analysis": team_result.get("benchmark_analysis", []),
        "summary": team_result.get("summary", ""),
        "simulation_runs": team_result.get("simulation_runs", []),
    }

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO team_score (
                team_member_ids,
                performance_score,
                summary
            )
            VALUES (?, ?, ?)
            """,
            (
                json.dumps(team_member_ids),
                team_result["performance_score"],
                json.dumps(simulation_summary),
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
You are an expert project team simulator.

Run one concrete behavioral simulation of how this team works through the provided project benchmarks.
Do not only evaluate the static team composition. Imagine the team making decisions, communicating, reacting to pressure, resolving conflict, adapting to change, and delivering work.

For each benchmark:
- simulate the likely behavior of the team members based on their roles and Big Five personality scores,
- consider collaboration dynamics, communication quality, reliability, stress response, adaptability, and delivery risk,
- decide what happens in this specific run,
- score the outcome for that benchmark.

This is one simulation run, not an average of all possible outcomes. If multiple runs are requested, each run should represent a different plausible trajectory.

Return only valid JSON.

You must include exactly these top-level keys:
- performance_score
- strengths
- risks
- benchmark_analysis
- summary

Do not rename keys.
Do not wrap the JSON inside another object.
Do not include markdown.
Do not include explanations outside JSON.

The performance_score must be a number from 0 to 100.
Higher means the team is more likely to perform well across all simulated benchmarks.
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
                        "strengths": ["string"],
                        "risks": ["string"],
                        "benchmark_analysis": [
                            {
                                "benchmark_name": "string",
                                "score": "number from 0 to 100",
                                "analysis": "string describing what happened in this run",
                            }
                        ],
                        "summary": "string summarizing the simulated team behavior in this run",
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
        "performance_score": float(result.get("performance_score", 0)),
        "strengths": result.get("strengths", []),
        "risks": result.get("risks", []),
        "benchmark_analysis": result.get("benchmark_analysis", []),
        "summary": result.get("summary", ""),
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


def aggregate_simulations(simulations):
    performance_score = round(
        sum(simulation["performance_score"] for simulation in simulations)
        / len(simulations),
        2,
    )

    strengths = unique_strings(
        strength
        for simulation in simulations
        for strength in simulation.get("strengths", [])
    )
    risks = unique_strings(
        risk for simulation in simulations for risk in simulation.get("risks", [])
    )
    summaries = unique_strings(
        simulation.get("summary", "") for simulation in simulations
    )

    return {
        "performance_score": performance_score,
        "strengths": strengths,
        "risks": risks,
        "benchmark_analysis": aggregate_benchmark_analysis(simulations),
        "summary": f"Average of {len(simulations)} simulation runs. "
        + " ".join(summaries),
        "simulation_runs": [
            {
                "run_number": simulation["run_number"],
                "performance_score": simulation["performance_score"],
                "summary": simulation.get("summary", ""),
            }
            for simulation in simulations
        ],
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


def build_ranked_team(team, selected_benchmarks, simulation_runs):
    simulation = run_team_simulations(team, selected_benchmarks, simulation_runs)

    return {
        "performance_score": simulation["performance_score"],
        "team": [candidate_summary(candidate) for candidate in team],
        "strengths": simulation["strengths"],
        "risks": simulation["risks"],
        "benchmark_analysis": simulation["benchmark_analysis"],
        "summary": simulation["summary"],
        "simulation_runs": simulation["simulation_runs"],
    }


def save_ranked_teams(ranked_teams):
    for team_result in ranked_teams:
        team_score_id = save_team_score_to_database(team_result)
        team_result["team_score_id"] = team_score_id


def top_team_response(team_result):
    return {
        "performance_score": team_result["performance_score"],
        "simulation_runs": team_result.get("simulation_runs", []),
        "summary": team_result.get("summary", ""),
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


def form_and_rank_teams(
    max_candidates_per_role=2,
    save_to_database=True,
    benchmark_limit=2,
    simulation_runs=2,
    project_name=None,
):
    selected_benchmarks = PROJECT_BENCHMARKS[:benchmark_limit]

    candidates = get_candidates_from_database(project_name=project_name)
    grouped_candidates = group_candidates_by_role(candidates)
    validate_role_coverage(grouped_candidates)

    role_candidate_lists = get_role_candidate_lists(
        grouped_candidates,
        max_candidates_per_role,
    )

    ranked_teams = [
        build_ranked_team(team, selected_benchmarks, simulation_runs)
        for team in itertools.product(*role_candidate_lists)
    ]

    ranked_teams.sort(
        key=lambda team_result: team_result["performance_score"],
        reverse=True,
    )

    if save_to_database:
        save_ranked_teams(ranked_teams)

    return [top_team_response(team_result) for team_result in ranked_teams[:3]]
