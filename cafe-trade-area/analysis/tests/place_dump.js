/* 위치 모듈 동작 확인 — 좌표 파서·이름 제안·외부 링크를 stdout 으로 낸다.
   tests/test_place.py 가 대조한다. 네트워크는 쓰지 않는다(순수 함수만 검사). */
const path = require('path');
const PLACE = require(path.resolve(__dirname, '..', '..', 'input', 'js', 'place.js'));

const coords = [
  '37.5445, 127.0557', '127.0557, 37.5445', '위도 37.5445 경도 127.0557',
  '37.5445\t127.0557', '서울시', '1, 2', '', '37.5445',
].map(t => ({ 입력: t, 결과: PLACE.parseCoords(t) }));

const names = [
  { 이름: '스타벅스 성수점', 주소: '서울 성동구 연무장길 42' },
  { 이름: '', 주소: '서울 성동구 연무장길 42' },
  { 이름: '', 주소: '서울 성동구' },
].map(h => ({ 입력: h, 결과: PLACE.suggestName(h) }));

const lawd = ['1114010300', '11140', '', 'abc', '111'].map(b => ({ 입력: b, 결과: PLACE.lawdCode(b) }));

/* ── 검색 — 가짜 SDK 로 상태별 동작을 고정한다 ──────────────────
   실제 카카오에 붙지 않는다. 여기서 보려는 것은 통신이 아니라 **실패를 어떻게
   구분하는가**다. 키가 도메인에 등록되지 않으면 SDK 는 스크립트를 잘 내려 주고
   검색 콜백만 ERROR 로 돌아온다 — 그것을 '결과 없음' 으로 보여 주면 사람은 주소가
   틀린 줄 알고 주소만 계속 고쳐 본다. */
const S = { OK: 'OK', ZERO_RESULT: 'ZERO_RESULT', ERROR: 'ERROR' };
const 주소결과 = [{
  address_name: '서울 성동구 성수동2가 333-1',
  road_address: { address_name: '서울 성동구 연무장길 42', building_name: '성수빌딩', zone_no: '04782' },
  address: { address_name: '서울 성동구 성수동2가 333-1', b_code: '1120011400' },
  x: '127.0557', y: '37.5445',
}];
const 장소결과 = [{
  place_name: '카페하다 성수점', road_address_name: '서울 성동구 연무장길 42',
  address_name: '서울 성동구 성수동2가 333-1', x: '127.0558', y: '37.5446',
}];

function 가짜SDK(addrStatus, placeStatus) {
  global.window = {
    kakao: { maps: {
      load: cb => cb(),
      services: {
        Status: S,
        Geocoder: function () {
          this.addressSearch = (q, cb) =>
            setTimeout(() => cb(addrStatus === S.OK ? 주소결과 : [], addrStatus), 0);
        },
        Places: function () {
          this.keywordSearch = (q, cb) =>
            setTimeout(() => cb(placeStatus === S.OK ? 장소결과 : [], placeStatus), 0);
        },
      },
    } },
  };
  // 키가 있는 것처럼 — localStorage 가 없는 node 에서는 getKey 가 '' 를 돌려주므로
  // 저장소를 흉내 낸다
  global.localStorage = {
    _v: { 'cafe-trade-area/kakao-js-key': 'FAKE-JS-KEY' },
    getItem(k) { return this._v[k] || null; },
    setItem(k, v) { this._v[k] = v; },
    removeItem(k) { delete this._v[k]; },
  };
}

async function 검색사례(이름, addrStatus, placeStatus) {
  가짜SDK(addrStatus, placeStatus);
  try {
    const hits = await PLACE.search('연무장길 42');
    return { 사례: 이름, 결과: 'ok', 건수: hits.length,
             출처: hits.map(h => h.출처), 첫결과: hits[0] || null };
  } catch (e) {
    return { 사례: 이름, 결과: '실패', 메시지: e.message };
  }
}

