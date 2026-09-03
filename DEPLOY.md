# 배포

이 서비스는 **조직 데이터를 담는 상태 있는 서버**다. 정적 사이트나 서버리스 함수가
아니다. 배포 전에 이 문서의 「먼저 정하고 갈 것」 세 가지를 읽으십시오 — 나중에
바꾸려면 데이터를 옮겨야 하는 것들입니다.

---

## 어디에 올릴 것인가

| | 월 비용 | 개인정보 위치 | 밖에서 접속 |
|---|---|---|---|
| **사내 서버 + Cloudflare Tunnel** | 0원 (전기·서버 제외) | 사내 | ✅ |
| 사내 서버만 | 0원 | 사내 | ✕ (사내망만) |
| Fly.io | 상시 기계 1대 + 볼륨 (아래 참고) | 해외 리전 | ✅ |
| Render | starter 이상 (디스크 필수) | 해외 리전 | ✅ |

이용자가 3~10명인 사내 판단 도구다. **사내 서버 + Cloudflare Tunnel** 이 가장
잘 맞는다 — 월 비용이 없고, 고객 개인정보가 국외로 나가지 않고, 영업팀이 현장에서도
쓸 수 있다. 절차는 아래 「사내 서버 + Cloudflare Tunnel」 에 있다.

---

## Fly.io 를 쓸 때 — 결제 수단이 있어야 한다

Fly 는 **결제 수단을 등록해야 앱을 배포할 수 있다.** 없으면 대시보드에 이렇게 뜨고,
토큰이 있어도 배포가 되지 않는다:

> Add a payment method to keep using our platform.
> To start deploying apps you'll need to add a payment method.

    fly.io → Account → Billing 에서 카드를 등록한다.

### 이 구성이 무엇에 과금되는가

무료 구간에 기대는 구성이 **아니다.** 위의 「인스턴스는 하나여야 한다」 때문에
`fly.toml` 이 이렇게 잡혀 있다:

    min_machines_running = 1     기계를 항상 하나 띄워 둔다
    auto_stop_machines   = "off" 놀아도 멈추지 않는다
    size / memory        = shared-cpu-1x / 1gb
    volume               = 1GB

즉 **기계 하나가 24시간 돈다.** 자동 정지를 끈 것은 아껴서 손해 보는 자리라서다 —
심의가 도는 중에 기계가 멈추면 그 실행이 통째로 날아간다. 메모리 1GB 도 마찬가지로,
후보지 수십 곳을 한 번에 돌 때 256MB 에서는 OOM 으로 죽는다.

과금 대상은 **상시 가동 기계 1대 + 볼륨 1GB + 송신 트래픽**이다. 금액은 바뀌므로
https://fly.io/docs/about/pricing/ 에서 확인하십시오. 쓰지 않는 동안에도 계속
나가는 비용이라는 점만 미리 알고 시작하는 편이 낫습니다.

멈춰 두려면 앱을 지우지 말고 기계만 내리십시오 — 볼륨(=조직 데이터)은 남습니다:

    fly scale count 0 --app store-scout    # 멈춤. 볼륨은 그대로 과금된다
    fly scale count 1 --app store-scout    # 다시 켬

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

### 2. 알고리즘 판은 이 저장소의 커밋이다

알고리즘(M1~M6)이 이 저장소 안에 있으므로, **빌드하는 커밋이 곧 알고리즘 판**이다.
밖에서 받아 오지 않는다 — 받아 오면 이미지와 커밋이 갈라져 그 보장이 사라진다.
`--build-arg STORE_SCOUT_REV=$(git rev-parse HEAD)` 로 넣으면 `/healthz` 가 그 값을
내보내므로, 어떤 판이 그 판정을 냈는지 나중에 짚을 수 있다.

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

## 공개 페이지 도메인 — `stores-scout.com` (GitHub Pages)

공개 페이지(`web/`)는 지금 `https://jasonsjo.github.io/store-scout/` 에 떠 있다.
여기에 `stores-scout.com` 을 붙이는 절차다. **순서가 있다.** 어기면 몇 분 동안
사이트가 두 주소 모두에서 깨진다 — 오류가 아니라 흰 화면이다.

### 한 도메인, 두 자리

