import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// 글꼴은 npm 에서 온다. 저장소가 스스로 낸다 — 회사 망이 바깥 글꼴 서버를 막아도 조판이 산다.
import '@fontsource-variable/geist';
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css';
import '../app/globals.css';
import '../app/landing.css';
import Home from '../app/page';

createRoot(document.getElementById('root')!).render(<StrictMode><Home/></StrictMode>);
