# 스스닷컴 (store-scout.com)
#
# 알고리즘(M1~M6)과 서비스가 한 저장소에 있다. 전에는 알고리즘이 jasons-company 에
# 있어 빌드 때 고정 리비전으로 받아 왔는데, 그 저장소에서 이관하면서 그럴 이유가
# 없어졌다 — 이제 이 저장소의 커밋 하나가 곧 알고리즘 판이다.
#
#   · 판정은 알고리즘 판에 따라 달라진다. 어제 통과한 후보지가 오늘 부결이 되면
#     왜 바뀌었는지 커밋으로 짚을 수 있어야 한다.
#   · 지난 심의를 재현할 수 있어야 한다. 이미지가 곧 알고리즘 판이다.
#   · 실행 중에 네트워크를 타지 않는다. 조직 데이터를 다루는 프로세스다.

FROM python:3.11-slim

# 빌드하는 커밋 SHA. /healthz 가 이 값을 내보내므로, 어떤 알고리즘 판이 그 판정을
# 냈는지 나중에 짚을 수 있다. CI 가 --build-arg STORE_SCOUT_REV=$GITHUB_SHA 로 넣는다.
ARG STORE_SCOUT_REV=unknown

ENV STORE_SCOUT_REV=${STORE_SCOUT_REV} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STORE_SCOUT_PIPELINE=/opt/pipeline/cafe-trade-area/analysis \
    STORE_SCOUT_DB=/data/store-scout.sqlite3 \
    STORE_SCOUT_HTTPS=1

WORKDIR /app

COPY requirements.txt ./
COPY cafe-trade-area/analysis/requirements.txt /tmp/pipeline-requirements.txt
# 파이프라인은 서브프로세스로 돌지만 같은 파이썬을 쓴다 — 그쪽 의존성도 함께 넣는다
RUN pip install --no-cache-dir -r requirements.txt -r /tmp/pipeline-requirements.txt \
    && rm /tmp/pipeline-requirements.txt

# 심의 콘솔(app/)은 사내 한정 자료이고 서버가 쓰지도 않는다. 이미지에 넣지 않는다.
COPY cafe-trade-area/analysis /opt/pipeline/cafe-trade-area/analysis
COPY server ./server
COPY scripts ./scripts
RUN test -f /opt/pipeline/cafe-trade-area/analysis/review_sites.py

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