| 주소 | 무엇 | 어디서 뜨나 | 누가 보나 |
|---|---|---|---|
| `stores-scout.com` · `www.` | 공개 페이지(소개 · 고객 상담) | GitHub Pages | 누구나 |
| `console.stores-scout.com` | 심의 콘솔(SaaS) | 사내 서버 + Cloudflare Tunnel | 사내 · Access 뒤 |

둘 다 Cloudflare 의 같은 zone 에 레코드로 들어간다. 이 절은 첫 줄(공개 페이지)이고,
둘째 줄은 아래 「사내 서버 + Cloudflare Tunnel」 절에서 Public Hostname 으로 붙인다.

### 0. 먼저 볼 것 — 이 도메인이 누구 것인가

```bash
dig +short stores-scout.com A        # 또는  nslookup stores-scout.com
whois stores-scout.com | grep -i "registrar\|name server"
```

2026-09-03 현재 `stores-scout.com` 은 **아무 데도 풀리지 않는다** — 레코드가 하나도
없다는 뜻이고, 그게 맞는 출발점이다. `dig` 가 GitHub 도 Cloudflare 도 아닌 IP 를
내면 누군가(등록기관 파킹 페이지 등)가 먼저 잡고 있는 것이니 그때는 멈추고 소유를
확인한다. 이름이 비슷한 `store-scout.com`(s 없음)은 **남의 것이다** — 89.31.143.90
을 가리키고 있다. 헷갈려서 그쪽에 레코드를 넣거나 CNAME 에 적으면 안 된다.
워크플로가 `stores-scout.com` 이 아닌 CNAME 을 거부하는 이유이기도 하다.

### 1. DNS 레코드 — Cloudflare(또는 등록기관) DNS 화면에서

| 종류 | 이름 | 값 | Proxy |
|---|---|---|---|
| A | `@` | `185.199.108.153` | **DNS only (회색)** |
| A | `@` | `185.199.109.153` | DNS only |
| A | `@` | `185.199.110.153` | DNS only |
| A | `@` | `185.199.111.153` | DNS only |
| AAAA | `@` | `2606:50c0:8000::153` | DNS only |
| AAAA | `@` | `2606:50c0:8001::153` | DNS only |
| AAAA | `@` | `2606:50c0:8002::153` | DNS only |
| AAAA | `@` | `2606:50c0:8003::153` | DNS only |
| CNAME | `www` | `jasonsjo.github.io` | DNS only |

> **Proxy 는 끄십시오(회색 구름).** 주황 구름(Proxied)으로 두면 GitHub 가 도메인
> 검증과 인증서 발급을 못 하고, Cloudflare SSL 모드가 Flexible 이면 리다이렉트가
> 무한히 돈다. TLS 는 GitHub 가 이미 해 주므로 Cloudflare 가 앞에 설 이유가 없다.
> `console.` 은 터널이라 사정이 다르다 — 그쪽은 터널이 알아서 Proxied 로 만든다.

넣고 나서 확인. **GitHub 의 IP 네 개가 나올 때까지** 다음으로 가지 않는다:

```bash
dig +short stores-scout.com A          # 185.199.108.153 … 111.153 넷
dig +short www.stores-scout.com CNAME  # jasonsjo.github.io.
```

반영에 몇 분, 등록기관 DNS 면 길게는 하루.

### 2. GitHub — Settings → Pages → Custom domain

`stores-scout.com` 을 넣고 **Save**. GitHub 가 DNS 를 검사한다(1분 안팎). 초록
체크가 뜨면 **Enforce HTTPS** 를 켠다 — 인증서 발급에 몇 분에서 한 시간.

이 순간부터 `jasonsjo.github.io/store-scout/` 는 `stores-scout.com` 으로 넘어간다.
그런데 지금 올라가 있는 빌드는 자산을 `/store-scout/assets/…` 에서 찾으므로,
**다음 단계를 바로 이어서** 해야 한다. 그 사이는 흰 화면이다.

### 3. 저장소 — 스위치 파일 하나

```bash
echo stores-scout.com > web/public/CNAME
git add web/public/CNAME
git commit -m "도메인을 붙인다 — stores-scout.com"
git push origin main
```

이 파일이 있으면 워크플로가 base 를 `/` 로 잡아 빌드한다(`deploy-pages.yml` 의
「Decide base」). 사람이 워크플로를 고칠 일이 없다. 파일 내용이 `stores-scout.com`
이 아니면 배포가 멈춘다 — 오타 난 도메인은 사이트를 두 주소 모두에서 내리기
때문이다. GitHub 는 Actions 배포에서 이 파일을 읽지 않는다. 우리 쪽 스위치다.

