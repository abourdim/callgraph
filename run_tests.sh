#!/bin/bash
# Callgraph Studio — Unified Test Runner
# Runs all 4 test suites and reports combined results.
#
# Usage: ./run_tests.sh [suite]
#   ./run_tests.sh          Run all suites
#   ./run_tests.sh quick    Skip smoke test (no server needed)
#   ./run_tests.sh smoke    Smoke only
#   ./run_tests.sh deep     Deep only

set -euo pipefail
cd "$(dirname "$0")"

R="\033[31m"; G="\033[32m"; Y="\033[33m"; B="\033[1m"; N="\033[0m"

TOTAL_PASS=0; TOTAL_FAIL=0; TOTAL_SUITES=0; FAILED_SUITES=""

run_suite() {
    local name="$1" cmd="$2"
    echo -e "\n${B}═══ $name ═══${N}"
    TOTAL_SUITES=$((TOTAL_SUITES+1))
    
    local output
    output=$(python3 "$cmd" 2>&1) || true
    echo "$output" | tail -5
    
    # Extract pass/fail counts
    local pass fail
    pass=$(echo "$output" | grep -oP '\d+(?= passed)' | head -1 || echo "0")
    fail=$(echo "$output" | grep -oP '\d+(?= failed| FAILED)' | head -1 || echo "0")
    
    if [ -z "$pass" ]; then pass=0; fi
    if [ -z "$fail" ]; then fail=0; fi
    
    TOTAL_PASS=$((TOTAL_PASS + pass))
    TOTAL_FAIL=$((TOTAL_FAIL + fail))
    
    if [ "$fail" -gt 0 ]; then
        FAILED_SUITES="$FAILED_SUITES $name"
    fi
}

MODE="${1:-all}"

echo -e "${B}╔══════════════════════════════════════════╗${N}"
echo -e "${B}║    Callgraph Studio — Test Runner        ║${N}"
echo -e "${B}╚══════════════════════════════════════════╝${N}"

case "$MODE" in
    all)
        run_suite "Static Tests (test_suite.py)"    "test_suite.py"
        run_suite "Report Tests (test_report.py)"   "report/test_report.py"
        run_suite "Deep Tests (deep_test.py)"        "deep_test.py"
        run_suite "Smoke Tests (smoke_test.py)"      "smoke_test.py"
        ;;
    quick)
        run_suite "Static Tests (test_suite.py)"    "test_suite.py"
        run_suite "Report Tests (test_report.py)"   "report/test_report.py"
        run_suite "Deep Tests (deep_test.py)"        "deep_test.py"
        echo -e "\n${Y}Skipped: smoke_test.py (use './run_tests.sh all' to include)${N}"
        ;;
    smoke)
        run_suite "Smoke Tests (smoke_test.py)"      "smoke_test.py"
        ;;
    deep)
        run_suite "Deep Tests (deep_test.py)"        "deep_test.py"
        ;;
    static)
        run_suite "Static Tests (test_suite.py)"    "test_suite.py"
        ;;
    report)
        run_suite "Report Tests (test_report.py)"   "report/test_report.py"
        ;;
    *)
        echo "Usage: $0 [all|quick|smoke|deep|static|report]"
        exit 1
        ;;
esac

TOTAL=$((TOTAL_PASS + TOTAL_FAIL))

echo ""
echo -e "${B}══════════════════════════════════════════${N}"
if [ "$TOTAL_FAIL" -eq 0 ]; then
    echo -e "  ${G}ALL GREEN${N}  ${B}${TOTAL_PASS}${N}/${TOTAL} passed across ${TOTAL_SUITES} suites"
else
    echo -e "  ${R}${TOTAL_FAIL} FAILED${N}  ${TOTAL_PASS}/${TOTAL} passed across ${TOTAL_SUITES} suites"
    echo -e "  Failed:${FAILED_SUITES}"
fi
echo -e "${B}══════════════════════════════════════════${N}"
echo ""

exit $TOTAL_FAIL
