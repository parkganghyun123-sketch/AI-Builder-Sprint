# FairSign 프론트엔드

Next.js(App Router), TypeScript, Tailwind로 만든 모바일 우선 웹입니다. 계약서
파일 추출부터 조건 확인, 백엔드 검증, PDF 미리보기, 모두싸인 요청과 상태 조회까지
실제 백엔드 API에 연결합니다.

## 로컬 실행

Node.js `18.18` 이상이 필요합니다. 프로젝트 검증에는 bundled Node 24를
사용했습니다.

백엔드를 먼저 실행합니다.

```bash
cd backend
python -m uvicorn app.main:app --reload
```

프론트 환경변수와 의존성을 준비한 뒤 실행합니다.

```bash
cd web
cp .env.example .env.local
npm install
npm run dev
```

기본 주소는 프론트 `http://localhost:3000`, 백엔드
`http://localhost:8000`입니다. 실제 환경변수를 담은 `.env.local`은 커밋하지
않습니다.

배포된 Railway 백엔드를 사용할 때는 `.env.local`을 다음처럼 설정합니다.

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://ai-builder-sprint-production.up.railway.app
```

## 연결된 흐름

| 라우트 | 실제 동작 |
|---|---|
| `/upload` | JPG·PNG·PDF를 `POST /contracts/extract`로 전송 |
| `/review` | AI 추출값 또는 직접 입력값 23개를 확인·수정하고 `POST /contracts/validate` 호출 |
| `/result` | 백엔드 `ValidationReport`만 표시 |
| `/contract` | `POST /contracts/preview` PDF를 메모리 URL로 미리보기·다운로드 |
| `/sign` | `POST /contracts/analyze-sign`, 409 확인 후 명시적 재요청 |
| `/complete` | `GET /contracts/{id}/status`를 폴링하고 실제 완료 상태와 다운로드 주소 표시 |
| `/archive` | 보관 API가 없어 `준비 중`만 표시 |

계약 조건·검증 결과·서명 문서 ID는 현재 브라우저 탭의 `sessionStorage`에만
저장합니다. 업로드한 파일 원본과 PDF Blob은 브라우저 저장소에 넣지 않습니다.
서버의 파일 보관·삭제 정책은 아직 검증되지 않았으므로 자동 삭제를 보장하지
않습니다.

## API 안전 규칙

- 외부 JSON 응답은 `lib/schemas.ts`의 Zod 스키마로 검증합니다.
- 판정과 금액 계산은 프론트에서 하지 않습니다.
- 409 응답을 우회하지 않고, 사용자가 확인 체크를 한 재요청에서만
  `proceed_with_violations=true`를 보냅니다.
- 오류 메시지와 콘솔에 파일 내용, 추출 원문, 이름, 이메일을 남기지 않습니다.
- `COMPLETED`는 상태 API가 해당 값을 반환했을 때만 표시합니다.
- 보관함은 실제 API가 연결되기 전까지 저장 기능처럼 표시하지 않습니다.

## 검사

```bash
cd web
npm run typecheck
npm run lint
npm run build
npm audit --omit=dev
```