배포(1분 안팎)가 끝나면:

```bash
curl -sI https://stores-scout.com/                 | head -1   # 200
curl -sI https://stores-scout.com/consultation/    | head -1   # 200
curl -sI https://www.stores-scout.com/             | head -1   # 301 → stores-scout.com
curl -sI https://jasonsjo.github.io/store-scout/  | head -1   # 301 → stores-scout.com
```

브라우저에서 상담 화면을 열어 주소 검색과 CSV 내려받기가 되는지까지 본다.
자산 경로가 어긋났으면 화면이 하얗고 개발자도구 Network 에 404 가 줄지어 있다.

### 되돌리기

`web/public/CNAME` 을 지우고 push, GitHub Settings → Pages 의 Custom domain 을
비운다. 그러면 `jasonsjo.github.io/store-scout/` 로 돌아간다. 순서는 반대로 —
파일을 먼저 지워 base 를 `/store-scout/` 로 돌린 뒤 Settings 를 비운다.

## 사내 서버 + Cloudflare Tunnel  ← 권장

포트를 하나도 열지 않고 HTTPS 주소를 만든다. 터널이 **나가는 연결만** 쓰기 때문에
공유기·방화벽을 건드리지 않는다. 무료이고, 고객 개인정보는 이 서버에만 남는다 —
Cloudflare 는 TLS 를 끝내고 지나보낼 뿐 저장하지 않는다.

### 1. 터널 만들기 — `CLOUDFLARE_TUNNEL_TOKEN` 을 어디서 받는가

**먼저 도메인.** 터널은 *가진 도메인에 주소를 붙이는* 물건이라, 도메인이
Cloudflare 계정에 들어와 있어야 한다. `dash.cloudflare.com` 왼쪽 **Websites**
목록에 도메인이 보이면 준비된 것이다. 안 보이면 둘 중 하나를 먼저 한다.

- **새로 하나 산다 ← 권장.** 대시보드 → **Domain Registration → Register
  Domains** 에서 `stores-scout.com` 을 등록한다. Cloudflare 는 원가로 판다
  (`.com` 연 2만원 안팎, 갱신도 같은 값). 등록하는 순간 이 계정의 도메인이
  되므로 네임서버를 만질 일이 없고, **회사 기존 도메인을 건드리지 않는다.**
  어차피 랜딩용으로 필요한 주소라 이 단계가 같이 끝난다.
- **회사 도메인의 네임서버를 옮긴다.** 대시보드 → **Add a site** → 도메인 입력
  → **Free** → Cloudflare 가 주는 네임서버 두 개를 등록기관(가비아·후이즈·
  카페24 등)에서 바꿔 넣는다. 반영에 몇십 분, 길면 하루. **Active** 가 돼야
  다음으로 간다. `.co.kr` 도 된다 — Cloudflare 가 `.kr` 을 팔지는 않지만
  네임서버를 옮기는 것은 TLD 를 가리지 않는다.

  > ⚠ 네임서버를 옮기면 **그 도메인의 DNS 전부**가 Cloudflare 로 온다. 회사
  > 메일(MX)과 기존 홈페이지 레코드까지 함께다. Cloudflare 가 자동으로 긁어
  > 오지만 전부 가져오지는 못한다 — 빠진 것이 있으면 **회사 메일이 멎는다.**
  > 옮기기 전에 지금 등록기관의 DNS 화면을 통째로 캡처해 두고, Active 된 뒤
  > MX·SPF·기존 A 레코드가 그대로 있는지 대조하십시오. 이걸 확인할 사람이
  > 없다면 위의 「새로 하나 산다」 쪽이 안전하다.

**도메인 정하는 데 며칠 걸린다면** — 그 사이에 연결 경로만 먼저 확인할 수 있다.
도메인도 토큰도 없이 즉석 주소를 하나 받는다:

```bash
docker compose --profile quick up tunnel-quick     # -d 를 붙이지 마십시오
```

로그에 `https://….trycloudflare.com` 이 뜬다. 폰에서 그 주소로 들어가 로그인
화면이 보이면 앱–터널–브라우저 경로는 뚫린 것이다. 끝나면 **Ctrl+C**.

