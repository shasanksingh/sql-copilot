import io
import os


def test_agent_file_contains_required_sections():
    repo_root = os.path.dirname(os.path.dirname(__file__))
    agent_path = os.path.join(repo_root, "SQL_Copilot.agent.md")
    assert os.path.exists(agent_path), f"Agent file not found: {agent_path}"
    content = io.open(agent_path, "r", encoding="utf-8").read()
    # Check for a few key phrases that should exist in the agent file
    assert "SQL Copilot — Senior Engineering Agent" in content
    assert "sql_generation_policy" in content
    assert "mandatory_process" in content
    assert "confidence_scoring" in content
