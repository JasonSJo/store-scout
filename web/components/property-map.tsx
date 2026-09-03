'use client';
import { useEffect, useRef, useState } from 'react';
import { loadKakaoMap, type KakaoMap, type KakaoMaps, type LatLng } from '@/lib/kakao-map';
export type MapPoint = { id: string; latitude: number; longitude: number; label: string };
export function PropertyMap({ points, selected, onSelect, onPick }: {
  points: MapPoint[]; selected?: string | null;
  onSelect?: (id: string) => void;
  onPick?: (latitude: number, longitude: number) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const instance = useRef<KakaoMap | null>(null);
  const library = useRef<KakaoMaps | null>(null);
  const callbacks = useRef({ onSelect, onPick });
  callbacks.current = { onSelect, onPick };
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    let dispose: (() => void) | undefined;
    const element = host.current;
    loadKakaoMap().then(K => {
      if (!live || !element) return;
      library.current = K;
      const map = new K.Map(element, { center: new K.LatLng(36.3, 127.8), level: 13, scrollwheel: false });
      instance.current = map;
      const click = (e: { latLng: LatLng }) => {
        const lat = e.latLng.getLat(), lng = e.latLng.getLng();
        if (lat >= 33 && lat <= 39 && lng >= 124 && lng <= 132) callbacks.current.onPick?.(lat, lng);
      };
      K.event.addListener(map, 'click', click);
      const observer = new ResizeObserver(() => map.relayout());
      observer.observe(element);
      dispose = () => { observer.disconnect(); K.event.removeListener(map, 'click', click); element.replaceChildren(); };
      setReady(true);
    }).catch(e => { if (live) setError(e instanceof Error ? e.message : '카카오맵을 불러오지 못했습니다.'); });
    return () => { live = false; dispose?.(); instance.current = null; };
  }, []);
  useEffect(() => {
    const map = instance.current, K = library.current;
    if (!ready || !map || !K) return;
    const valid = points.filter(p => Number.isFinite(p.latitude) && Number.isFinite(p.longitude) && p.latitude >= 33 && p.latitude <= 39 && p.longitude >= 124 && p.longitude <= 132);
    const bounds = new K.LatLngBounds();
    const overlays = valid.map(p => {
      const position = new K.LatLng(p.latitude, p.longitude);
      bounds.extend(position);
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = p.label; button.title = p.label;
      button.setAttribute('aria-label', p.label);
      button.style.cssText = 'background:#FF6D2D;color:white;border:2px solid #BB3E18;border-radius:16px;padding:6px 10px;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;font-size:13px;';
      button.onclick = e => { e.stopPropagation(); callbacks.current.onSelect?.(p.id); };
      return new K.CustomOverlay({ map, position, content: button, yAnchor: 1, clickable: true });
    });
    if (valid.length === 1) { map.setCenter(new K.LatLng(valid[0].latitude, valid[0].longitude)); map.setLevel(3); }
    else if (valid.length > 1) map.setBounds(bounds, 40, 40, 40, 40);
    else { map.setCenter(new K.LatLng(36.3, 127.8)); map.setLevel(13); }
    return () => overlays.forEach(o => o.setMap(null));
  }, [points, ready]);
  useEffect(() => {
    const p = points.find(p => p.id === selected && Number.isFinite(p.latitude) && Number.isFinite(p.longitude) && p.latitude >= 33 && p.latitude <= 39 && p.longitude >= 124 && p.longitude <= 132);
    if (p && instance.current && library.current) {
      instance.current.setCenter(new library.current.LatLng(p.latitude, p.longitude));
      instance.current.setLevel(3);
    }
  }, [selected, points, ready]);
  return <div className="property-map-wrap">
    <div ref={host} className="property-map" role="region" aria-label={onPick ? '카카오맵에서 매물 위치 지정' : '현재 페이지 매물 카카오맵'} />
    {!ready && !error && <p role="status">카카오맵을 불러오는 중입니다.</p>}
    {error && <p role="status" className="form-error">{error} 매물 목록과 주소는 계속 확인할 수 있습니다.</p>}
    <p className="map-caption">{onPick ? '지도를 확대해 위치를 누르거나 위도·경도를 직접 입력하세요.' : points.length ? '표시는 제공된 좌표 기준입니다. 주소와 실제 위치를 함께 확인하세요.' : '표시할 매물 좌표가 아직 연결되지 않았습니다.'} 지도: 카카오맵 · 지도 화면을 카카오에서 불러옵니다. 지도 제공은 매물 데이터 제공과 별개입니다.</p>
  </div>;
}
