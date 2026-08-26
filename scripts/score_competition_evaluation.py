"""Score an ECHO competition evaluation run and export auditable reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPOSITORY_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from evaluation import (  # noqa: E402
    load_actual_results,
    load_frozen_cases,
    score_results,
    write_score_reports,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="根据冻结案例和真实运行结果生成比赛评测指标。",
    )
    parser.add_argument("--run-dir", type=Path, required=True, help="本次运行目录")
    parser.add_argument(
        "--cases",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "member-d" / "eval_50_cases.json",
        help="冻结的 50 组案例文件",
    )
    parser.add_argument(
        "--require-formal",
        action="store_true",
        help="若缺少 50 组结果或人工复核未完成，则返回非零状态",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    cases = load_frozen_cases(args.cases.resolve())
    results = load_actual_results(run_dir / "results")
    summary = score_results(cases, results)
    write_score_reports(run_dir / "reports", summary, results)

    print(f"冻结案例：{summary['case_count']}")
    print(f"实际结果：{summary['result_count']}")
    print(f"人工复核待完成：{summary['pending_human_review_count']}")
    print(f"正式报告条件：{'满足' if summary['formal_ready'] else '不满足'}")
    print(f"报告目录：{run_dir / 'reports'}")
    return 2 if args.require_formal and not summary["formal_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
