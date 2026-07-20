from __future__ import annotations

import json
import sys


def main() -> int:
    result = json.load(sys.stdin)
    summary = result.get("summary", {})
    if result.get("status") == "ready":
        passed = summary.get("passed", 0)
        warnings = summary.get("warnings", 0)
        warning_label = "warning" if warnings == 1 else "warnings"
        print(f"iRead check passed: {passed} passed, {warnings} {warning_label}.")
        warning_checks = [
            check for check in result.get("checks", []) if check.get("status") == "warn"
        ]
        if warning_checks:
            details = "; ".join(
                f"{check.get('name')}: {check.get('detail')}"
                for check in warning_checks[:2]
            )
            print(f"Optional setup: {details}")
        return 0

    print("iRead check failed:", file=sys.stderr)
    for check in result.get("checks", []):
        if check.get("status") == "fail":
            print(f"- {check.get('name')}: {check.get('detail')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
