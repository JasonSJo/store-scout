'use client';

import Link from '@/lib/link';
import { useState, useEffect, useRef, type FormEvent } from 'react';
import { flushSync } from 'react-dom';
import {
  ArrowLeft,
  ArrowRight,
  UserRound,
  MapPin,
  Wallet,
  Store,
  Search,
  Check,
  ShieldCheck,
  ClipboardCheck,
  Download,
  Info,
  Building2,
  BriefcaseBusiness,
  GraduationCap,
  Hospital,
  Landmark,
  Layers3,
  ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { REGIONS } from '@/lib/regions';

type Address = { zip: string; main: string; detail: string };
type Area = { city: string; district: string };
type Consultation = {
  name: string;
  phone: string;
  home: Address;
  work: Address;
  areas: Area[];
  size: string;
  market: string;
  deposit: string;
  premium: string;
  saleBudget: string;
  monthlyRentMax: string;
  funding: string;
  operation: string;
};
type PostcodeData = {
  zonecode: string;
  roadAddress: string;
  jibunAddress: string;
};
// 카카오 지도 SDK 에서 쓰는 만큼만 적는다. 전체 타입을 들이면 쓰지 않는 API 가
// 수백 개 따라오고, 그중 무엇이 실제로 쓰이는지가 보이지 않게 된다.
type KakaoLatLng = { getLat(): number; getLng(): number };
type KakaoMaps = {
  load(cb: () => void): void;
  LatLng: new (lat: number, lng: number) => KakaoLatLng;
  LatLngBounds: new () => { extend(p: KakaoLatLng): void };
  Map: new (
    el: HTMLElement,
    opts: { center: KakaoLatLng; level: number },
  ) => { setBounds(b: unknown): void; setLevel(l: number): void; setCenter(p: KakaoLatLng): void };
  Marker: new (opts: { map: unknown; position: KakaoLatLng }) => unknown;
  CustomOverlay: new (opts: {
    map: unknown;
    position: KakaoLatLng;
    content: HTMLElement;
    yAnchor?: number;
  }) => unknown;
  services: {
    Status: { OK: string; ZERO_RESULT: string; ERROR: string };
    Geocoder: new () => {
      addressSearch(
        query: string,
        cb: (result: Array<{ x: string; y: string }>, status: string) => void,
      ): void;
    };
  };
};
declare global {
  interface Window {
    kakao?: {
      Postcode: new (options: {
        oncomplete: (data: PostcodeData) => void;
        width: string;
        height: string;
      }) => { embed: (element: HTMLElement) => void };
      maps?: KakaoMaps;
    };
  }
}

// 카카오 지도 JS 키. 도메인을 등록해야만 동작하는 키라 공개 페이지에 들어가도
// 안전하다 — 다른 도메인에서는 쓸 수 없다. 값은 빌드 때 넣는다:
//   GitHub → Settings → Secrets and variables → Actions → Variables → KAKAO_JS_KEY
//   로컬:  VITE_KAKAO_JS_KEY=... npm run dev
// 옛 화면은 키를 브라우저 저장소에 넣게 했는데, 이 화면은 브라우저 저장소가
// 금지다(개인정보를 브라우저에 남기지 않는다는 약속). 그래서 빌드 변수다.
const KAKAO_JS_KEY = String(import.meta.env.VITE_KAKAO_JS_KEY ?? '').trim();

type MapState = {
  status: 'idle' | 'nokey' | 'loading' | 'ready' | 'error';
  message?: string;
  plotted: string[]; // 지도에 찍힌 희망 지역
  missed: string[]; // 좌표를 못 찾은 희망 지역
};
const initial: Consultation = {
  name: '',
  phone: '',
  home: { zip: '', main: '', detail: '' },
  work: { zip: '', main: '', detail: '' },
  areas: [
    { city: '', district: '' },
    { city: '', district: '' },
    { city: '', district: '' },
  ],
  size: '',
  market: '',
  deposit: '',
  premium: '',
  saleBudget: '',
  monthlyRentMax: '',
  funding: '',
  operation: '',
};
const markets = [
  { name: '오피스', icon: BriefcaseBusiness },
  { name: '주거', icon: Building2 },
  { name: '학교', icon: GraduationCap },
  { name: '병원', icon: Hospital },
  { name: '메인', icon: Landmark },
  { name: '복합', icon: Layers3 },
];
const money = (value: string) =>
  value === '' ? '미입력' : Number(value).toLocaleString('ko-KR') + '만 원';

export default function ConsultationPage() {
  const [form, setForm] = useState<Consultation>(initial);
  const [addressTarget, setAddressTarget] = useState<'home' | 'work' | null>(
    null,
  );
  const [addressError, setAddressError] = useState('');
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState('');
  const postcodeRef = useRef<HTMLDivElement>(null);
  const formRef = useRef(form);
  formRef.current = form;
  const update = (key: keyof Consultation, value: unknown) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setError('');
  };
  const setAddress = (
    target: 'home' | 'work',
    part: keyof Address,
    value: string,
  ) =>
    setForm((prev) => ({
      ...prev,
      [target]: { ...prev[target], [part]: value },
    }));
  const filled = [
    Boolean(
      form.name.trim() && form.phone.trim() && form.home.main && form.work.main,
    ),
    Boolean(form.areas[0].district && form.size && form.market),
    Boolean(form.deposit !== '' && form.premium !== '' && form.funding),
    Boolean(form.operation),
  ];
  const progress = filled.filter(Boolean).length;
  const total = Number(form.deposit || 0) + Number(form.premium || 0);

  // ── 지도 시작 ──────────────────────────────────────────────────────
  // 결과 화면의 지도. 카카오 지도 위에 **희망 지역(시·군·구)만** 찍는다.
  //
  // 고객명·전화번호·거주지·근무지는 지도에 보내지 않는다. 지도는 카카오
  // 서버가 그리는 것이라, 거기 보내는 것은 곧 바깥으로 나가는 것이다.
  // 희망 지역은 '서울특별시 강남구' 같은 행정구역 이름이라 개인정보가 아니다.
  // 이 경계는 tests/test_saas.py 가 지킨다 — 이 블록 안에 form.home 이나
  // form.phone 이 들어오면 테스트가 깨진다.
  //
  // 실패를 종류별로 가른다. 키가 없는 것, SDK 를 못 불러온 것(도메인 미등록·망),
  // 좌표를 못 찾은 것은 고칠 사람이 다르다. 회색 빈 상자 하나로 뭉개면
  // 무엇을 고쳐야 하는지 아무도 모른다.
  const mapRef = useRef<HTMLDivElement>(null);
  const [mapState, setMapState] = useState<MapState>({
    status: 'idle',
    plotted: [],
    missed: [],
  });
  useEffect(() => {
    if (!complete) return;
    const 지역 = 희망지역();
    if (!KAKAO_JS_KEY) {
      setMapState({ status: 'nokey', plotted: [], missed: 지역 });
      return;
    }
    let alive = true;
    setMapState({ status: 'loading', plotted: [], missed: [] });
    const fail = (message: string) => {
      if (alive) setMapState({ status: 'error', message, plotted: [], missed: 지역 });
    };

    const ensureSdk = (): Promise<void> => {
      if (window.kakao?.maps) return Promise.resolve();
      return new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src =
          'https://dapi.kakao.com/v2/maps/sdk.js?appkey=' +
          encodeURIComponent(KAKAO_JS_KEY) +
          '&libraries=services&autoload=false';
        s.async = true;
        s.onload = () => resolve();
        s.onerror = () => reject(new Error('sdk'));
        document.head.appendChild(s);
      });
    };

    const draw = () => {
      const maps = window.kakao?.maps;
      const el = mapRef.current;
      if (!maps || !el || !alive) return;
      const map = new maps.Map(el, {
        center: new maps.LatLng(37.5665, 126.978), // 서울시청. 좌표가 오면 바로 옮긴다
        level: 8,
      });
      if (!지역.length) {
        setMapState({ status: 'ready', plotted: [], missed: [] });
        return;
      }
      const geocoder = new maps.services.Geocoder();
      const bounds = new maps.LatLngBounds();
      const plotted: string[] = [];
      const missed: string[] = [];
      let sawError = false;
      let pending = 지역.length;
      지역.forEach((name, i) => {
        geocoder.addressSearch(name, (result, status) => {
          if (!alive) return;
          if (status === maps.services.Status.OK && result[0]) {
            const pos = new maps.LatLng(Number(result[0].y), Number(result[0].x));
            new maps.Marker({ map, position: pos });
            // 라벨은 HTML 문자열이 아니라 DOM 으로 만든다. name 은 우리 목록
            // (lib/regions.ts) 에서 온 값이지만, 문자열 조립 습관을 두지 않는다.
            const label = document.createElement('div');
            label.className = 'map-rank';
            label.textContent = `${i + 1}순위 · ${name}`;
            new maps.CustomOverlay({ map, position: pos, content: label, yAnchor: 2.3 });
            bounds.extend(pos);
            plotted.push(name);
          } else {
            if (status === maps.services.Status.ERROR) sawError = true;
            missed.push(name);
          }
          pending -= 1;
          if (pending > 0) return;
          if (plotted.length) {
            map.setBounds(bounds);
            if (plotted.length === 1) map.setLevel(7);
            setMapState({ status: 'ready', plotted, missed });
          } else {
            fail(
              sawError
                ? '지도는 떴지만 좌표 검색이 거부됐습니다 — 카카오 개발자 사이트에서 이 도메인이 플랫폼(Web)에 등록돼 있는지 확인하십시오.'
                : '희망 지역의 좌표를 찾지 못했습니다.',
            );
          }
        });
      });
    };

    const timer = window.setTimeout(
      () => fail('지도를 불러오는 데 시간이 너무 걸립니다. 잠시 후 다시 열어 보십시오.'),
      12000,
    );
    ensureSdk()
      .then(
        () =>
          new Promise<void>((resolve) => {
            window.kakao!.maps!.load(() => resolve());
          }),
      )
      .then(draw)
      .catch(() =>
        fail(
          '카카오 지도 SDK 를 불러오지 못했습니다 — JS 키가 맞는지, stores-scout.com 이 카카오 개발자 사이트의 플랫폼(Web)에 등록돼 있는지 확인하십시오.',
        ),
      )
      .finally(() => window.clearTimeout(timer));
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [complete]); // eslint-disable-line react-hooks/exhaustive-deps
  // ── 지도 끝 ────────────────────────────────────────────────────────

  useEffect(() => {
    const script = document.createElement('script');
    script.src =
      'https://t1.kakaocdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js';
    script.async = true;
    script.onerror = () =>
      setAddressError(
        '주소 검색 서비스를 불러오지 못했습니다. 주소를 직접 입력하거나 잠시 후 다시 시도해 주세요.',
      );
    document.head.appendChild(script);
    return () => {
      script.remove();
    };
  }, []);
  useEffect(() => {
    if (!addressTarget) return;
    let active = true;
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts++;
      if (window.kakao?.Postcode && postcodeRef.current) {
        window.clearInterval(timer);
        setAddressError('');
        new window.kakao.Postcode({
          width: '100%',
          height: '100%',
          oncomplete(data) {
            if (!active) return;
            setForm((prev) => ({
              ...prev,
              [addressTarget]: {
                ...prev[addressTarget],
                zip: data.zonecode,
                main: data.roadAddress || data.jibunAddress,
              },
            }));
            setAddressTarget(null);
          },
        }).embed(postcodeRef.current);
      } else if (attempts > 50) {
        window.clearInterval(timer);
        setAddressError(
          '주소 검색을 연결할 수 없습니다. 창을 닫고 주소를 직접 입력해 주세요.',
        );
      }
    }, 150);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [addressTarget]);

  useEffect(() => {
    type Tool = {
      name: string;
      title: string;
      description: string;
      inputSchema: object;
      annotations: object;
      execute: (input: unknown) => unknown;
    };
    const context = (
      document as Document & {
        modelContext?: {
          registerTool: (
            tool: Tool,
            options: { signal: AbortSignal },
          ) => void | Promise<void>;
        };
      }
    ).modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    const register = (tool: Tool) => {
      try {
        void Promise.resolve(
          context.registerTool(tool, { signal: lifecycle.signal }),
        ).catch(() => {});
      } catch {}
    };
    register({
      name: 'get_consultation_preferences',
      title: '상담 조건 확인',
      description:
        '현재 입력된 창업 조건을 읽습니다. 고객 이름, 전화번호, 주소는 반환하지 않습니다.',
      inputSchema: {
        type: 'object',
        properties: {},
        additionalProperties: false,
      },
      annotations: { readOnlyHint: true },
      execute: () => {
        const f = formRef.current;
        return {
          areas: f.areas,
          size: f.size,
          market: f.market,
          deposit: f.deposit,
          premium: f.premium,
          funding: f.funding,
          operation: f.operation,
        };
      },
    });
    register({
      name: 'stage_consultation_preferences',
      title: '창업 조건 입력',
      description:
        '상담 폼의 창업 조건을 입력합니다. 저장하거나 제출하지 않으며 사용자가 확인할 수 있도록 화면에 반영합니다.',
      inputSchema: {
        type: 'object',
        properties: {
          size: { type: 'string' },
          market: { type: 'string', enum: markets.map((m) => m.name) },
          funding: {
            type: 'string',
            enum: ['현금', '현금+대출', '현금+대출+리스'],
          },
          operation: { type: 'string', enum: ['오토', '점주+알바', '점주'] },
        },
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false },
      execute: (input) => {
        if (!input || typeof input !== 'object' || Array.isArray(input))
          throw new Error('입력은 객체여야 합니다.');
        const patch = input as Record<string, unknown>;
        const allowed: Record<string, string[]> = {
          market: markets.map((m) => m.name),
          funding: ['현금', '현금+대출', '현금+대출+리스'],
          operation: ['오토', '점주+알바', '점주'],
        };
        for (const [key, value] of Object.entries(patch)) {
          if (
            typeof value !== 'string' ||
            !(key === 'size' || key in allowed) ||
            (key === 'size'
              ? !/^\d+(\.\d+)?$/.test(value) ||
                Number(value) <= 0 ||
                Number(value) > 100000
              : !allowed[key].includes(value))
          )
            throw new Error('올바르지 않은 창업 조건입니다.');
        }
        flushSync(() => setForm((prev) => ({ ...prev, ...patch })));
        return { status: 'staged', fields: Object.keys(patch) };
      },
    });
    return () => lifecycle.abort();
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!/^0\d{8,10}$/.test(form.phone.replace(/\D/g, ''))) {
      setError('전화번호를 확인해 주세요. 숫자 9~11자리로 입력해 주세요.');
      document.getElementById('phone')?.focus();
      return;
    }
    if (!form.market || !form.funding || !form.operation) {
      setError('희망 상권, 투자금 형태, 운영 형태를 모두 선택해 주세요.');
      return;
    }
    const areas = form.areas.filter((a) => a.city || a.district);
    if (areas.some((a) => !a.city || !a.district)) {
      setError('선택한 희망 지역의 시·군·구를 끝까지 선택해 주세요.');
      return;
    }
    if (new Set(areas.map((a) => a.city + a.district)).size !== areas.length) {
      setError('희망 지역은 순위별로 서로 다른 지역을 선택해 주세요.');
      return;
    }
    setComplete(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  // 상담 파일은 둘로 가른다.
  //
  //   상담카드.csv — 고객명·전화번호·거주지·근무지가 들어 있다. 상담사가 보관한다.
  //   조건.csv     — 개인정보가 없다. 파이프라인(analysis/consult.py)이 읽는 키만 담는다.
  //
  // 한 파일로 내려주면 그 파일이 그대로 파이프라인에 들어가고, 그때 고객 연락처가
  // 심의 자료로 넘어간다. 파이프라인이 읽는 키만 골라 쓰긴 하지만 — 애초에
  // 들어가지 않는 것과, 들어갔다가 걸러지는 것은 다르다.
  //
  // 키 이름은 analysis/consult.py 의 읽는키 와 글자 그대로 같아야 한다.
  // 다르면 파이프라인이 조용히 빈 값으로 읽고 필터가 아무것도 거르지 않는다.

  function csvCell(value: string) {
    // 쉼표·따옴표·줄바꿈이 든 칸만 감싼다. 감싼 칸 안의 따옴표는 겹따옴표로 쓴다.
    return /[",\n\r]/.test(value) ? '"' + value.replace(/"/g, '""') + '"' : value;
  }
  function csv(rows: string[][]) {
    // 맨 앞의 \ufeff 는 엑셀이 UTF-8 로 읽게 하는 표식이다. 없으면 한글이 깨진다.
    // 줄 끝은 CRLF — 엑셀이 그것을 기대한다.
    return '\ufeff' + rows.map((r) => r.map(csvCell).join(',')).join('\r\n') + '\r\n';
  }
  function save(name: string, text: string) {
    const blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function 주소(a: Address) {
    return [a.main, a.detail].filter(Boolean).join(' ');
  }
  function 희망지역() {
    return form.areas.filter((a) => a.city && a.district)
      .map((a) => `${a.city} ${a.district}`);
  }
  function 스탬프() {
    const d = new Date();
    const p2 = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${p2(d.getMonth() + 1)}${p2(d.getDate())}_${p2(d.getHours())}${p2(d.getMinutes())}`;
  }

  function 상담카드내려받기() {
    const 지역 = 희망지역();
    save(
      `상담카드_${form.name || '무명'}_${스탬프()}.csv`,
      csv([
        ['항목', '값'],
        ['작성시각', new Date().toISOString()],
        ['고객명', form.name],
        ['고객전화번호', form.phone],
        ['거주지', 주소(form.home)],
        ['근무지', 주소(form.work)],
        ...지역.map((a, i) => [`희망지역_${i + 1}순위`, a]),
        ['희망평수', form.size],
        ['희망상권', form.market],
        ['보증금_만원', form.deposit],
        ['권리금_만원', form.premium],
        ['매매총예산_만원', form.saleBudget],
        ['월세상한_만원', form.monthlyRentMax],
        ['투자금형태', form.funding],
        ['운영형태', form.operation],
      ]),
    );
  }

  function 조건내려받기() {
    // 이 파일 이름에는 고객명을 넣지 않는다 — 파일 이름도 개인정보다.
    // 열 이름·차례는 analysis/consult.py 의 읽는키 그대로다.
    // 목록 칸(희망지역·희망상권)은 · 로 잇는다 — 파이프라인이 목록을 찍을 때 쓰는 구분자다.
    save(
      `조건_${스탬프()}.csv`,
      csv([
        ['희망평수', '희망상권', '희망지역', '보증금_만원', '권리금_만원',
          '투자금형태', '운영형태'],
        [form.size, form.market, 희망지역().join('·'), form.deposit,
          form.premium, form.funding, form.operation],
      ]),
    );
  }

  function download() {
    상담카드내려받기();
    // 브라우저가 연속된 두 개의 내려받기를 하나로 묶어 막는 일이 있다 — 사이를 띄운다.
    setTimeout(조건내려받기, 400);
  }

  function renderAddressFields({
    target,
    title,
  }: {
    target: 'home' | 'work';
    title: string;
  }) {
    return (
      <div className="field address-field">
        <Label htmlFor={`${target}-address`}>
          {title}
          <span className="required">*</span>
        </Label>
        <div className="address-row">
          <Input
            aria-label={`${title} 우편번호`}
            placeholder="우편번호"
            value={form[target].zip}
            onChange={(e) => setAddress(target, 'zip', e.target.value)}
            maxLength={5}
            inputMode="numeric"
          />
          <Button
            type="button"
            variant="outline"
            onClick={() => setAddressTarget(target)}
          >
            <Search size={15} /> 주소 검색
          </Button>
        </div>
        <Input
          id={`${target}-address`}
          placeholder="도로명 또는 지번 주소"
          value={form[target].main}
          onChange={(e) => setAddress(target, 'main', e.target.value)}
          required
        />
        <Input
          aria-label={`${title} 상세주소`}
          placeholder="상세주소 (선택)"
          value={form[target].detail}
          onChange={(e) => setAddress(target, 'detail', e.target.value)}
        />
      </div>
    );
  }
  if (complete)
    return (
      <div className="workspace-page property-review">
        <header className="tool-header">
          <Link href="/" className="brand">
            <span className="brand-mark">
              <span className="brand-monogram">스스</span>
            </span>
            <strong>
              스스닷컴<span>stores scout</span>
            </strong>
          </Link>
          <Button variant="outline" onClick={() => setComplete(false)}>
            <ArrowLeft size={16} /> 상담 조건 수정
          </Button>
        </header>
        <main className="property-review-main">
          <div className="workspace-heading">
            <div>
              <span className="eyebrow">CONSULTATION · PROPERTY MATCH</span>
              <h1>{form.name} 고객님의 조건별 매물</h1>
              <p>
                입력하신 조건을 정리했습니다. 아래에서 상담 파일로 내려받으실 수
                있습니다.
              </p>
            </div>
          </div>
          <section className="property-condition-summary">
            <div>
              <h2>희망 지역</h2>
              {form.areas
                .filter((a) => a.district)
                .map((a, i) => (
                  <p key={i}>
                    {i + 1}순위 · {a.city} {a.district}
                  </p>
                ))}
            </div>
            <div>
              <h2>면적·상권</h2>
              <p>
                전용 {form.size}평 · {form.market}
              </p>
              <p>
                {form.operation} · {form.funding}
              </p>
            </div>
            <div>
              <h2>가격 상한</h2>
              <p>매매 총예산 {money(form.saleBudget)}</p>
              <p>
                임대 보증금 {money(form.deposit)} / 권리금 {money(form.premium)}{' '}
                / 월세 {money(form.monthlyRentMax)}
              </p>
            </div>
          </section>
          <section className="property-layout">
            <div className="property-map-wrap">
              <div ref={mapRef} className="property-map" aria-label="희망 지역 지도" />
              {mapState.status !== 'ready' && (
                <div className={`map-state map-state-${mapState.status}`} role="status">
                  {mapState.status === 'loading' && <p>지도를 불러오는 중…</p>}
                  {mapState.status === 'nokey' && (
                    <>
                      <p>
                        <b>지도 키가 없습니다.</b>
                      </p>
                      <p>
                        카카오 지도 JavaScript 키를 GitHub 저장소 변수{' '}
                        <code>KAKAO_JS_KEY</code> 에 넣고 다시 배포하면 여기에 지도가
                        뜹니다. 절차는 DEPLOY.md 「결과 화면 지도」.
                      </p>
                    </>
                  )}
                  {mapState.status === 'error' && (
                    <>
                      <p>
                        <b>지도를 표시하지 못했습니다.</b>
                      </p>
                      <p>{mapState.message}</p>
                    </>
                  )}
                </div>
              )}
              <p className="map-note">
                지도: Kakao. 희망 지역(시·군·구)만 지도에 표시합니다. 고객명·연락처·
                거주지·근무지는 지도에 보내지 않습니다.
              </p>
            </div>
            <div>
              <section className="workspace-card map-legend">
                <h2>지도에 표시한 지역</h2>
                {mapState.plotted.length === 0 && mapState.missed.length === 0 && (
                  <p className="planned">희망 지역을 고르지 않았습니다</p>
                )}
                <ol>
                  {form.areas
                    .filter((a) => a.city && a.district)
                    .map((a, i) => {
                      const name = `${a.city} ${a.district}`;
                      const on = mapState.plotted.includes(name);
                      const off = mapState.missed.includes(name);
                      return (
                        <li key={name} className={on ? 'on' : off ? 'off' : ''}>
                          <span className="rank-badge">{i + 1}순위</span> {name}
                          {off && mapState.status === 'ready' && (
                            <small> · 좌표를 찾지 못했습니다</small>
                          )}
                        </li>
                      );
                    })}
                </ol>
              </section>
              {/* 매물 조회는 서버가 있어야 한다. 이 사이트는 정적 배포라 서버가 없다 —
                  '준비 중' 이라고 적는다. 빈 목록을 보여 주면 '조건에 맞는 매물이 없다'
                  로 읽힌다. 없는 것과 아직 못 보는 것은 다르다. */}
              <section className="workspace-card">
                <h2>조건에 맞는 매물</h2>
                <p className="planned">매물 연동 준비 중</p>
                <p>
                  지금은 상담 조건을 정리해 파일로 내려받는 데까지 됩니다. 조건별
                  매매·임대 목록은 매물 공급처를 연결한 뒤 이 지도 위에 올라옵니다.
                </p>
              </section>
            </div>
          </section>
          <details className="workspace-card property-save">
            <summary>상담 내용 확인·저장·내려받기</summary>
            <dl className="complete-summary">
              <dt>고객</dt>
              <dd>
                {form.name} · {form.phone}
              </dd>
              <dt>거주지</dt>
              <dd>
                {form.home.main} {form.home.detail}
              </dd>
              <dt>근무지</dt>
              <dd>
                {form.work.main} {form.work.detail}
              </dd>
            </dl>
            <p>
              입력하신 값은 서버로 나가지 않습니다. 내려받은 파일이 유일한 기록입니다.
            </p>
            {/* 파일을 둘로 가른 이유를 화면에도 적는다. 적지 않으면 상담사가
                둘 중 아무거나 넘기게 되고, 가른 것이 무의미해진다. */}
            <dl className="download-guide">
              <dt>상담카드</dt>
              <dd>
                고객명·전화번호·거주지·근무지가 들어 있습니다.{' '}
                <b>상담사가 보관하고, 분석에는 넘기지 않습니다.</b>
              </dd>
              <dt>조건</dt>
              <dd>
                개인정보가 없습니다. 평수·상권·지역·투자금·운영형태만 담겨 있어{' '}
                <b>이 파일만 분석에 넘깁니다.</b>
              </dd>
            </dl>
            <div className="download-row">
              <Button variant="outline" onClick={상담카드내려받기}>
                <Download size={16} /> 상담카드 CSV
              </Button>
              <Button variant="outline" onClick={조건내려받기}>
                <Download size={16} /> 조건 CSV
              </Button>
              <Button variant="outline" onClick={download}>
                <Download size={16} /> 둘 다
              </Button>
            </div>
          </details>
        </main>
      </div>
    );
  return (
    <div className="tool-page">
      <header className="tool-header">
        <Link href="/" className="brand">
          <span className="brand-mark">
            <span className="brand-monogram" aria-hidden="true">
              스스
            </span>
          </span>
          <strong>
            스스닷컴<span>stores scout</span>
          </strong>
        </Link>
        <span className="tool-name">상권분석 도구</span>
        {/* /workspace 는 서버가 있어야 하는 화면이다. 이 배포에는 없다 —
            없는 곳으로 보내는 링크를 두면 404 가 난다. 메인으로 돌린다. */}
        <Link href="/" className="back-home">
          <ArrowLeft size={15} /> 메인으로
        </Link>
      </header>
      <div className="tool-layout">
        <aside className="tool-sidebar">
          <span className="eyebrow">NEW CONSULTATION</span>
          <h2>
            좋은 출점의
            <br />첫 번째 단계.
          </h2>
          <p>
            고객의 조건을 정리하면
            <br />
            상권의 방향이 보입니다.
          </p>
          <nav className="form-steps">
            {[
              ['basic', '고객 기본 정보', UserRound],
              ['location', '창업 희망 조건', MapPin],
              ['budget', '투자 계획', Wallet],
              ['operation', '운영 계획', Store],
            ].map(([id, title, Icon], i) => {
              const StepIcon = Icon as typeof UserRound;
              return (
                <a
                  key={String(id)}
                  href={`#${id}`}
                  className={filled[i] ? 'done' : ''}
                >
                  <span className="step-icon">
                    {filled[i] ? <Check size={15} /> : <StepIcon size={16} />}
                  </span>
                  <span>{String(title)}</span>
                  <small>0{i + 1}</small>
                </a>
              );
            })}
          </nav>
          <div className="sidebar-tip">
            <ShieldCheck size={20} />
            <h3>상담 정보는 안전하게</h3>
            <p>
              입력하신 내용은 이 브라우저 안에만 있습니다. 서버로 보내지 않고,
              페이지를 벗어나면 지워집니다. 남기시려면 상담 파일로 내려받으십시오.
            </p>
          </div>
          <span className="sidebar-domain">stores-scout.com</span>
        </aside>
        <main className="consultation-main">
          <div className="breadcrumb">
            <Link href="/">홈</Link>
            <ChevronRight size={12} />
            <span>상권분석</span>
            <ChevronRight size={12} />
            <b>고객 상담</b>
          </div>
          <div className="form-heading">
            <div>
              <span className="eyebrow">STEP 01 · CLIENT CONSULTATION</span>
              <h1>고객 상담</h1>
              <p>고객에게 맞는 상권을 찾기 위해 창업 조건을 입력해 주세요.</p>
            </div>
            <span className="required-guide">
              <i /> 필수 입력 항목
            </span>
          </div>
          <form onSubmit={submit}>
            <section className="form-section" id="basic">
              <div className="form-section-title">
                <span>01</span>
                <h2>고객 기본 정보</h2>
                <small>상담 고객의 기본 정보를 입력해 주세요.</small>
              </div>
              <div className="field-grid">
                <div className="field">
                  <Label htmlFor="customer-name">
                    고객명 <span className="required">*</span>
                  </Label>
                  <Input
                    id="customer-name"
                    autoComplete="name"
                    placeholder="고객 이름을 입력해 주세요"
                    value={form.name}
                    onChange={(e) => update('name', e.target.value)}
                    required
                    maxLength={60}
                  />
                </div>
                <div className="field">
                  <Label htmlFor="phone">
                    고객 전화번호 <span className="required">*</span>
                  </Label>
                  <Input
                    id="phone"
                    type="tel"
                    autoComplete="tel"
                    placeholder="010-0000-0000"
                    value={form.phone}
                    onChange={(e) => update('phone', e.target.value)}
                    required
                    maxLength={14}
                  />
                </div>
                {renderAddressFields({ target: 'home', title: '거주지' })}
                {renderAddressFields({ target: 'work', title: '근무지' })}
              </div>
              <p className="field-help">
                <Info size={13} /> 주소 검색 후 우편번호와 기본 주소가 자동으로
                입력됩니다. 상세주소는 선택 사항입니다.
              </p>
            </section>
            <section className="form-section" id="location">
              <div className="form-section-title">
                <span>02</span>
                <h2>창업 희망 조건</h2>
                <small>어떤 지역과 상권을 찾고 계신가요?</small>
              </div>
              <Label className="group-label">
                창업 희망 지역 <span className="required">*</span>
                <small>1순위 필수 · 2, 3순위 선택</small>
              </Label>
              <div className="regions-list">
                {form.areas.map((area, i) => (
                  <div className="region-row" key={i}>
                    <span className={`rank rank-${i}`}>
                      {i + 1}
                      <small>순위</small>
                    </span>
                    <NativeSelect
                      aria-label={`${i + 1}순위 시·도`}
                      value={area.city}
                      required={i === 0}
                      onChange={(e) => {
                        const next = [...form.areas];
                        next[i] = { city: e.target.value, district: '' };
                        update('areas', next);
                      }}
                    >
                      <option value="">시·도 선택</option>
                      {Object.keys(REGIONS).map((city) => (
                        <option key={city}>{city}</option>
                      ))}
                    </NativeSelect>
                    <NativeSelect
                      aria-label={`${i + 1}순위 시·군·구`}
                      value={area.district}
                      disabled={!area.city}
                      required={i === 0 || Boolean(area.city)}
                      onChange={(e) => {
                        const next = [...form.areas];
                        next[i] = { ...area, district: e.target.value };
                        update('areas', next);
                      }}
                    >
                      <option value="">시·군·구 선택</option>
                      {(REGIONS[area.city] || []).map((d) => (
                        <option key={d}>{d}</option>
                      ))}
                    </NativeSelect>
                  </div>
                ))}
              </div>
              <div className="field size-field">
                <Label htmlFor="size">
                  희망 평수 <span className="required">*</span>
                </Label>
                <div className="unit-input">
                  <Input
                    id="size"
                    type="number"
                    min="1"
                    max="100000"
                    step="0.1"
                    placeholder="예: 30"
                    value={form.size}
                    onChange={(e) => update('size', e.target.value)}
                    required
                  />
                  <span>평</span>
                </div>
                <small>
                  {form.size
                    ? `약 ${(Number(form.size) * 3.3058).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}㎡`
                    : '전용면적 기준으로 입력해 주세요.'}
                </small>
              </div>
              <fieldset>
                <legend>
                  희망 상권 <span className="required">*</span>
                </legend>
                <RadioGroup
                  className="market-options"
                  value={form.market}
                  onValueChange={(v) => update('market', v)}
                  aria-label="희망 상권"
                >
                  {markets.map(({ name, icon: Icon }) => (
                    <Label
                      className={`market-option ${form.market === name ? 'selected' : ''}`}
                      key={name}
                    >
                      <Icon size={21} />
                      <span>{name}</span>
                      <RadioGroupItem value={name} aria-label={name} />
                    </Label>
                  ))}
                </RadioGroup>
              </fieldset>
            </section>
            <section className="form-section" id="budget">
              <div className="form-section-title">
                <span>03</span>
                <h2>투자 계획</h2>
                <small>투자 가능한 범위를 확인합니다.</small>
              </div>
              <div className="field-grid">
                <div className="field">
                  <Label htmlFor="deposit">
                    보증금 <span className="required">*</span>
                  </Label>
                  <div className="unit-input">
                    <Input
                      id="deposit"
                      type="number"
                      min="0"
                      max="100000000"
                      step="1"
                      placeholder="예: 5,000"
                      value={form.deposit}
                      onChange={(e) => update('deposit', e.target.value)}
                      required
                    />
                    <span>만 원</span>
                  </div>
                </div>
                <div className="field">
                  <Label htmlFor="premium">
                    권리금 <span className="required">*</span>
                  </Label>
                  <div className="unit-input">
                    <Input
                      id="premium"
                      type="number"
                      min="0"
                      max="100000000"
                      step="1"
                      placeholder="권리금이 없으면 0"
                      value={form.premium}
                      onChange={(e) => update('premium', e.target.value)}
                      required
                    />
                    <span>만 원</span>
                  </div>
                </div>
              </div>
              <div className="total-investment">
                <span>보증금 + 권리금</span>
                <strong>
                  {total.toLocaleString('ko-KR')}
                  <small>만 원</small>
                </strong>
              </div>
              <div className="field-grid">
                <div className="field">
                  <Label htmlFor="sale-budget">매매 총예산 (선택)</Label>
                  <div className="unit-input">
                    <Input
                      id="sale-budget"
                      type="number"
                      min="0"
                      max="100000000"
                      step="1"
                      placeholder="매매 검색 시 입력"
                      value={form.saleBudget}
                      onChange={(e) => update('saleBudget', e.target.value)}
                    />
                    <span>만 원</span>
                  </div>
                </div>
                <div className="field">
                  <Label htmlFor="monthly-rent-max">월세 상한 (선택)</Label>
                  <div className="unit-input">
                    <Input
                      id="monthly-rent-max"
                      type="number"
                      min="0"
                      max="10000000"
                      step="1"
                      placeholder="임대 검색 시 입력"
                      value={form.monthlyRentMax}
                      onChange={(e) => update('monthlyRentMax', e.target.value)}
                    />
                    <span>만 원</span>
                  </div>
                </div>
              </div>
              <p className="field-help">
                매매 총예산이 없으면 매매, 월세 상한이 없으면 임대 결과를
                제외합니다. 보증금·권리금을 매매 예산으로 계산하지 않습니다.
              </p>
              <fieldset>
                <legend>
                  투자금 형태 <span className="required">*</span>
                </legend>
                <RadioGroup
                  className="choice-options"
                  value={form.funding}
                  onValueChange={(v) => update('funding', v)}
                  aria-label="투자금 형태"
                >
                  {['현금', '현금+대출', '현금+대출+리스'].map((name) => (
                    <Label
                      className={`choice-option ${form.funding === name ? 'selected' : ''}`}
                      key={name}
                    >
                      <RadioGroupItem value={name} />
                      <span>{name.replaceAll('+', ' + ')}</span>
                    </Label>
                  ))}
                </RadioGroup>
              </fieldset>
            </section>
            <section className="form-section" id="operation">
              <div className="form-section-title">
                <span>04</span>
                <h2>운영 계획</h2>
                <small>예상하시는 매장 운영 방식을 선택해 주세요.</small>
              </div>
              <fieldset>
                <legend className="sr-only">운영 형태</legend>
                <RadioGroup
                  className="choice-options operation-options"
                  value={form.operation}
                  onValueChange={(v) => update('operation', v)}
                  aria-label="운영 형태"
                >
                  {[
                    { name: '오토', desc: '직원 중심의 매장 운영' },
                    { name: '점주+알바', desc: '점주와 직원이 함께 운영' },
                    { name: '점주', desc: '점주가 직접 운영' },
                  ].map(({ name, desc }) => (
                    <Label
                      className={`choice-option ${form.operation === name ? 'selected' : ''}`}
                      key={name}
                    >
                      <RadioGroupItem value={name} />
                      <span>
                        {name.replaceAll('+', ' + ')}
                        <small>{desc}</small>
                      </span>
                    </Label>
                  ))}
                </RadioGroup>
              </fieldset>
            </section>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <div className="form-actions">
              <p>
                <ShieldCheck size={15} /> 서버로 보내지 않습니다. 확인 화면에서
                파일로 내려받으십시오.
              </p>
              <Button type="submit" className="submit-button">
                상담 내용 확인 <ArrowRight size={17} />
              </Button>
            </div>
          </form>
        </main>
        <aside className="summary-sidebar">
          <div className="summary-card">
            <span className="eyebrow">CONSULTATION SUMMARY</span>
            <h3>상담 조건 한눈에</h3>
            <div className="completion-count">
              <span>입력 완료</span>
              <b>
                {progress}
                <small> / 4</small>
              </b>
            </div>
            <div className="completion-bar">
              <span style={{ width: `${progress * 25}%` }} />
            </div>
            <dl>
              <dt>고객명</dt>
              <dd>{form.name || '아직 입력하지 않았어요'}</dd>
              <dt>1순위 희망 지역</dt>
              <dd>
                {form.areas[0].district
                  ? `${form.areas[0].city} ${form.areas[0].district}`
                  : '지역을 선택해 주세요'}
              </dd>
              <dt>희망 면적 · 상권</dt>
              <dd>
                {form.size ? `${form.size}평` : '면적 미입력'}
                <span className="summary-dot">·</span>
                {form.market || '상권 미선택'}
              </dd>
              <dt>투자금 합계</dt>
              <dd className="summary-money">
                {total.toLocaleString('ko-KR')} <small>만 원</small>
              </dd>
              <dt>운영 형태</dt>
              <dd>{form.operation || '운영 형태 미선택'}</dd>
            </dl>
            <div className="summary-bottom">
              <ClipboardCheck size={16} /> 모든 조건을 확인한 후<br />
              상담 파일로 내려받으세요.
            </div>
          </div>
          <p className="data-disclaimer">
            매물 조회와 유동인구는 아직 연결되지 않았습니다.
            <br />
            유동인구는 별도 데이터 연결이 필요합니다.
          </p>
        </aside>
      </div>
      <Dialog
        open={Boolean(addressTarget)}
        onOpenChange={(open) => {
          if (!open) setAddressTarget(null);
        }}
      >
        <DialogContent className="postcode-dialog">
          <DialogTitle>
            {addressTarget === 'home' ? '거주지' : '근무지'} 주소 검색
          </DialogTitle>
          <DialogDescription>
            도로명, 건물명 또는 지번으로 검색해 주세요.
          </DialogDescription>
          {addressError ? <p className="form-error">{addressError}</p> : null}
          <div ref={postcodeRef} className="postcode-frame" />
          <p className="field-help">주소 검색 서비스: Kakao (Daum) 우편번호</p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
