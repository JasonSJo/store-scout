# 배포

이 서비스는 **조직 데이터를 담는 상태 있는 서버**다. 정적 사이트나 서버리스 함수가
아니다. 배포 전에 이 문서의 「먼저 정하고 갈 것」 세 가지를 읽으십시오 — 나중에
바꾸려면 데이터를 옮겨야 하는 것들입니다.

---

## 먼저 정하고 갈 것

### 1. 인스턴스는 **하나**여야 한다

늘리면 안 되는 이유가 둘 다 구조에서 온다.

- 상태가 **SQLite 파일**에 있다. 인스턴스마다 자기 볼륨을 붙이므로, 둘로 늘리면
  A 인스턴스에 로그인한 사람과 B 에 로그인한 사람이 서로 다른 데이터를 본다.
  화면은 멀쩡해 보이고 데이터만 조용히 갈라진다.
- 심의 실행이 **그 프로세스 안의 백그라운드 작업**이다. 요청을 받은 인스턴스가
  아닌 곳에서는 그 실행의 존재조차 모른다.

`fly.toml` 과 `render.yaml` 이 인스턴스 1개를 강제하고, 테스트가 그 값을 지킨다
(`test_배포_설정이_전부_같은_볼륨을_가리킨다`). 늘려야 할 만큼 커지면 SQLite → Postgres,
백그라운드 태스크 → 작업 큐(RQ·Celery)로 옮기는 것이 먼저입니다.

### 2. 알고리즘 판을 커밋으로 고정한다

이미지는 알고리즘(M1~M6)을 `jasons-company` 에서 **빌드 시점에** 받아 박는다.
`Dockerfile` 의 `PIPELINE_REV` 가 그 커밋 SHA다. 브랜치명을 넣으면 안 된다.

- 판정은 알고리즘 판에 따라 달라진다. `main` 을 따라가면 어제 통과한 후보지가
  오늘 부결이 되고, 왜 바뀌었는지 아무도 모른다.
- 지난 심의를 재현할 수 있어야 한다. **이미지가 곧 알고리즘 판**이다.
- 실행 중에 네트워크를 타지 않는다. 조직 데이터를 다루는 프로세스다.

지금 도는 판은 `GET /healthz` 가 알려 준다: `ok pipeline=yes rev=<SHA>`.
알고리즘을 올릴 때는 `PIPELINE_REV` 를 바꿔 다시 빌드하고, 그 커밋을 배포 기록에
남기십시오.

### 3. 개인정보가 서버에 남는다

상담 화면이 붙으면서 고객 성명·연락처·거주지·근무지가 DB 에 저장된다. 배포는
그것을 인터넷에 올리는 일입니다. 최소한 이 셋:

- **HTTPS 강제.** `STORE_SCOUT_HTTPS=1` 이어야 세션 쿠키에 `Secure` 가 붙는다.
  아래 세 구성 모두 켜 두었지만, 직접 올릴 때 프록시를 안 두면 평문으로 흐릅니다.
- **백업도 개인정보다.** `scripts/backup.py` 가 뜨는 파일에는 기존점 실매출과 고객
  연락처가 그대로 들어 있다. 두는 자리를 서버와 같은 수준으로 통제하거나 암호화하십시오.
- **보관기간.** 상담 기록은 기본 12개월 뒤 파기 대상으로 **표시**만 된다.
  자동으로 지우지 않는다 — 정기 파기는 아직 사람이 합니다(README 「아직 없는 것」).

---

## Fly.io

`fly launch` 는 쓰지 않는다 — 저장소를 훑어 `fly.toml` 을 자기 판단으로 다시 쓰기
때문에, 여기서 정해 둔 볼륨·기계 수·헬스체크가 조용히 바뀐다. 앱을 직접 만들고
이 파일을 그대로 쓴다.

### 한 번만 하는 준비

```bash
# 0. 배포 전 점검 — Fly 에 붙지 않고 확인할 수 있는 것부터
python3 scripts/preflight.py

# 1. flyctl 설치 후 로그인
curl -L https://fly.io/install.sh | sh
fly auth login

# 2. 앱을 만든다. 이름은 Fly 전체에서 유일해야 한다 —
#    store-scout 이 이미 있으면 fly.toml 의 app 을 바꾸고 그 이름으로 만든다.
fly apps create store-scout

# 3. 볼륨. 이름과 지역이 fly.toml 의 [mounts].source · primary_region 과 같아야 한다.
#    여기에 조직 데이터가 들어간다. 이 볼륨을 지우면 복구할 방법이 없다.
fly volumes create scout_data --size 1 --region nrt --app store-scout

# 4. 첫 배포. --remote-only 면 Fly 빌더에서 빌드해 로컬 Docker 가 없어도 된다.
fly deploy --remote-only

# 5. 어느 알고리즘 판이 올라갔는지 확인
curl https://store-scout.fly.dev/healthz     # ok pipeline=yes rev=<SHA>

# 6. 첫 조직과 관리자. 화면에 가입 경로가 없으므로 이걸 해야 들어갈 수 있다.
fly ssh console -C "python3 -m server.bootstrap --org '조직명' --email you@brand.co.kr"
```

6번이 임시 비밀번호를 **한 번만** 출력한다. 옮겨 적고, 터미널 기록에 남았다면 지우십시오.
로그인한 뒤 설정에서 브랜드, 기존점에서 실매출을 넣어야 심의를 돌릴 수 있습니다.

### 그다음부터의 배포

`fly deploy` 를 직접 돌려도 되고, 저장소의 **Actions → Fly 배포 → Run workflow**
로 눌러도 된다. 워크플로가 테스트와 점검을 먼저 돌리고, 배포 뒤 `/healthz` 로
알고리즘 판까지 확인한다. 쓰려면 한 번만:

