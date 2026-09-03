/* 정적 빌드. Vinext·Cloudflare Worker 구성을 걷어냈다 — GitHub Pages 는 정적 파일만
   받는다. 두 쪽짜리 사이트라 라우터를 두지 않고 진짜 HTML 두 장으로 낸다. */
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';
import { resolve } from 'node:path';

// 저장소 Pages 는 /stores-scout/ 아래에 놓인다. 사용자 도메인을 붙이면 '/' 로 준다.
//   STORE_SCOUT_BASE=/ pnpm build
const base = process.env.STORE_SCOUT_BASE || '/stores-scout/';

export default defineConfig({
  base,
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('.', import.meta.url)) },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        home: resolve(fileURLToPath(new URL('.', import.meta.url)), 'index.html'),
        consultation: resolve(fileURLToPath(new URL('.', import.meta.url)), 'consultation/index.html'),
      },
    },
  },
});
