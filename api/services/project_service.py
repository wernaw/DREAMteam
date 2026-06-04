import sqlite3

from api.services.database import DATABASE_PATH


def ensure_projects_table():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def add_project(name):
    project_name = name.strip() if name else ""

    if not project_name:
        raise ValueError("Project name is required.")

    ensure_projects_table()
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO projects (name) VALUES (?)",
            (project_name,),
        )
        connection.commit()
    finally:
        connection.close()

    return project_name


def get_project_names():
    ensure_projects_table()
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM projects ORDER BY name ASC")
        return [row[0] for row in cursor.fetchall()]
    finally:
        connection.close()
