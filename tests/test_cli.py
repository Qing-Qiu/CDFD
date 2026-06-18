import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cli_json_output_includes_concurrent_paths():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "cdfd.cli",
            str(ROOT / "examples" / "join.json"),
            "--output-format",
            "json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload["concurrent_paths"][0]["notation"] == "IN -> Split -> [ L || R ] -> Combine -> OUT"
