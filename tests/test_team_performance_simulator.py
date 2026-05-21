import json
import sqlite3
import pytest
from api.services import team_performance_simulator as simulator


@pytest.fixture()
def test_database(tmp_path, monkeypatch):
    database_path = tmp_path / "dreamteam"

    connection = sqlite3.connect(database_path)
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE candidate_personality_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            surname TEXT NOT NULL,
            role TEXT NOT NULL,
            openness REAL NOT NULL,
            conscientiousness REAL NOT NULL,
            extraversion REAL NOT NULL,
            agreeableness REAL NOT NULL,
            neuroticism REAL NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE team_score (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_member_ids TEXT NOT NULL,
            performance_score REAL NOT NULL,
            summary TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    candidates = [
        ("Anna", "Kowalska", "Project Manager", 0.7, 0.9, 0.8, 0.8, 0.2),
        ("Julia", "Wisniewska", "Product Owner", 0.9, 0.7, 0.7, 0.8, 0.3),
        ("Karolina", "Wojcik", "Backend Developer", 0.6, 0.9, 0.4, 0.6, 0.2),
        ("Natalia", "Lewandowska", "Frontend Developer", 0.8, 0.7, 0.7, 0.8, 0.3),
        ("Oliwia", "Kaczmarek", "QA Engineer", 0.5, 0.9, 0.4, 0.7, 0.2),
        ("Ewa", "Grabowska", "DevOps Engineer", 0.6, 0.8, 0.5, 0.6, 0.3),
    ]

    cursor.executemany(
        """
        INSERT INTO candidate_personality_scores (
            first_name,
            surname,
            role,
            openness,
            conscientiousness,
            extraversion,
            agreeableness,
            neuroticism
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        candidates,
    )

    connection.commit()
    connection.close()

    monkeypatch.setattr(simulator, "DATABASE_PATH", database_path)

    return database_path


def test_get_candidates_from_database(test_database):
    candidates = simulator.get_candidates_from_database()

    assert len(candidates) == 6
    assert candidates[0]["first_name"] == "Anna"
    assert candidates[0]["role"] == "Project Manager"


def test_group_candidates_by_role(test_database):
    candidates = simulator.get_candidates_from_database()

    grouped = simulator.group_candidates_by_role(candidates)

    assert set(grouped.keys()) == set(simulator.REQUIRED_ROLES)
    assert len(grouped["Project Manager"]) == 1
    assert grouped["Project Manager"][0]["first_name"] == "Anna"


def test_candidate_summary(test_database):
    candidate = simulator.get_candidates_from_database()[0]

    summary = simulator.candidate_summary(candidate)

    assert summary == {
        "id": 1,
        "name": "Anna Kowalska",
        "role": "Project Manager",
        "personality": {
            "openness": 0.7,
            "conscientiousness": 0.9,
            "extraversion": 0.8,
            "agreeableness": 0.8,
            "neuroticism": 0.2,
        },
    }


def test_normalize_llm_result_returns_direct_result():
    result = {
        "performance_score": 88,
        "summary": "Strong team",
    }

    assert simulator.normalize_llm_result(result) == result


def test_normalize_llm_result_returns_nested_result():
    nested = {
        "evaluation": {
            "performance_score": 75,
            "summary": "Good team",
        }
    }

    assert simulator.normalize_llm_result(nested) == nested["evaluation"]


def test_simulate_team_performance(monkeypatch, test_database):
    candidates = simulator.get_candidates_from_database()
    team = candidates[:6]

    fake_llm_response = json.dumps(
        {
            "performance_score": 91,
            "strengths": ["Clear ownership", "Strong planning"],
            "risks": ["Possible communication delay"],
            "benchmark_analysis": [
                {
                    "benchmark_name": "Stable Project",
                    "score": 92,
                    "analysis": "The team should perform well.",
                }
            ],
            "summary": "The team is well balanced.",
        }
    )

    monkeypatch.setattr(
        simulator,
        "call_ollama",
        lambda messages, json_format=False: fake_llm_response,
    )

    result = simulator.simulate_team_performance(
        team,
        [
            {
                "name": "Stable Project",
                "nature": "predictable",
                "description": "Simple project.",
                "conditions": [],
                "tests": [],
            }
        ],
    )

    assert result["performance_score"] == 91.0
    assert result["strengths"] == ["Clear ownership", "Strong planning"]
    assert result["risks"] == ["Possible communication delay"]
    assert result["benchmark_analysis"][0]["benchmark_name"] == "Stable Project"
    assert result["summary"] == "The team is well balanced."


def test_save_team_score_to_database(test_database):
    team_result = {
        "performance_score": 87.5,
        "team": [
            {"id": 1, "name": "Anna Kowalska", "role": "Project Manager"},
            {"id": 2, "name": "Julia Wisniewska", "role": "Product Owner"},
        ],
        "strengths": ["Good planning"],
        "risks": ["Limited stress tolerance"],
        "benchmark_analysis": [
            {
                "benchmark_name": "Stable Project",
                "score": 90,
                "analysis": "Good fit.",
            }
        ],
        "summary": "Good overall fit.",
    }

    row_id = simulator.save_team_score_to_database(team_result)

    connection = sqlite3.connect(test_database)
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT id, team_member_ids, performance_score, summary
        FROM team_score
        WHERE id = ?
        """,
        (row_id,),
    )
    row = cursor.fetchone()
    connection.close()

    assert row[0] == row_id
    assert json.loads(row[1]) == [1, 2]
    assert row[2] == 87.5

    summary = json.loads(row[3])
    assert summary["strengths"] == ["Good planning"]
    assert summary["risks"] == ["Limited stress tolerance"]
    assert summary["summary"] == "Good overall fit."


def test_form_and_rank_teams_returns_top_teams_and_saves_all(
    monkeypatch, test_database
):
    def fake_simulate_team_performance(team, project_benchmarks):
        score = sum(candidate["id"] for candidate in team)

        return {
            "performance_score": score,
            "strengths": ["Test strength"],
            "risks": ["Test risk"],
            "benchmark_analysis": [],
            "summary": "Test summary",
        }

    monkeypatch.setattr(
        simulator,
        "simulate_team_performance",
        fake_simulate_team_performance,
    )

    monkeypatch.setattr(
        simulator,
        "PROJECT_BENCHMARKS",
        [
            {
                "name": "Stable Project",
                "nature": "predictable",
                "description": "Simple project.",
                "conditions": [],
                "tests": [],
            }
        ],
    )

    result = simulator.form_and_rank_teams(
        max_candidates_per_role=1,
        save_to_database=True,
        benchmark_limit=1,
    )

    assert len(result) == 1
    assert result[0]["performance_score"] == 21
    assert len(result[0]["team_members"]) == 6
    assert result[0]["team_members"][0] == {
        "id": 1,
        "name": "Anna Kowalska",
        "role": "Project Manager",
    }

    connection = sqlite3.connect(test_database)
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM team_score")
    saved_rows_count = cursor.fetchone()[0]
    connection.close()

    assert saved_rows_count == 1
