from __future__ import annotations

import argparse
import json

from rl.agent.ppo_agent import PPOAgent
from rl.environment.sql_env import SQLQueryOptimizationEnv, SQLState


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained SQL PPO optimizer.")
    parser.add_argument("--model-path", default="rl/models/sql_ppo_agent.zip")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--query", default="Count all employees")
    parser.add_argument("--sql", default="SELECT COUNT(*) FROM employees;")
    parser.add_argument("--schema-context", default="")
    parser.add_argument("--episodes", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = SQLQueryOptimizationEnv(db_path=args.db_path)
    agent = PPOAgent.load(env, args.model_path)
    scores = []

    for _ in range(args.episodes):
        obs, info = env.reset(options={
            "state": SQLState(
                user_query=args.query,
                schema_context=args.schema_context,
                generated_sql=args.sql,
            )
        })
        done = False
        total = 0.0
        while not done:
            action = agent.predict(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            total += reward
            done = terminated or truncated
        scores.append(total)

    print(json.dumps({
        "episodes": args.episodes,
        "average_reward": sum(scores) / len(scores),
        "scores": scores,
    }, indent=2))


if __name__ == "__main__":
    main()

