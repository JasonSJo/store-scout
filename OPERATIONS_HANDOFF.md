# 스스닷컴: 디자인·설계 / 운영 인수인계

## 담당
- Codex: 디자인 시스템, 화면 UX, 기능 설계·구현, 테스트 및 변경 문서 작성.
- Claude: 변경 검토, 사용자 승인에 따른 배포, 환경변수·도메인·모니터링·백업·장애 대응.
- 사용자: 외부 데이터 사용권, 유료 계약, 운영 배포 승인과 사업 정책 결정.

이는 사용자가 정한 협업 분담입니다. Claude에게 메시지를 보내거나 자동 운영을 시작한 것은 아닙니다. 운영자는 이 문서와 변경 diff를 확인한 뒤 작업합니다. 운영 비밀키·고객 정보를 대화나 Git에 출력하지 않습니다.

## 이번 변경
대상은 JasonSJo/stores-scout 저장소의 web/ (Vite 정적 공개 페이지)입니다.
상담 확인 화면에 카카오맵과 명시적인 매물 미연동 안내를 추가했습니다.
현재 전달 좌표는 빈 배열이며 전국 개요 지도만 표시합니다. 고객 이름·전화·거주/근무 주소를 지도에 넘기지 않고 주소 자동 지오코딩도 하지 않습니다. 매물 공급원·백엔드 매물 검색을 새로 연결한 것이 아닙니다.
지도 컴포넌트는 향후 매물 마커 선택, 좌표 위치 지정, 범위 맞춤을 지원하지만 실제 매물 연결은 별도 변경입니다.

기존 chatgpt.site용 work/store-scout 프로젝트와 이 저장소는 다릅니다. 그 프로젝트의 MCP/파일 가져오기/회사 매물 API는 이번 변경으로 이식되지 않았습니다. NEXT_PUBLIC_ 환경변수도 Vite에서 사용하지 않습니다.

## Claude 운영 순서
1. 이 변경 브랜치를 검토합니다. main으로 병합하면 deploy-pages.yml이 자동 실행됩니다. 운영 배포 시점을 승인받기 전 main에 병합하지 않습니다. Fly 백엔드 배포는 불필요합니다.
2. GitHub 저장소 Settings → Secrets and variables → Actions에 KAKAO_MAP_JS_KEY를 설정합니다. 사용자가 기존 로컬 .env에 넣은 NEXT_PUBLIC_KAKAO_MAP_JS_KEY와 같은 **JavaScript 키**를 안전하게 옮깁니다. 본 변경은 GitHub secret을 설정하지 않았습니다.
3. 카카오 SDK 도메인: https://stores-scout.com . github.io로 접근할 때는 https://jasonsjo.github.io 도 등록합니다. github.com 저장소 URL을 SDK 도메인으로 넣지 않습니다.
4. 카카오 지도 사용 설정/이용량을 확인합니다. JavaScript 키는 빌드 후 브라우저에 노출되는 공개 식별자입니다. REST/Admin 키와 다른 비밀키는 절대 VITE_ 변수에 넣지 않습니다.
5. `cd web && npm ci && npm run typecheck && npm run test:map && npm run build`를 수행합니다. 로컬에서는 web/.env.local의 VITE_KAKAO_MAP_JS_KEY를 사용합니다.
6. 사용자 승인 후 병합하여 Pages 배포. 상담에 가상 정보를 입력하고 결과에서 카카오 배경·로고·확대/축소 및 모바일 크기를 확인합니다. 실제 등록 매물이 없으므로 빈 지도는 정상이며 실시간 매물이 뜬다고 안내하지 않습니다.
7. 키 미설정/네트워크 오류에서도 조건 요약과 CSV 다운로드가 정상인지 확인합니다. 원본 고객 정보를 테스트로 저장하거나 전달하지 않습니다.

## 미검증 및 롤백
- 실제 키/도메인 조합에서 SDK 로딩은 운영 브라우저 검증이 필요합니다. 모의 테스트는 카카오 서버 접속 성공을 증명하지 않습니다.
- 기존 Pages base 설정 /store-scout/와 저장소 이름 stores-scout의 차이는 기존 설정입니다. 이번에는 변경하지 않았습니다. CNAME 사용 시 base=/ 인지 운영자가 점검합니다.
- 실패 시 운영자가 이 변경을 revert하고 이전 정상 Pages 버전을 재배포합니다. SQLite 백엔드나 DB 마이그레이션은 변경하지 않았습니다.

공식 SDK 안내: https://apis.map.kakao.com/web/guide/
