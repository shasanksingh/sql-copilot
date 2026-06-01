from __future__ import annotations

import argparse

from rl.agent.ppo_agent import PPOAgent
from rl.environment.sql_env import SQLQueryOptimizationEnv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train PPO for SQL Copilot query optimization.")
    parser.add_argument("--db-path", default=None, help="SQLite database used for execution feedback.")
    parser.add_argument("--feedback-db-path", default=None, help="SQLite database for agent_feedback.")
    parser.add_argument("--timesteps", type=int, default=10_000)
    parser.add_argument("--model-path", default="rl/models/sql_ppo_agent.zip")
    parser.add_argument("--checkpoint-dir", default="rl/models/checkpoints")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = SQLQueryOptimizationEnv(
        db_path=args.db_path,
        feedback_db_path=args.feedback_db_path or args.db_path,
    )
    agent = PPOAgent(
        env,
        model_path=args.model_path,
        checkpoint_dir=args.checkpoint_dir,
    )
    agent.train(total_timesteps=args.timesteps)


if __name__ == "__main__":
    main()

