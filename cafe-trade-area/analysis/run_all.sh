#!/usr/bin/env bash
# 점포개발 심의 알고리즘 v1.0 — 전체 파이프라인
#
#   M1 상권 획정 → M2 수요 변수 → M3 경쟁 배분 → M4 매출 추정
#                                                 ↓
#                                        M5 판정 로직 → M6 사후 보정
#
# 기본은 dry-run(무료·네트워크 없음). --live 를 붙일 때만 외부 API 를 호출한다.
#
#   ./run_all.sh                       # 예시 데이터로 전 과정
#   ./run_all.sh --live                # 등시선·경쟁점 실제 수집까지
#   ./run_all.sh --stores 기존점.example_초기.csv   # Mode B 경로 확인
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
LIVE=""
SITES="후보지.example.csv"
STORES="기존점.example.csv"
ACTUALS="실적.example.csv"
EXTRA=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --live)     LIVE="--live"; shift ;;
    --sites)    SITES="$2"; shift 2 ;;
    --stores)   STORES="$2"; shift 2 ;;
    --actuals)  ACTUALS="$2"; shift 2 ;;
    -h|--help)  sed -n '2,14p' "$0"; exit 0 ;;
    *)          EXTRA+=("$1"); shift ;;
  esac
done

COMMON=(--sites "$SITES" --stores "$STORES" "${EXTRA[@]+"${EXTRA[@]}"}")

echo "════════════════════════════════════════════════════"
echo " 점포개발 심의 파이프라인   후보지=$SITES  기존점=$STORES"
[[ -n "$LIVE" ]] && echo " ⚠ --live: 외부 API 를 실제 호출합니다 (쿼터 소모)"
echo " 사내 한정 · 대외 배포 금지"
echo "════════════════════════════════════════════════════"

echo -e "\n[1/5] M1 등시선"
"$PY" fetch_isochrones.py --sites "$SITES" --stores "$STORES" $LIVE

echo -e "\n[2/5] M3 경쟁점"
"$PY" collect_competitors.py --sites "$SITES" --stores "$STORES" $LIVE

echo
echo "── 배후 인구 H·W (통계청 SGIS · 전국 · 등록 데이터) ──"
"$PY" collect_grid_population.py --sites "$SITES" $LIVE || \
  echo "  ! 격자 인구 수집을 건너뜁니다 — 준비해 둔 격자인구.csv 를 씁니다."

echo
echo "── 유동인구 대용 (서울 상권분석 · 실측 아님) ──"
"$PY" collect_foot_traffic.py --sites "$SITES" $LIVE || \
  echo "  ! 유동인구 대용 수집을 건너뜁니다 — 심의는 계속 진행됩니다."

echo
echo "── 유동인구 커버리지 (전국: 빠진 후보지가 있으면 알려 준다) ──"
# 막지는 않는다(--strict 없음). 다만 자료가 없는 후보지는 D_am 이 0 이 되고 S 가
# 바닥에 깔리므로, 심의표를 읽기 전에 그 사실을 알고 있어야 한다.
"$PY" collect_carrier_flow.py --coverage --sites "$SITES" || true

echo
echo "── 브랜드 매출 벤치마크 (공정위 공시 · 연 1회면 충분) ──"
"$PY" collect_benchmarks.py $LIVE || \
  echo "  ! 벤치마크 수집을 건너뜁니다 — 심의는 계속 진행됩니다."

echo
echo "── 실거래가 (심의표 참고 · 판정에도 매출 추정에도 미사용) ──"
"$PY" collect_transactions.py --sites "$SITES" $LIVE || \
  echo "  ! 실거래가 수집을 건너뜁니다 — 심의는 계속 진행됩니다."

echo -e "\n[3/5] M1~M5 심의표"
"$PY" review_sites.py "${COMMON[@]}"

echo -e "\n[4/5] 후보지별 심의 리포트"
"$PY" build_report.py "${COMMON[@]}"

echo -e "\n[5/5] M6 사후 보정"
if [[ -f "$ACTUALS" ]]; then
  "$PY" calibrate.py "${COMMON[@]}" --actuals "$ACTUALS"
else
  echo "  실적 CSV($ACTUALS)가 없어 건너뜁니다."
  echo "  ⛔ M6 없이는 Mode B 가 순환논리를 벗어나지 못합니다. 개점 후 실적을 반드시 수집하십시오."
fi

echo -e "\n✅ 완료 — output/ 확인"
echo "   · output/심의표.md          판정 한눈에"
echo "   · output/reports/           후보지별 심의 리포트"
echo "   · output/보정_제안.md        계수 교정 제안(사람이 반영)"
echo
echo "사람이 해야 할 일: 07~09시 현장 통행량 실측 · 등기/임대인/소송/인허가 실사 ·"
echo "                  임대조건 협상 · 최종 출점 결정"