> ⚠ 확인용입니다. 이 주소는 Access 로 막을 수 없어 주소를 아는 사람은 누구나
> 로그인 화면에 닿고, 껐다 켜면 매번 바뀝니다. **고객 성명·연락처가 들어간 DB
> 로 띄우지 마십시오** — 부트스트랩 전 빈 상태에서만 쓰십시오. 영업팀에 줄
> 주소는 아래 절차(도메인 + 토큰 + Access)로 만든 것이어야 합니다.

**토큰 받기.** `dash.cloudflare.com` → 왼쪽 **Zero Trust** → **Networks →
Tunnels** → **Create a tunnel** → **Cloudflared** 선택 → 이름을 짓고(예:
`store-scout`) **Save**.

다음 화면 「Install and run a connector」 에 OS 별 설치 명령이 뜬다. 어느 탭이든
좋다 — **명령을 실행하지는 않는다.** 명령 안에 있는 긴 문자열 하나만 쓴다.

    cloudflared service install eyJhIjoiZjM4…（아주 긴 문자열）…In0=
                                └──────── 이 부분만이 토큰이다 ────────┘

- 토큰은 항상 **`eyJ` 로 시작**하고 보통 **180~220자**다.
- `cloudflared`, `service install`, `--token` 같은 앞부분은 **빼고** 복사한다.
  (여기서 제일 많이 틀린다. `scripts/tunnel_check.py` 가 잡아 준다.)
- 터널 목록의 **Configure** 로 들어가면 이 화면을 언제든 다시 볼 수 있다.
  잃어버렸으면 다시 보면 되고, 유출됐으면 같은 자리에서 **Refresh token**.
- 토큰은 **자격증명**이다. 이 값 하나면 누구나 사내 서버 이름으로 터널을 붙일
  수 있다. 채팅·이슈·커밋에 붙여넣지 않는다. `.env` 는 이미 gitignore 에 있다.

이어서 **Public Hostname** 을 하나 추가한다:

    Subdomain   scout            (원하는 이름)
    Domain      brand.co.kr      (가진 도메인)
    Service     HTTP  →  app:8000

`app:8000` 은 이 컴포즈 네트워크 안의 이름이다. `localhost` 가 아니다 —
터널도 컨테이너라 자기 자신을 가리키게 된다.

### 2. 서버에서

```bash
git clone https://github.com/JasonSJo/store-scout && cd store-scout
cp .env.example .env
# .env 를 열어 채운다:
#   STORE_SCOUT_HTTPS=1           ← 반드시. 안 켜면 로그인 쿠키에 Secure 가 안 붙는다
#   CLOUDFLARE_TUNNEL_TOKEN=...   ← 1번에서 복사한 값
#   STORE_SCOUT_REV=$(git rev-parse HEAD)

docker compose --profile tunnel up -d --build
docker compose exec app python3 -m server.bootstrap --org "조직명" --email you@brand.co.kr
```

`https://scout.brand.co.kr` 로 들어가면 로그인 화면이 뜬다.

### 3. 한 겹 더 — Cloudflare Access (권장)

터널을 켜는 순간 이 화면은 **인터넷에서 닿는다.** 앱 자체 로그인이 있지만, 고객
성명·연락처를 담은 사내 도구다. 로그인 화면 자체를 아무나 못 보게 막는 편이 낫다.

Zero Trust → **Access → Applications → Add an application** → Self-hosted
→ 위 호스트명을 넣고, 정책을 **Emails ending in `@brand.co.kr`** 로 둔다.
50명까지 무료다. 이러면 회사 메일이 없는 사람은 로그인 화면조차 보지 못한다.

### 4. 늘 켜 두기 — 실제로 물리는 자리

컨테이너는 `restart: unless-stopped` 라 도커만 살아 있으면 알아서 다시 뜬다.
문제는 **도커 밖**이다. 아래 셋을 안 해 두면 어느 날 조용히 끊긴다.

**① 재부팅 후 도커가 스스로 뜨는가**

    리눅스   sudo systemctl enable docker
    윈도우   Docker Desktop → Settings → General →
             "Start Docker Desktop when you sign in" 체크
             ⚠ 이건 **로그인해야** 뜬다. 재부팅 후 아무도 로그인하지 않으면
               서버가 죽어 있다. 자동 로그인을 켜거나 WSL2 + systemd 로 두십시오.
    macOS    Docker Desktop → Settings → General → "Start Docker Desktop..."

