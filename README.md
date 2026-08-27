# 출점심의 (store-scout)

프랜차이즈 **운영팀·영업팀**을 위한 상권분석 구독 서비스. 조직 단위로
상권분석 알고리즘 M1~M6 을 돌리고 결과를 보관·통제한다.

제품 정의(대상·요금제·팔 수 있는 것과 없는 것)는 **[PRODUCT.md](PRODUCT.md)**.

---

## 알고리즘은 이 저장소에 없다

M1~M6 파이프라인의 원본은
[jasons-company](https://github.com/JasonSJo/jasons-company) 의
`cafe-trade-area/analysis` 한 곳에 둔다. 여기로 복사해 오면 원본이 둘이 되고,
한쪽 계수를 고쳤을 때 다른 쪽이 조용히 어긋난다.

이 서비스는 그 디렉터리를 **서브프로세스로 부른다.** 경로는 자동으로 찾고
(나란히 클론한 경우), 못 찾으면 `STORE_SCOUT_PIPELINE` 로 지정한다.

## 돌려보기

```bash
# 알고리즘 저장소를 나란히 클론
git clone https://github.com/JasonSJo/jasons-company ../jasons-company

pip install -r requirements.txt
python3 seed_demo.py                     # 데모 조직 + 계정 3개 (비밀번호 demo-1234)
python3 -m uvicorn server.app:app --reload
```

`http://127.0.0.1:8000` → `ops@cafehada.kr` / `demo-1234`
후보지 CSV 는 `../jasons-company/cafe-trade-area/analysis/후보지.example.csv` 를 쓰면 된다.
`GET /healthz` 가 `pipeline=yes` 인지로 연결을 확인할 수 있다.

| 환경변수 | 뜻 | 기본값 |
|---|---|---|
| `STORE_SCOUT_DB` | SQLite 경로 | `store-scout.sqlite3` |
| `STORE_SCOUT_PIPELINE` | analysis 디렉터리 | 나란히 클론한 jasons-company 에서 자동 탐색 |
| `STORE_SCOUT_TIMEOUT` | 파이프라인 제한 시간(초) | `600` |
| `STORE_SCOUT_HTTPS` | 값이 있으면 세션 쿠키에 `Secure` | (없음) |

## 설계에서 물러서지 않은 것 넷

이 제품의 위험은 기능이 모자란 게 아니라 **경계가 새는 것**이다.

**1. 조직 경계.** 모든 행이 `org_id` 를 갖고, 조회는 `db.rows_for_org()` 를 통해서만
한다. 남의 조직 자원은 403 이 아니라 **404** 로 답한다 — 403 은 "그 id 가 존재한다"
는 사실을 알려 준다.

**2. 파이프라인은 서브프로세스로 돈다.** `import` 로 끌어 쓰면 파이프라인의 전역 계수
레지스트리(`config.COEFFICIENTS`)가 요청 사이에 공유되어, 한 조직이 넣은 계수가 다른
조직의 판정에 새어 든다. 서브프로세스는 그 사고를 구조적으로 막는다. 실행은 격리된
임시 디렉터리에서 하고 끝나면 지운다.

**3. 매출은 구간으로만 보여 준다.** 단일 숫자를 보여 주면 그 숫자가 상담 자리에서
그대로 인용된다. 내려받는 파일명에는 `internal` 이 박힌다 — 파일이 조직 밖으로
나가도 등급이 함께 간다.

**4. 열람 기록은 의무다.** 로그인·열람·내보내기·실행이 감사 로그에 남는다.
사내 한정 자료를 다루는 이상 기능이 아니다.

## 아직 없는 것

정직하게 적는다. 이 목록이 곧 다음 작업이다.

- **결제.** 요금제 정의와 게이팅은 있지만 청구는 없다. Stripe 등 연동 필요.
- **조직·계정 관리 화면.** 지금은 `seed_demo.py` 나 SQL 로 만든다.
- **비밀번호 재설정 · 2단계 인증.**
- **작업 큐.** 지금은 FastAPI 백그라운드 태스크다. 프로세스가 죽으면 실행 중인
  분석이 '실행중' 에서 멈춘다. 여러 대로 늘리려면 큐(RQ·Celery 등)가 필요하다.
- **속도 제한 · CSRF 토큰.** 폼은 `SameSite=Lax` 쿠키에 기대고 있다.
- **입력·상담 화면 통합.** 지금은 jasons-company 의 `cafe-trade-area/input`,
  `consult` 가 별도 정적 페이지다. 조직 계정과 이어지면 CSV 를 손으로 옮기지 않아도 된다.

## 테스트

```bash
python3 -m unittest discover -s tests
```

기능 검사가 아니라 **사고 방지선** 검사다 — 조직 격리, 권한, 한도 게이팅,
등급 표시, 감사 로그.
