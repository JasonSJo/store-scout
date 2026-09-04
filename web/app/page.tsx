import { useRef } from 'react';
import Link from '@/lib/link';
import { ArrowRight, ArrowUpRight, ClipboardList, FileSpreadsheet, Lock, ShieldCheck } from 'lucide-react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useGSAP } from '@gsap/react';

gsap.registerPlugin(useGSAP, ScrollTrigger);

/* 메인 페이지. 서버를 부르지 않고, 숫자를 지어내지 않는다.
   유동인구·매출·성공률 같은 수치는 여기 없다 — 있으면 지어낸 것이다.
   그림은 전부 인라인 SVG 다. 바깥 이미지 서버를 부르면 회사 망에서 빈 칸이 된다. */

const 상권유형 = [
  { 이름: '오피스', 한줄: '평일 점심과 퇴근길에 수요가 몰리고, 주말에는 비는 상권.', c1: '#3b2a20', c2: '#140f0b', a: '28deg' },
  { 이름: '주거', 한줄: '저녁과 주말이 살아 있고, 단골이 매출을 받치는 상권.', c1: '#2f3527', c2: '#0f120c', a: '-32deg' },
  { 이름: '학교', 한줄: '학기와 방학의 리듬을 그대로 타는 상권.', c1: '#33302a', c2: '#100e0b', a: '90deg' },
  { 이름: '병원', 한줄: '환자와 보호자의 대기 시간이 수요가 되는 상권.', c1: '#2b2f38', c2: '#0d0f13', a: '0deg' },
  { 이름: '메인', 한줄: '번화가의 유동이 그대로 문 앞을 지나는 상권.', c1: '#4a2a1c', c2: '#160c07', a: '55deg' },
  { 이름: '복합', 한줄: '둘 이상의 성격이 겹쳐, 시간대마다 손님이 바뀌는 상권.', c1: '#3a2c2c', c2: '#120d0d', a: '-60deg' },
];

function HeroArt() {
  // 거리 격자 위에 동심원과 핀. 지도가 아니라 지도의 인상이다 — 실제 좌표가 아니다.
  return (
    <svg viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <pattern id="lp-grid" width="80" height="80" patternUnits="userSpaceOnUse">
          <path d="M80 0H0V80" fill="none" stroke="#16130f" strokeOpacity=".07" strokeWidth="1" />
        </pattern>
        <linearGradient id="lp-fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f7f4ee" stopOpacity="0" />
          <stop offset="1" stopColor="#f7f4ee" stopOpacity="1" />
        </linearGradient>
      </defs>
      <rect width="1600" height="900" fill="url(#lp-grid)" />
      <g fill="none" stroke="#ff6d2d" strokeWidth="1.5">
        <circle cx="800" cy="470" r="120" strokeOpacity=".55" />
        <circle cx="800" cy="470" r="240" strokeOpacity=".32" />
        <circle cx="800" cy="470" r="380" strokeOpacity=".2" />
        <circle cx="800" cy="470" r="540" strokeOpacity=".1" />
      </g>
      <g stroke="#16130f" strokeOpacity=".14" strokeWidth="2" fill="none">
        <path d="M0 620 C 300 600, 520 520, 800 470 S 1300 380, 1600 300" />
        <path d="M200 0 C 420 260, 640 380, 800 470 S 1080 760, 1180 900" />
      </g>
      <g fill="#ff6d2d">
        <circle cx="800" cy="470" r="9" />
        <circle cx="800" cy="470" r="22" fillOpacity=".18" />
        <circle cx="1046" cy="392" r="6" fillOpacity=".8" />
        <circle cx="612" cy="612" r="6" fillOpacity=".8" />
        <circle cx="948" cy="662" r="6" fillOpacity=".8" />
      </g>
      <rect y="620" width="1600" height="280" fill="url(#lp-fade)" />
    </svg>
  );
}

function PillArt() {
  return (
    <svg viewBox="0 0 92 40" aria-hidden="true">
      <g fill="none" stroke="#fff" strokeOpacity=".55" strokeWidth="1.2">
        <circle cx="46" cy="20" r="9" /><circle cx="46" cy="20" r="17" />
        <path d="M0 30 C 20 26, 34 22, 46 20 S 72 12, 92 8" />
      </g>
      <circle cx="46" cy="20" r="3.2" fill="#fff" />
      <circle cx="70" cy="13" r="2" fill="#fff" fillOpacity=".8" />
      <circle cx="26" cy="27" r="2" fill="#fff" fillOpacity=".8" />
    </svg>
  );
}

