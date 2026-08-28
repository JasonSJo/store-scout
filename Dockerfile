# 출점심의 (store-scout)
#
# 이 이미지는 두 저장소를 담는다. 알고리즘(M1~M6)은 jasons-company 에 있고
# 이 서비스는 그것을 서브프로세스로 부른다. 런타임에 받아 오지 않고 **빌드 때
# 고정된 리비전으로 박는다** — 이유는 셋이다.
#
#   1. 판정은 알고리즘 판에 따라 달라진다. main 을 따라가면 어제 통과한 후보지가
#      오늘 부결이 되고, 왜 바뀌었는지 아무도 모른다.
#   2. 지난 심의를 재현할 수 있어야 한다. 이미지가 곧 알고리즘 판이다.
#   3. 실행 중에 네트워크를 타지 않는다. 조직 데이터를 다루는 프로세스다.
#
# 알고리즘을 올리려면 PIPELINE_REV 를 바꿔 다시 빌드한다. 그 자체가 배포 기록이다.

FROM python:3.11-slim AS pipeline

# 알고리즘 리비전. 반드시 커밋 SHA 로 고정한다 — 브랜치명을 넣으면 빌드마다
# 다른 알고리즘이 들어가고 이 파일의 목적이 사라진다.
ARG PIPELINE_REPO=https://github.com/JasonSJo/jasons-company.git
ARG PIPELINE_REV=6b4ab2431d671d1ebe467607ee109d57ab922b76

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN git init /src \
    && cd /src \
    && git remote add origin "$PIPELINE_REPO" \
    && git fetch --depth 1 origin "$PIPELINE_REV" \
    && git checkout FETCH_HEAD \
    # 심의 콘솔(app/)은 사내 한정 자료이고 서버가 쓰지도 않는다. 이미지에 넣지 않는다.
    && rm -rf /src/cafe-trade-area/app /src/content-agency /src/.git \
    && test -f /src/cafe-trade-area/analysis/review_sites.py


FROM python:3.11-slim

ARG PIPELINE_REV=6b4ab2431d671d1ebe467607ee109d57ab922b76
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STORE_SCOUT_PIPELINE=/opt/pipeline/cafe-trade-area/analysis \
    STORE_SCOUT_PIPELINE_REV=${PIPELINE_REV} \
    STORE_SCOUT_DB=/data/store-scout.sqlite3 \
    STORE_SCOUT_HTTPS=1

WORKDIR /app

COPY requirements.txt ./
COPY --from=pipeline /src/cafe-trade-area/analysis/requirements.txt /tmp/pipeline-requirements.txt
# 파이프라인은 서브프로세스로 돌지만 같은 파이썬을 쓴다 — 그쪽 의존성도 함께 넣는다
RUN pip install --no-cache-dir -r requirements.txt -r /tmp/pipeline-requirements.txt \
    && rm /tmp/pipeline-requirements.txt

COPY --from=pipeline /src/cafe-trade-area /opt/pipeline/cafe-trade-area
COPY server ./server
COPY scripts ./scripts

# 조직 데이터를 다루는 프로세스다. root 로 돌릴 이유가 없다.
RUN useradd --create-home --uid 10001 scout \
    && mkdir -p /data && chown -R scout:scout /data /app
USER scout

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request,sys; \
sys.exit(0 if b'pipeline=yes' in urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).read() else 1)"

# 워커는 하나다. 파이프라인 실행이 프로세스 안의 백그라운드 작업이고 상태가
# SQLite 에 있어, 워커를 늘리면 실행 상태와 DB 가 갈라진다(DEPLOY.md 참고).
CMD ["python3", "-m", "uvicorn", "server.app:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