**② 절전으로 잠들지 않는가**

화면만 꺼지는 것은 괜찮다. **시스템이 잠들면** 터널이 끊긴다.

    윈도우   설정 → 시스템 → 전원 → "다음 시간이 경과하면 PC를 절전 모드로" = 안 함
             (노트북이면 "전원 연결 시" 쪽도 함께)
    macOS    시스템 설정 → 배터리 → 옵션 → "디스플레이가 꺼져 있을 때 자동 잠자기 방지"
    리눅스   sudo systemctl mask sleep.target suspend.target hibernate.target

**③ 진짜 되는지 한 번 확인한다**

말로만 켜 두면 안 된다. 재부팅해 보고 아무 조작 없이 도는지 본다:

```bash
sudo reboot
# 다시 켜진 뒤, 아무것도 손대지 않고
docker compose ps                       # app·tunnel 이 Up 인가
curl -s http://127.0.0.1:8000/healthz    # pipeline=yes 인가
```

바깥 주소(`https://scout.brand.co.kr`)로도 한 번 들어가 보십시오. 여기까지 확인해야
「늘 켜 둔다」가 사실이 된다.

### 고쳐서 올릴 때

```bash
cd store-scout && git pull
STORE_SCOUT_REV=$(git rev-parse HEAD) docker compose --profile tunnel up -d --build
```

볼륨은 그대로라 데이터가 남는다. **도는 중인 심의는 죽는다** — 재시작 때 '실패'로
정리되지만 사용자는 다시 올려야 하므로, 아무도 안 쓸 때 하십시오.

### 터널이 안 될 때

```bash
python3 scripts/tunnel_check.py
```

막힌 곳을 순서대로 짚어 준다. 읽기만 하고 아무것도 고치지 않는다.

이 구성에서 특히 헷갈리는 자리가 하나 있다. **앱이 healthy 가 아니면 터널은 시작
자체를 하지 않는다**(`depends_on: service_healthy`). 그래서 터널 로그를 아무리 봐도
비어 있다 — 컨테이너가 없으니까. 그때는 터널이 아니라 앱을 봐야 한다.

자주 나오는 것:

| 증상 | 원인 |
|---|---|
| `tunnel` 컨테이너가 아예 없다 | `--profile tunnel` 을 빠뜨렸거나, 앱이 healthy 가 아니다 |
| 터널은 붙었는데 502·1033 | Public Hostname 의 Service 가 `localhost:8000` 이다 — `app:8000` 이어야 한다 |
| `Provided Tunnel token is not valid` | 토큰이 잘렸거나 대시보드에서 터널을 지웠다 |
| `.env` 를 채웠는데 안 읽힌다 | 파일 이름이 `.env.txt` 다 (윈도우가 확장자를 숨긴다) |

### 알아 둘 것

- 로그: `docker compose logs -f app` · 터널은 `docker compose logs -f tunnel`
- 백업은 `backup` 서비스가 올릴 때 한 벌, 그 뒤 24시간마다 한 벌 떠서 최근 14개를
  `./backup` 에 남긴다. **그 안에 기존점 실매출과 상담 개인정보가 들어 있다** —
  서버와 같은 수준으로 통제하거나 암호화해 다른 곳으로 옮기십시오.
  이 PC 가 고장 나면 그 백업도 함께 사라진다. 다른 기계나 외장 디스크로 한 벌 더
  옮겨 두십시오.
- 터널을 끄려면 `docker compose --profile tunnel stop tunnel`. 앱은 계속 돌고
  사내망에서만 닿는다.

## 사내망에서만 (터널 없이)

```bash
STORE_SCOUT_REV=$(git rev-parse HEAD) docker compose up -d --build
docker compose exec app python3 -m server.bootstrap --org "조직명" --email you@brand.co.kr
```

`127.0.0.1:8000` 에만 연다. 다른 기계에서 보려면 `ports` 를 `"0.0.0.0:8000:8000"` 으로
바꾸기 전에 — 그건 **평문 HTTP** 다. 사내망이라도 로그인 쿠키와 고객 연락처가 그대로
흐른다. Caddy·nginx 로 HTTPS 를 끝내고 `STORE_SCOUT_HTTPS=1` 을 켜십시오.

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