function StepArtForm() {
  return (
    <svg viewBox="0 0 640 320" aria-hidden="true">
      <rect x="120" y="36" width="400" height="248" rx="18" fill="#fff" stroke="#e2dcd1" />
      {[0, 1, 2, 3].map((i) => (
        <g key={i} transform={`translate(150 ${70 + i * 52})`}>
          <rect width="90" height="12" rx="6" fill="#efe9df" />
          <rect x="110" width={[230, 180, 250, 140][i]} height="26" y="-7" rx="8" fill="#f7f4ee" stroke="#e2dcd1" />
        </g>
      ))}
      <rect x="150" y="256" width="120" height="14" rx="7" fill="#ff6d2d" />
    </svg>
  );
}

function StepArtCsv() {
  return (
    <svg viewBox="0 0 640 320" aria-hidden="true">
      <g transform="translate(96 60)">
        <rect width="200" height="200" rx="16" fill="#fff8f4" stroke="#f1c4b3" />
        <rect x="24" y="30" width="110" height="12" rx="6" fill="#bb3e18" fillOpacity=".55" />
        <rect x="24" y="60" width="150" height="10" rx="5" fill="#f1c4b3" />
        <rect x="24" y="82" width="120" height="10" rx="5" fill="#f1c4b3" />
        <rect x="24" y="104" width="140" height="10" rx="5" fill="#f1c4b3" />
        <text x="24" y="176" fontSize="15" fontWeight="700" fill="#bb3e18">상담카드.csv</text>
      </g>
      <g transform="translate(344 60)">
        <rect width="200" height="200" rx="16" fill="#fff" stroke="#16130f" />
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <rect key={i} x={24 + (i % 7) * 22} y="40" width="16" height="10" rx="3" fill="#16130f" fillOpacity=".8" />
        ))}
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <rect key={i} x={24 + (i % 7) * 22} y="62" width="16" height="10" rx="3" fill="#efe9df" />
        ))}
        <text x="24" y="176" fontSize="15" fontWeight="700" fill="#16130f">조건.csv</text>
        <text x="24" y="140" fontSize="12" fill="#8f887c">개인정보 없음</text>
      </g>
      <path d="M300 160 h40" stroke="#8f887c" strokeWidth="2" strokeDasharray="4 6" />
    </svg>
  );
}

function StepArtVerdict() {
  const rows: Array<[string, number, string]> = [['통과', 210, '#16130f'], ['보류', 150, '#ff6d2d'], ['부결', 90, '#bb3e18'], ['통과', 240, '#16130f']];
  return (
    <svg viewBox="0 0 640 320" aria-hidden="true">
      <rect x="100" y="40" width="440" height="240" rx="18" fill="#fff" stroke="#e2dcd1" />
      {rows.map(([label, w, c], i) => (
        <g key={i} transform={`translate(130 ${82 + i * 48})`}>
          <rect width="120" height="12" rx="6" fill="#efe9df" />
          <rect x="150" width={w} height="14" y="-1" rx="7" fill={c} fillOpacity={c === '#16130f' ? .85 : 1} />
          <text x="400" y="10" fontSize="12" fontWeight="700" fill={c} textAnchor="end">{label}</text>
        </g>
      ))}
    </svg>
  );
}

