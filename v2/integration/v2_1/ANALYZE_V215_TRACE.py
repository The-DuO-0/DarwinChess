from __future__ import annotations

"""Analyze a JSONL trace emitted by the isolated V2.1.5 Mac experiment.

Usage:
    PYTHONPATH=v2 python v2/integration/v2_1/ANALYZE_V215_TRACE.py trace.jsonl

The analyzer is deliberately pure Python. It does not import python-chess, torch,
or the live DarwinChess runtime.
"""

from dataclasses import asdict
import json
from pathlib import Path
import sys

from dogmatist_v2.opentree_report import OpenTreeExperimentReport


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: ANALYZE_V215_TRACE.py /path/to/opentree-trace.jsonl")
    path = Path(sys.argv[1]).expanduser().resolve()
    report = OpenTreeExperimentReport.read_jsonl(path)
    summary = report.summarize()
    print(json.dumps(asdict(summary), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