/* ── 역지오코딩 — 마커를 옮겼을 때 '어디로 옮겼는지' ────────────
   카카오는 x(경도)를 먼저 받는다. 순서를 바꿔 넣으면 조용히 엉뚱한 곳이 나온다. */
function 가짜역(주소상태, 코드상태) {
  const 받은 = {};
  가짜SDK(S.OK, S.OK);
  const G = global.window.kakao.maps.services;
  G.Geocoder = function () {
    this.addressSearch = (q, cb) => setTimeout(() => cb([], S.ZERO_RESULT), 0);
    this.coord2Address = (x, y, cb) => {
      받은.주소호출 = { x, y };
      setTimeout(() => cb(주소상태 === S.OK ? [{
        road_address: { address_name: '서울 광진구 아차산로 100', zone_no: '04998' },
        address: { address_name: '서울 광진구 구의동 1-1' },
      }] : [], 주소상태), 0);
    };
    this.coord2RegionCode = (x, y, cb) => {
      받은.코드호출 = { x, y };
      setTimeout(() => cb(코드상태 === S.OK ? [
        { region_type: 'H', code: '1121500000' },   // 행정동 — 이걸 쓰면 안 된다
        { region_type: 'B', code: '1121510300' },   // 법정동 — 실거래가 지역코드의 출처
      ] : [], 코드상태), 0);
    };
  };
  return 받은;
}

async function 역사례(이름, 주소상태, 코드상태) {
  const 받은 = 가짜역(주소상태, 코드상태);
  const got = await PLACE.whereIs(37.5445, 127.0557);
  return { 사례: 이름, 결과: got, 호출: 받은 };
}

/* ── 지도 ────────────────────────────────────── */
async function 지도사례() {
  가짜SDK(S.OK, S.OK);
  const K = global.window.kakao.maps;
  const 기록 = { 마커끌기: null, 정리됨: false };
  let dragend = null;
  K.LatLng = function (a, b) { this.getLat = () => a; this.getLng = () => b; };
  K.Map = function (el, o) { this.level = o.level; this.setCenter = () => {}; };
  K.Marker = function (o) {
    this.draggable = o.draggable;
    this._p = o.position;
    this.getPosition = () => this._p;
    this.setPosition = p => { this._p = p; };
    this.setMap = () => { 기록.정리됨 = true; };
    기록.마커 = this;
  };
  K.event = { addListener: (obj, ev, fn) => { if (ev === 'dragend') dragend = fn; } };

  const box = { innerHTML: '' };
  const h = await PLACE.showMap(box, { 위도: 37.5445, 경도: 127.0557 },
                                m => { 기록.마커끌기 = m; });
  기록.끌수있음 = 기록.마커.draggable === true;
  // 마커를 옮기고 dragend 를 흉내 낸다
  기록.마커.setPosition(new K.LatLng(37.54, 127.09));
  dragend();
  h.destroy();
  return 기록;
}

(async () => {
  const 검색 = [
    await 검색사례('둘 다 성공', S.OK, S.OK),
    await 검색사례('주소만 없음', S.ZERO_RESULT, S.OK),
    await 검색사례('둘 다 없음', S.ZERO_RESULT, S.ZERO_RESULT),
    await 검색사례('키/도메인 오류', S.ERROR, S.ERROR),
    await 검색사례('장소만 오류 — 주소는 살린다', S.OK, S.ERROR),
  ];

  const 역 = [
    await 역사례('둘 다 성공', S.OK, S.OK),
    await 역사례('주소만 실패', S.ERROR, S.OK),
    await 역사례('코드만 실패', S.OK, S.ERROR),
  ];
  const 지도 = await 지도사례();

  process.stdout.write(JSON.stringify({
    coords, names, lawd, 검색, 역, 지도: {
      끌수있음: 지도.끌수있음, 마커끌기: 지도.마커끌기, 정리됨: 지도.정리됨,
    },
    서비스: PLACE.SERVICES.map(s => s.이름),
    링크: PLACE.links({ 주소: '서울 성동구 연무장길 42' }),
    링크_주소없음: PLACE.links({ 주소: '' }),
  }, null, 1));
})();