export default function Home() {
  const root = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    const mm = gsap.matchMedia();
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      // 히어로 진입
      gsap.to('.lp-hero [data-rise]', { opacity: 1, y: 0, duration: 1.1, stagger: 0.12, ease: 'power3.out', delay: 0.1 });
      // 절마다 떠오르기
      gsap.utils.toArray<HTMLElement>('.lp-section [data-rise]').forEach((el) => {
        gsap.to(el, { opacity: 1, y: 0, duration: 0.9, ease: 'power3.out',
          scrollTrigger: { trigger: el, start: 'top 88%', once: true } });
      });
      // 핀 고정 분할 — 왼쪽 제목은 서 있고 오른쪽 단계가 올라온다
      ScrollTrigger.create({
        trigger: '.lp-flow-left', start: 'top 120px',
        endTrigger: '.lp-flow-right', end: 'bottom bottom',
        pin: true, pinSpacing: false,
      });
      // 이미지 스케일·페이드 — 작게 들어와 커지고, 나갈 때 어두워진다
      gsap.utils.toArray<HTMLElement>('.lp-step-visual').forEach((el) => {
        gsap.fromTo(el, { scale: 0.8, opacity: 0.35 }, { scale: 1, opacity: 1, ease: 'none',
          scrollTrigger: { trigger: el, start: 'top 92%', end: 'top 45%', scrub: true } });
        gsap.to(el, { opacity: 0.2, ease: 'none',
          scrollTrigger: { trigger: el, start: 'bottom 40%', end: 'bottom 8%', scrub: true } });
      });
    });
    mm.add('(prefers-reduced-motion: reduce)', () => {
      gsap.set('[data-rise]', { opacity: 1, y: 0 });
    });
  }, { scope: root });

  return (
    <div className="lp" ref={root}>
      <nav className="lp-nav" aria-label="주 메뉴">
        <Link href="/" className="lp-nav-brand"><span className="lp-mark" aria-hidden="true">스스</span>스스닷컴</Link>
        <div className="lp-nav-links">
          <a href="#flow">진행 방식</a>
          <a href="#bento">받는 것</a>
          <a href="#types">상권 유형</a>
        </div>
        <Link href="/consultation" className="lp-nav-cta">상담 시작 <ArrowUpRight size={15} /></Link>
      </nav>

      <main>
        <section className="lp-hero">
          <div className="lp-hero-art"><HeroArt /></div>
          <div className="lp-hero-glow" />
          <div className="lp-grain" />
          <div className="lp-hero-inner">
            <h1 data-rise>
              좋은 입지는 감이 아니라
              <span className="lp-inline-pill" aria-hidden="true"><PillArt /></span>
              <br />
              <em>근거로</em> 정합니다.
            </h1>
            <p className="lp-hero-sub" data-rise>
              고객 상담에서 받은 조건을 파일 하나로 정리해 사내 심의에 넘깁니다.
              고객의 이름과 연락처는 이 브라우저 밖으로 나가지 않습니다.
            </p>
            <div className="lp-hero-ctas" data-rise>
              <Link href="/consultation" className="lp-btn lp-btn-dark">상담 시작하기 <ArrowRight size={18} /></Link>
              <a href="#flow" className="lp-btn lp-btn-light">진행 방식 보기</a>
            </div>
            <div className="lp-hero-foot" data-rise><span />프랜차이즈 출점팀의 사내 판단 도구<span /></div>
          </div>
        </section>

        <section className="lp-section" id="bento">
          <div className="lp-wrap">
            <h2 className="lp-h2" data-rise>상담 한 번에 받는 것, 그리고 밖으로 나가지 않는 것.</h2>
            <p className="lp-lead" data-rise>
              화면은 받아 적기만 합니다. 계산하지 않고, 서버로 보내지 않습니다.
              그래서 무엇을 받는지와 무엇이 어디로 가는지를 여기서 그대로 보여 드립니다.
            </p>
            <div className="lp-bento">
              <article className="lp-card lp-card-a" data-rise>
                <span className="lp-card-icon"><ClipboardList size={20} /></span>
                <h3>고객 상담에서 받는 항목</h3>
                <p>고객 기본 정보, 창업 희망 조건, 투자 계획, 운영 계획. 상담사가 고객 앞에서 그대로 따라 묻는 순서입니다.</p>
                <div className="lp-chips">
                  <span>고객명</span><span>전화번호</span><span>거주지</span><span>근무지</span>
                  <span>희망 지역 1·2·3순위</span><span>희망 평수</span>
                  <span className="on">오피스</span><span className="on">주거</span><span className="on">학교</span><span className="on">병원</span><span className="on">메인</span><span className="on">복합</span>
                  <span>보증금</span><span>권리금</span>
                  <span>현금</span><span>현금+대출</span><span>현금+대출+리스</span>
                  <span>오토</span><span>점주+알바</span><span>점주</span>
                </div>
                <div className="lp-form-mock" aria-hidden="true">
                  <div className="lp-form-row"><small>희망 지역</small><i className="g" /></div>
                  <div className="lp-form-row"><small>희망 평수</small><i className="h" /></div>
                  <div className="lp-form-row"><small>보증금·권리금</small><i className="f" /></div>
                </div>
              </article>

              <article className="lp-card lp-card-b" data-rise>
                <span className="lp-card-icon"><FileSpreadsheet size={20} /></span>
                <h3>파일이 둘로 갈라집니다</h3>
                <p>고객 정보가 든 상담카드는 상담사가 보관하고, 조건만 담은 파일이 사내 심의로 갑니다. 들어가지 않는 것과 들어갔다가 걸러지는 것은 다릅니다.</p>
                <div className="lp-split">
                  <div className="lp-file keep"><b>상담카드.csv</b><small>고객명 · 전화번호 · 거주지 · 근무지</small>상담사 보관</div>
                  <div className="lp-split-arrow"><ArrowRight size={18} /></div>
                  <div className="lp-file send"><b>조건.csv</b><small>평수 · 상권 · 지역 · 투자금 · 운영형태</small>사내 심의로</div>
                </div>
              </article>

              <article className="lp-card lp-card-c" data-rise>
                <span className="lp-card-icon"><Lock size={20} /></span>
                <h3>브라우저 안에만</h3>
                <p>입력한 값은 서버로 보내지 않고, 페이지를 벗어나면 지워집니다. 남기려면 파일로 내려받습니다.</p>
              </article>

              <article className="lp-card lp-card-d" data-rise>
                <span className="lp-card-icon"><ShieldCheck size={20} /></span>
                <h3>사내 판단용</h3>
                <p>가맹희망자에게 예상 매출을 제시하는 문서가 아닙니다. 출점팀이 회의에 올리는 근거입니다.</p>
              </article>
            </div>
          </div>
        </section>

        <section className="lp-section" id="flow">
          <div className="lp-wrap lp-flow">
            <div className="lp-flow-left">
              <h2 className="lp-h2" data-rise>상담에서 심의까지,<br />세 걸음.</h2>
              <p className="lp-lead" data-rise>
                화면이 하는 일은 첫 걸음뿐입니다. 판단은 사내에서, 사람이 합니다.
                이 순서가 바뀌지 않도록 파일의 열 이름과 심의 도구가 읽는 이름을 테스트로 묶어 두었습니다.
              </p>
            </div>
            <div className="lp-flow-right">
              <article className="lp-step" data-rise>
                <div className="lp-step-num">01</div>
                <h3>상담 조건을 정리합니다</h3>
                <p>고객 앞에서 화면을 따라 묻고 적습니다. 지역은 시·도와 시·군·구를 고르고, 주소는 우편번호 검색으로 채웁니다.</p>
                <div className="lp-step-visual"><StepArtForm /></div>
              </article>
              <article className="lp-step" data-rise>
                <div className="lp-step-num">02</div>
                <h3>파일 둘을 내려받습니다</h3>
                <p>상담카드는 상담사가, 조건 파일은 사내 심의가 받습니다. 엑셀에서 바로 열립니다.</p>
                <div className="lp-step-visual"><StepArtCsv /></div>
              </article>
              <article className="lp-step" data-rise>
                <div className="lp-step-num">03</div>
                <h3>사내에서 심의합니다</h3>
                <p>조건 파일로 후보지를 거르고 심의표를 만듭니다. 통과·보류·부결과 그 사유가 한 표에 남습니다.</p>
                <div className="lp-step-visual"><StepArtVerdict /></div>
              </article>
            </div>
          </div>
        </section>

        <section className="lp-section" id="types" style={{ paddingTop: 0 }}>
          <div className="lp-wrap">
            <h2 className="lp-h2" data-rise>여섯 가지 상권, 여섯 가지 하루.</h2>
            <p className="lp-lead" data-rise>고객이 고르는 희망 상권입니다. 같은 평수라도 하루의 모양이 다릅니다.</p>
            <div className="lp-acc" data-rise>
              {상권유형.map((t) => (
                <div key={t.이름} className="lp-slice" style={{ '--c1': t.c1, '--c2': t.c2, '--a': t.a } as React.CSSProperties}>
                  <span className="lp-slice-title">{t.이름}</span>
                  <div className="lp-slice-body">
                    <h3>{t.이름} 상권</h3>
                    <p>{t.한줄}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <div className="lp-marquee" aria-hidden="true">
          <div className="lp-marquee-track">
            {[0, 1].map((k) => (
              <span key={k}>
                <span>고객 상담</span><span>조건 파일</span><span>사내 심의</span><span>개인정보는 브라우저 안에</span><span>사내 판단용</span><span>좋은 입지의 시작</span>
              </span>
            ))}
          </div>
        </div>

        <section className="lp-section lp-cta">
          <div className="lp-wrap">
            <h2 data-rise>상담을 시작하십시오.</h2>
            <p data-rise>다섯 분이면 조건이 정리됩니다. 파일은 당신의 컴퓨터에만 남습니다.</p>
            <div className="lp-hero-ctas" data-rise>
              <Link href="/consultation" className="lp-btn lp-btn-dark">고객 상담 열기 <ArrowRight size={18} /></Link>
              <a href="#bento" className="lp-btn lp-btn-light">받는 항목 다시 보기</a>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-wrap">
          <div><b>스스닷컴</b> · stores-scout.com</div>
          <nav>
            <Link href="/consultation">상권분석</Link>
            <a href="#flow">진행 방식</a>
            <a href="#types">상권 유형</a>
          </nav>
          <div>© 2026 STORES SCOUT · 좋은 입지의 시작.</div>
        </div>
      </footer>
    </div>
  );
}
