import json
import sys
import time
from pathlib import Path
from api.services.team_performance_simulator import form_and_rank_teams


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main():
    start_time = time.perf_counter()

    top_teams = form_and_rank_teams(benchmark_limit=2)

    end_time = time.perf_counter()
    execution_time = end_time - start_time

    print(json.dumps(top_teams, indent=2))
    print(f"\nExecution time: {execution_time:.2f} seconds")


if __name__ == "__main__":
    main()
