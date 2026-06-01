from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import CheckpointCallback
except ImportError:  # pragma: no cover - optional dependency
    PPO = None
    CheckpointCallback = None


class PPOAgent:
    def __init__(
        self,
        env: Any,
        model_path: str | Path = "rl/models/sql_ppo_agent.zip",
        checkpoint_dir: str | Path = "rl/models/checkpoints",
        learning_rate: float = 3e-4,
    ) -> None:
        if PPO is None:
            raise ImportError("stable-baselines3 is required to use PPOAgent")
        self.env = env
        self.model_path = Path(model_path)
        self.checkpoint_dir = Path(checkpoint_dir)
        self.learning_rate = learning_rate
        self.model = self._load_or_create()

    def _load_or_create(self):
        if self.model_path.exists():
            return PPO.load(self.model_path, env=self.env)
        return PPO("MlpPolicy", self.env, verbose=1, learning_rate=self.learning_rate)

    def train(self, total_timesteps: int = 10_000, checkpoint_freq: int = 1_000):
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        callback = CheckpointCallback(
            save_freq=checkpoint_freq,
            save_path=str(self.checkpoint_dir),
            name_prefix="sql_ppo",
        )
        self.model.learn(total_timesteps=total_timesteps, callback=callback)
        self.save()
        return self.model

    def predict(self, observation, deterministic: bool = True) -> int:
        action, _ = self.model.predict(observation, deterministic=deterministic)
        return int(action)

    def save(self) -> None:
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save(self.model_path)

    @classmethod
    def load(cls, env: Any, model_path: str | Path):
        agent = cls.__new__(cls)
        if PPO is None:
            raise ImportError("stable-baselines3 is required to load PPOAgent")
        agent.env = env
        agent.model_path = Path(model_path)
        agent.checkpoint_dir = Path("rl/models/checkpoints")
        agent.learning_rate = 3e-4
        agent.model = PPO.load(agent.model_path, env=env)
        return agent

