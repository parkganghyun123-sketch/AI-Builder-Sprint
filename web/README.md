# 페어사인 프론트 (`web/`) — D 담당

Next.js(App Router) + TypeScript + Tailwind.

## 실행

```bash
cd web
npm install
npm run dev        # http://localhost:3000
```

백엔드는 별도로 띄운다 (`cd backend && uvicorn app.main:app --reload` → `http://localhost:8000`).
API 명세: http://localhost:8000/docs

환경변수는 `.env.example` → `.env.local` 복사.

기타: `npm run build`, `npm run typecheck`, `npm run lint`

## 화면 (기획서 8단계 → 라우트 8개)

| 기획서 단계 | 라우트 | 스텝 |
|---|---|---|
| 1 접속 | `/` | — |
| 2·3 업로드·추출 | `/upload` | 1 |
| 4 확인·수정 ⭐ | `/review` (`?path=B` 경로 B) | 2 |
| 5 검증 | `/result` | 3 |
| 6 수정본 생성 | `/contract` | 4 |
| 7 전자서명 | `/sign` → `/complete` | 5 |
| 8 보관 | `/archive` | 6 |

버튼 전체 정리: [`../docs/버튼_정리.md`](../docs/버튼_정리.md)

## 구조

```
app/          라우트 8개
components/   ScreenShell · ui(Button/Card/Pill) · FieldInput
              DocumentStatusBadge · CheckResultCard · LegalDisclaimer
lib/
  types.ts      backend/app/schemas.py 와 1:1 대응 ⚠️ 임의 변경 금지
  api.ts        /contracts/validate · /preview · /analyze-sign 클라이언트
  constants.ts  화면 표시용 상수 (판정 계산용 아님)
  mock.ts       ⚠️ 화면 개발용 목 데이터 — API 연결 시 교체
```

## 지켜야 할 것

- 화면의 숫자·판정·근거는 **백엔드 `ValidationReport` 반환값만**. 프론트에서 계산하지 않는다.
- 시간은 **시각**으로 다룬다 (`"09:00"`). 1일/주 근로시간은 백엔드 property가 계산한다.
- `confidence=LOW` 항목은 **노란색으로 강조**해 사용자 확인을 유도한다. `NOT_FOUND`는 "계약서에서 확인되지 않습니다"로 두고 임의 값을 채우지 않는다.
- 계약 사실과 법정 기준을 시각적으로 분리하고 "2026년 기준"을 함께 표시한다.
- 결과·서명·보관 화면에 1350 안내 문구를 고정한다.
- 서명 전 문서는 "계약서"가 아니라 **"근로조건 확인 요청서"**로 부른다.
- 모두싸인 서명 요청은 **이메일**로 보낸다 (전화번호 아님).
- 위반이 남으면 `/contracts/analyze-sign` 이 409로 막는다. 사용자가 알고 진행할 때만 `proceed_with_violations=true`.

## 남은 작업

- [ ] 입력 상태 관리(useState) → `validateTerms()` 연결
- [ ] 업로드 → `/contracts/extract` (A 담당 완료 후)
- [ ] `previewPdf()` blob 미리보기
- [ ] `analyzeAndSign()` + 409 처리 + 서명 상태 폴링
- [ ] 보관함 목록 API (C, Day 4)
- [ ] Vercel 배포
