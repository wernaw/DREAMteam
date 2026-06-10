import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_LIMIT = 10
MAX_CANDIDATES_PER_ROLE = 2
TEAM_LIMIT = 64
SIMULATION_RUNS = 5
PARALLEL_WORKERS = 4

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main():
    from api.services.team_recommendation_service import (
        PROJECT_BENCHMARKS,
        build_candidate_teams,
        build_role_candidate_lists,
        candidate_summary,
        get_candidates_from_database,
        group_candidates_by_role,
        simulate_team_performance,
        validate_role_coverage,
    )

    print("Full-scope team simulation")
    print(f"Benchmarks: {BENCHMARK_LIMIT}")
    print(f"Team combinations per run: {TEAM_LIMIT}")
    print(f"Simulation runs: {SIMULATION_RUNS}")
    print(f"Parallel workers: {PARALLEL_WORKERS}")
    print(f"Expected LLM calls: {TEAM_LIMIT * SIMULATION_RUNS}")
    print("Results will not be saved to the database.\n")

    candidates = get_candidates_from_database()
    grouped_candidates = group_candidates_by_role(candidates)
    validate_role_coverage(grouped_candidates)
    role_candidate_lists = build_role_candidate_lists(
        grouped_candidates,
        MAX_CANDIDATES_PER_ROLE,
    )
    candidate_teams = build_candidate_teams(role_candidate_lists, TEAM_LIMIT)
    selected_benchmarks = PROJECT_BENCHMARKS[:BENCHMARK_LIMIT]

    total_start_time = time.perf_counter()
    run_results = []

    for run_number in range(1, SIMULATION_RUNS + 1):
        print(f"Starting simulation run {run_number}/{SIMULATION_RUNS}...")
        run_start_time = time.perf_counter()
        ranked_teams = []

        def evaluate_team(team_result):
            team = team_result["team"]
            simulation = simulate_team_performance(
                team,
                selected_benchmarks,
                run_number=run_number,
                simulation_runs=SIMULATION_RUNS,
            )

            return {
                "heuristic_score": team_result["heuristic_score"],
                "performance_score": simulation["performance_score"],
                "team_members": [candidate_summary(candidate) for candidate in team],
            }

        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = [
                executor.submit(evaluate_team, team_result)
                for team_result in candidate_teams
            ]

            for completed_count, future in enumerate(
                as_completed(futures),
                start=1,
            ):
                ranked_teams.append(future.result())
                print(
                    f"  Completed team {completed_count}/{len(candidate_teams)}",
                    flush=True,
                )

        ranked_teams.sort(
            key=lambda team_result: team_result["performance_score"],
            reverse=True,
        )

        run_time = time.perf_counter() - run_start_time
        run_results.append(
            {
                "run_number": run_number,
                "execution_time_seconds": round(run_time, 2),
                "top_teams": ranked_teams[:3],
            }
        )
        print(
            f"Finished run {run_number}/{SIMULATION_RUNS} "
            f"in {run_time:.2f} seconds ({run_time / 60:.2f} minutes).\n"
        )

    total_time = time.perf_counter() - total_start_time

    print(json.dumps(run_results, indent=2))
    print("\nPerformance summary")
    print(f"Benchmarks per team: {BENCHMARK_LIMIT}")
    print(f"Team combinations per run: {TEAM_LIMIT}")
    print(f"Simulation runs: {SIMULATION_RUNS}")
    print(f"Parallel workers: {PARALLEL_WORKERS}")
    print(f"Total LLM calls: {TEAM_LIMIT * SIMULATION_RUNS}")
    print(f"Total execution time: {total_time:.2f} seconds")
    print(f"Total execution time: {total_time / 60:.2f} minutes")
    print(
        f"Average time per simulation run: {total_time / SIMULATION_RUNS:.2f} seconds"
    )


if __name__ == "__main__":
    main()
