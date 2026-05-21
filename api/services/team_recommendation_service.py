import json
import itertools
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path

from api.data.project_benchmarks import PROJECT_BENCHMARKS


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "llama3"

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "dreamteam"

REQUIRED_ROLES = [
    "Project Manager",
    "Product Owner",
    "Backend Developer",
    "Frontend Developer",
    "QA Engineer",
    "DevOps Engineer",
]


def call_ollama(messages, json_format=False):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }

    if json_format:
        payload["format"] = "json"

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8")
        raise RuntimeError(
            f"Ollama returned HTTP {error.code}: {error_body}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError("Ollama is not running.") from error

    return data["message"]["content"].strip()


def get_candidates_from_database():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                id,
                first_name,
                surname,
                role,
                openness,
                conscientiousness,
                extraversion,
                agreeableness,
                neuroticism
            FROM candidate_personality_scores
            """
        )

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


def simulate_team_performance(team, project_benchmarks):
    team_data = [candidate_summary(candidate) for candidate in team]

    messages = [
        {
            "role": "system",
            "content": """
You are an expert project team evaluator.

Evaluate whether a team is well matched for project work across the provided project benchmarks.

Consider:
- role coverage,
- personality fit,
- collaboration potential,
- ability to handle pressure,
- ability to adapt to change,
- ability to deliver reliably,
- benchmark conditions,
- what each benchmark tests.

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
Higher means the team is more likely to perform well across all benchmarks.
""",
        },
        {
            "role": "user",
            "content": json.dumps(
                {
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
                                "analysis": "string",
                            }
                        ],
                        "summary": "string",
                    },
                }
            ),
        },
    ]

    raw_response = call_ollama(messages, json_format=True)
    result = json.loads(raw_response)
    result = normalize_llm_result(result)

    return {
        "performance_score": float(result.get("performance_score", 0)),
        "strengths": result.get("strengths", []),
        "risks": result.get("risks", []),
        "benchmark_analysis": result.get("benchmark_analysis", []),
        "summary": result.get("summary", ""),
    }


def heuristic_team_score(team):
    avg_openness = sum(candidate["openness"] for candidate in team) / len(team)
    avg_conscientiousness = sum(
        candidate["conscientiousness"] for candidate in team
    ) / len(team)
    avg_extraversion = sum(candidate["extraversion"] for candidate in team) / len(team)
    avg_agreeableness = sum(candidate["agreeableness"] for candidate in team) / len(
        team
    )
    avg_neuroticism = sum(candidate["neuroticism"] for candidate in team) / len(team)

    score = (
        avg_conscientiousness * 30
        + avg_agreeableness * 20
        + avg_openness * 20
        + avg_extraversion * 10
        + (1 - avg_neuroticism) * 20
    )

    return round(score, 2)


def validate_role_coverage(grouped_candidates):
    missing_roles = [
        role
        for role, role_candidates in grouped_candidates.items()
        if not role_candidates
    ]

    if missing_roles:
        raise ValueError(f"Missing candidates for roles: {missing_roles}")


def candidate_sort_score(candidate):
    return (
        candidate["conscientiousness"]
        + candidate["agreeableness"]
        + candidate["openness"]
        - candidate["neuroticism"]
    )


def build_role_candidate_lists(grouped_candidates, max_candidates_per_role):
    role_candidate_lists = []

    for role in REQUIRED_ROLES:
        sorted_candidates = sorted(
            grouped_candidates[role],
            key=candidate_sort_score,
            reverse=True,
        )
        role_candidate_lists.append(sorted_candidates[:max_candidates_per_role])

    return role_candidate_lists


def build_candidate_teams(role_candidate_lists, llm_team_limit):
    candidate_teams = []

    for team in itertools.product(*role_candidate_lists):
        candidate_teams.append(
            {
                "heuristic_score": heuristic_team_score(team),
                "team": team,
            }
        )

    candidate_teams.sort(
        key=lambda team_result: team_result["heuristic_score"],
        reverse=True,
    )

    return candidate_teams[:llm_team_limit]


def evaluate_candidate_teams(candidate_teams, selected_benchmarks):
    ranked_teams = []

    for team_result in candidate_teams:
        team = team_result["team"]
        simulation = simulate_team_performance(team, selected_benchmarks)

        ranked_teams.append(
            {
                "heuristic_score": team_result["heuristic_score"],
                "performance_score": simulation["performance_score"],
                "team": [candidate_summary(candidate) for candidate in team],
                "strengths": simulation["strengths"],
                "risks": simulation["risks"],
                "benchmark_analysis": simulation["benchmark_analysis"],
                "summary": simulation["summary"],
            }
        )

    return ranked_teams


def save_team_scores(ranked_teams):
    for team_result in ranked_teams:
        team_score_id = save_team_score_to_database(team_result)
        team_result["team_score_id"] = team_score_id


def format_top_teams(ranked_teams):
    top_teams = ranked_teams[:3]

    return [
        {
            "performance_score": team_result["performance_score"],
            "heuristic_score": team_result["heuristic_score"],
            "team_members": [
                {
                    "id": candidate["id"],
                    "name": candidate["name"],
                    "role": candidate["role"],
                }
                for candidate in team_result["team"]
            ],
        }
        for team_result in top_teams
    ]


def form_and_rank_teams(
    max_candidates_per_role=2,
    save_to_database=True,
    benchmark_limit=2,
    llm_team_limit=10,
):
    selected_benchmarks = PROJECT_BENCHMARKS[:benchmark_limit]
    candidates = get_candidates_from_database()
    grouped_candidates = group_candidates_by_role(candidates)

    validate_role_coverage(grouped_candidates)

    role_candidate_lists = build_role_candidate_lists(
        grouped_candidates,
        max_candidates_per_role,
    )
    candidate_teams = build_candidate_teams(role_candidate_lists, llm_team_limit)
    ranked_teams = evaluate_candidate_teams(candidate_teams, selected_benchmarks)

    ranked_teams.sort(
        key=lambda team_result: team_result["performance_score"],
        reverse=True,
    )

    if save_to_database:
        save_team_scores(ranked_teams)

    return format_top_teams(ranked_teams)
