import Link from '@/lib/link';
import { ArrowUpRight, ArrowRight, MapPin, Radar, Building2, Users, ChevronDown, Layers3, ClipboardList } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function Home() {
  return <div className="site-home">
    <header className="site-header"><Link href="/" className="brand"><span className="brand-mark"><span className="brand-monogram" aria-hidden="true">스스</span></span><strong>스스닷컴<span>store scout</span></strong></Link><nav><a href="#how">서비스 소개</a><Link href="/consultation">상권분석</Link></nav><span className="header-label">FOR FRANCHISE TEAMS <ArrowUpRight size={14}/></span></header>
    <main>
      <section className="hero">
        <div className="hero-eyebrow"><span/> 좋은 매장의 시작, 정확한 상권에서</div>
        <h1>가능성을 찾고,<br/><em>확신으로 출점하세요.</em></h1>
        <p className="hero-description">고객의 창업 조건부터 상권의 가능성까지.<br/>프랜차이즈 출점의 모든 판단을, 스스닷컴에서.</p>
        <Button className="hero-cta" nativeButton={false} render={<Link href="/consultation"/>}>상권분석하기 <ArrowRight size={20}/></Button>
        <p className="hero-note"><ClipboardList size={14}/> 고객 상담 정보 입력부터 시작합니다</p>
        <div className="hero-tag tag-a"><span className="tag-icon"><Users size={19}/></span><div><small>상권을 읽는 데이터</small><b>유동인구 분석</b></div><ArrowUpRight size={17}/></div>
        <div className="hero-tag tag-b"><span className="tag-icon"><Building2 size={19}/></span><div><small>조건에 맞는 공간</small><b>상가 매물 탐색</b></div><ArrowUpRight size={17}/></div>
        <div className="hero-bottom"><span>더 나은 출점을 위한 새로운 기준</span><ChevronDown size={18}/></div>
      </section>
      <section className="capabilities" id="how"><div className="section-intro"><span className="eyebrow">FROM INSIGHT TO OPENING</span><h2>좋은 입지를 찾는 일,<br/>더 명확하고 간편하게.</h2><p>흩어져 있던 정보를 모아<br/>출점 검토의 흐름을 연결합니다.</p></div><div className="capability"><span className="feature-number">01</span><ClipboardList/><h3>고객을 이해하고</h3><p>창업 희망 지역, 투자금, 운영 방식까지.<br/>상담 조건을 한눈에 정리하세요.</p><Link href="/consultation">고객 상담 시작 <ArrowUpRight size={16}/></Link></div><div className="capability"><span className="feature-number">02</span><Radar/><h3>상권을 살펴보고</h3><p>유동인구와 지역 특성을 바탕으로<br/>입지의 가능성을 검토합니다.</p><span className="planned">데이터 연동 준비 중</span></div><div className="capability"><span className="feature-number">03</span><Layers3/><h3>출점 조건을 비교합니다</h3><p>상권과 부동산 정보를 함께 살펴<br/>고객에게 맞는 공간을 찾습니다.</p><span className="planned">매물 연동 준비 중</span></div></section>
      <section className="data-note" id="data"><div><MapPin size={21}/><div><h3>현장의 정보가, 더 나은 의사결정으로.</h3><p>현재 고객 상담 도구를 이용할 수 있습니다. 실시간 유동인구·부동산 정보는 제공처 연결 후 서비스됩니다.</p></div></div><Link href="/consultation">상담 도구 열기 <ArrowRight size={17}/></Link></section>
    </main><footer><Link href="/" className="footer-brand">스스닷컴 <span>stores-scout.com</span></Link><span>© 2026 STORE SCOUT. All rights reserved.</span><span>좋은 입지의 시작.</span></footer>
  </div>;
}
