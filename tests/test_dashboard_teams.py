import asyncio
import json
import sqlite3

from api import app as app_module
from api.services import team_performance_simulator_openai as simulator


def create_dashboard_database(path):
    connection = sqlite3.connect(path)

    try:
        cursor = connection.cursor()
        cursor.executescript(
            """
            CREATE TABLE candidate_personality_scores (
                id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                surname TEXT NOT NULL,
                role TEXT NOT NULL,
                project_name TEXT
            );

            CREATE TABLE team_score (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_member_ids TEXT NOT NULL,
                performance_score REAL NOT NULL,
                summary TEXT,
                project_name TEXT,
                team_vector TEXT,
                rank_position INTEGER,
                generation_id TEXT,
                generation_created_at TEXT
            );
            """
        )
        cursor.executemany(
            """
            INSERT INTO candidate_personality_scores (
                id, first_name, surname, role, project_name
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (1, "Anna", "Nowak", "Project Manager", "New project"),
                (2, "Jan", "Kowalski", "Backend Developer", "New project"),
                (3, "Ewa", "Zielinska", "QA Engineer", "New project"),
            ],
        )
        cursor.executemany(
            """
            INSERT INTO team_score (
                team_member_ids,
                performance_score,
                project_name,
                rank_position,
                generation_id,
                generation_created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (json.dumps([3]), 99, "Old project", 1, "old", "2026-01-01"),
                (json.dumps([1, 2]), 92, "New project", 1, "new", "2026-02-01"),
                (json.dumps([2, 3]), 88, "New project", 2, "new", "2026-02-01"),
                (json.dumps([1, 3]), 84, "New project", 3, "new", "2026-02-01"),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_get_latest_team_from_database(tmp_path, monkeypatch):
    database_path = tmp_path / "dashboard.sqlite"
    create_dashboard_database(database_path)
    monkeypatch.setattr(app_module, "DATABASE_PATH", database_path)

    teams = app_module.get_latest_teams_from_database(limit=1)

    assert len(teams) == 1
    assert teams[0]["generation_id"] == "new"
    assert teams[0]["rank_position"] == 1
    assert [member["name"] for member in teams[0]["team_members"]] == [
        "Anna Nowak",
        "Jan Kowalski",
    ]


def test_get_top_three_from_latest_generation(tmp_path, monkeypatch):
    database_path = tmp_path / "dashboard.sqlite"
    create_dashboard_database(database_path)
    monkeypatch.setattr(app_module, "DATABASE_PATH", database_path)

    teams = app_module.get_latest_teams_from_database(limit=3)

    assert [team["rank_position"] for team in teams] == [1, 2, 3]
    assert [team["performance_score"] for team in teams] == [92, 88, 84]


def test_saved_teams_are_loaded_by_dashboard(tmp_path, monkeypatch):
    database_path = tmp_path / "dashboard.sqlite"
    create_dashboard_database(database_path)
    monkeypatch.setattr(app_module, "DATABASE_PATH", database_path)
    monkeypatch.setattr(simulator, "DATABASE_PATH", database_path)
    payload = app_module.SaveTeamsRequest(
        teams=[
            {
                "project_name": "Saved project",
                "generation_id": "saved-generation",
                "generation_created_at": "2026-03-01T12:00:00+01:00",
                "performance_score": 95,
                "rank_position": 1,
                "team_vector": {"performance_score": 95},
                "summary": "Strong team.",
                "team_members": [
                    {"id": 1, "name": "Anna Nowak", "role": "Project Manager"},
                    {"id": 2, "name": "Jan Kowalski", "role": "Backend Developer"},
                ],
            },
            {
                "project_name": "Saved project",
                "generation_id": "saved-generation",
                "generation_created_at": "2026-03-01T12:00:00+01:00",
                "performance_score": 90,
                "rank_position": 2,
                "team_vector": {"performance_score": 90},
                "summary": "Second team.",
                "team_members": [
                    {"id": 2, "name": "Jan Kowalski", "role": "Backend Developer"},
                    {"id": 3, "name": "Ewa Zielinska", "role": "QA Engineer"},
                ],
            },
        ]
    )

    result = asyncio.run(app_module.save_teams(payload, _user={"role": "recruiter"}))
    teams = app_module.get_latest_teams_from_database(limit=1)

    assert result["success"] is True
    assert len(result["team_score_ids"]) == 2
    assert teams[0]["generation_id"] == "saved-generation"
    assert teams[0]["performance_score"] == 95

    connection = sqlite3.connect(database_path)

    try:
        saved_count = connection.execute(
            "SELECT COUNT(*) FROM team_score WHERE generation_id = ?",
            ("saved-generation",),
        ).fetchone()[0]
    finally:
        connection.close()

    assert saved_count == 2
