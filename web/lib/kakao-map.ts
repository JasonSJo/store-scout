export type LatLng = { getLat(): number; getLng(): number };
export type KakaoMap = {
  setCenter(p: LatLng): void; setLevel(n: number): void;
  setBounds(b: unknown, top?: number, right?: number, bottom?: number, left?: number): void;
  relayout(): void;
};
export type KakaoMaps = {
  load(cb: () => void): void;
  LatLng: new (lat: number, lng: number) => LatLng;
  LatLngBounds: new () => { extend(p: LatLng): void };
  Map: new (host: HTMLElement, options: { center: LatLng; level: number; scrollwheel: boolean }) => KakaoMap;
  CustomOverlay: new (options: { map: KakaoMap; position: LatLng; content: HTMLElement; yAnchor: number; clickable: boolean }) => { setMap(map: KakaoMap | null): void };
  event: { addListener(target: KakaoMap, type: string, cb: (e: { latLng: LatLng }) => void): void;
    removeListener(target: KakaoMap, type: string, cb: (e: { latLng: LatLng }) => void): void };
};
// The address-search widget also declares window.kakao; do not overwrite its type.
const currentMaps = () => (window as unknown as { kakao?: { maps?: KakaoMaps } }).kakao?.maps;
let pending: Promise<KakaoMaps> | undefined;
export function loadKakaoMap(): Promise<KakaoMaps> {
  const key = import.meta.env.VITE_KAKAO_MAP_JS_KEY;
  if (!key) return Promise.reject(new Error('카카오맵 JavaScript 키가 필요합니다. VITE_KAKAO_MAP_JS_KEY와 사이트 도메인을 설정해 주세요.'));
  if (pending) return pending;
  pending = new Promise<KakaoMaps>((resolve, reject) => {
    const script = document.createElement('script');
    let finished = false;
    const fail = () => {
      if (finished) return;
      finished = true; clearTimeout(timer); script.remove();
      reject(new Error('카카오맵을 불러오지 못했습니다. JavaScript 키, 등록 도메인, 지도 사용 설정과 네트워크를 확인하세요.'));
    };
    const timer = setTimeout(fail, 15000);
    script.src = 'https://dapi.kakao.com/v2/maps/sdk.js?autoload=false&appkey=' + encodeURIComponent(key);
    script.async = true;
    script.onerror = fail;
    script.onload = () => {
      if (finished) return;
      const maps = currentMaps();
      if (!maps) return fail();
      maps.load(() => {
        if (finished) return;
        finished = true; clearTimeout(timer); resolve(maps);
      });
    };
    document.head.appendChild(script);
  }).catch(error => { pending = undefined; throw error; });
  return pending;
}