1. <https://fly.io/user/personal_access_tokens> 에서 토큰 발급
2. 저장소 **Settings → Secrets and variables → Actions** 에 `FLY_API_TOKEN` 으로 저장

push 마다 자동으로 배포하지 않는다. 배포는 프로세스를 갈아 끼우고 그때 돌던 심의는
함께 죽는다(재시작 때 '실패' 로 정리되지만 사용자는 다시 올려야 한다). 언제 끊을지는
사람이 정해야 합니다.

### 도메인

우선 `store-scout.fly.dev` 로 뜬다. 도메인을 사면:

```bash
fly certs add scout.example.com
fly certs show scout.example.com     # 여기 나오는 A/AAAA 레코드를 DNS 에 넣는다
```

### 첫 배포에서 막히는 자리

| 증상 | 원인 | 할 일 |
|---|---|---|
| `Name has already been taken` | 앱 이름이 Fly 전체에서 유일해야 한다 | `fly.toml` 의 `app` 을 바꾸고 다시 `fly apps create` |
| `volume ... not found` | 볼륨 이름·지역이 `fly.toml` 과 다르다 | `[mounts].source` 와 `primary_region` 에 맞춰 다시 만든다 |
| `/healthz` 가 `pipeline=no` | 이미지에 알고리즘이 안 들어갔다 | 빌드 로그의 `git fetch` 단계 확인. 이대로 두면 모든 심의가 실패한다 |
| 헬스체크 실패로 재시작 반복 | 볼륨이 안 붙어 DB 를 못 만든다 | `fly volumes list` 로 붙었는지 확인 |
| `auto_stop_machines` 파싱 오류 | 구버전 flyctl 은 문자열 대신 불리언을 받는다 | `"off"` → `false` |
| 큰 묶음에서 실행이 죽는다 | 메모리 부족 | `[[vm]].memory` 를 올린다 |

## Render

저장소를 연결하고 **New + → Blueprint** 로 `render.yaml` 을 읽힌다. 배포가 끝나면
Shell 에서 한 번:

```bash
python3 -m server.bootstrap --org "조직명" --email you@brand.co.kr
```

> free 플랜은 쓸 수 없습니다. 디스크를 못 붙이고 비활성 시 잠들어서, 도는 중인 심의가
> 사라지고 SQLite 도 남지 않습니다. starter 이상이어야 합니다.

## 직접 서버 (사내 서버·VPS)

```bash
docker compose up -d --build
docker compose exec app python3 -m server.bootstrap --org "조직명" --email you@brand.co.kr
```

기본값이 `127.0.0.1:8000` 에만 연다. 앞에 HTTPS 를 끝내는 리버스 프록시(Caddy·nginx·
Cloudflare Tunnel)를 두고, 그 뒤에 `STORE_SCOUT_HTTPS=1` 을 켜십시오. `backup` 서비스가
올릴 때 한 벌 뜨고 24시간마다 한 벌 떠서 최근 14개를 남깁니다.

---

## 환경변수

| 변수 | 뜻 | 배포 시 |
|---|---|---|
| `STORE_SCOUT_DB` | SQLite 경로 | **반드시 볼륨 안**(`/data/...`). 밖이면 재배포 때 통째로 사라진다 |
| `STORE_SCOUT_HTTPS` | 값이 있으면 세션 쿠키에 `Secure` | HTTPS 뒤라면 `1` |
| `STORE_SCOUT_PIPELINE` | 알고리즘 디렉터리 | 이미지가 `/opt/pipeline/...` 로 설정해 둔다 |
| `STORE_SCOUT_PIPELINE_REV` | 그 알고리즘의 커밋 | 빌드가 주입. `/healthz` 에 나온다 |
| `STORE_SCOUT_TIMEOUT` | 파이프라인 제한 시간(초) | 후보지가 많으면 `900` 이상 |

비밀 키는 없습니다. 비밀번호는 PBKDF2 해시로만 저장하고 세션 토큰은 DB 에 있어,
유출될 서명 키가 존재하지 않습니다.

## 백업과 복구

```bash
# 백업 — 열려 있는 DB 를 일관된 상태로 뜬다 (파일 복사는 안 된다: WAL 이 빠진다)
python3 scripts/backup.py /backup --keep 14

# 복구 — 서버를 멈추고 파일을 제자리에 놓는다
docker compose down
cp /backup/store-scout-20260828T033632Z.sqlite3 /var/lib/docker/volumes/.../store-scout.sqlite3
docker compose up -d
```

## 재시작하면 무슨 일이 나는가

배포·크래시로 프로세스가 죽으면 그때 돌던 심의도 함께 죽는다. 시작할 때 `실행중` 인
행은 예외 없이 죽은 프로세스의 것이므로(인스턴스가 하나이므로) **실패로 정리하고
청구하지 않는다.** 그 사용자는 다시 올려야 합니다. 사용량이 많은 시간대의 재배포는
피하십시오.

## 배포 전 확인

```bash
python3 scripts/preflight.py              # Fly 없이 확인되는 것부터
pip install -r requirements-dev.txt
python3 -m unittest discover -s tests     # 65개 — 조직 격리·권한·개인정보·배포 설정
docker build -t store-scout .
docker run --rm -p 8000:8000 -v scout-data:/data store-scout
curl localhost:8000/healthz               # ok pipeline=yes rev=<SHA>
```

`pipeline=no` 가 나오면 이미지에 알고리즘이 안 들어간 것입니다. 그대로 두면 모든
심의가 실패합니다.
