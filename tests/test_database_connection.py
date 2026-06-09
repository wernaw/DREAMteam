import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parents[1] / "api" / "dreamteam"


def test_database_connection():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1")

        result = cursor.fetchone()[0]

        assert result == 1
    finally:
        connection.close()


def test_database_has_candidate_personality_scores_table():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'candidate_personality_scores'
            """
        )

        table = cursor.fetchone()

        assert table is not None
    finally:
        connection.close()


def test_candidate_personality_scores_columns_exist():
    expected_columns = {
        "id",
        "first_name",
        "surname",
        "role",
        "project_name",
        "openness",
        "conscientiousness",
        "extraversion",
        "agreeableness",
        "neuroticism",
        "conversation_history",
    }

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA table_info(candidate_personality_scores)")

        columns = {row[1] for row in cursor.fetchall()}

        assert expected_columns.issubset(columns)
    finally:
        connection.close()
