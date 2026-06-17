from pathlib import Path
from tools.confidence_benchmark import run_benchmark


def test_benchmark_runs_and_writes_report(tmp_path: Path):
    out = run_benchmark(out_dir=tmp_path)
    assert out["total"] >= 100
    assert Path(out["csv"]).exists()
