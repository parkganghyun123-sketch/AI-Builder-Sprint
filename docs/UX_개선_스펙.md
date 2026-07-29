# UX 개선 스펙 — 진행 차단 · 단계 이동 · 업로드

> 2026-07-29 · 백엔드는 구현 완료. 프론트는 이 문서대로 붙이면 된다.
> **`web/` 파일은 D가 작업 중이라 C가 직접 고치지 않았다.** 충돌을 피하기 위해서다.

---

## 1단계: 현황 분석 결과

### 화면 흐름

```
upload → review → result → contract → sign → complete → archive
```

상태는 `web/lib/session.ts` 가 `sessionStorage` 에 저장한다.
새로고침·뒤로가기에도 값이 유지된다. **이 부분은 이미 잘 되어 있다.**

### 확인된 버그

| # | 문제 | 재현 | 심각도 |
|---|---|---|---|
| 1 | **시급 `0000` 으로 PDF가 생성된다** | review에서 시급 0000 → contract 화면 → PDF 나옴 | **P0** |
| 2 | 0원을 "최저임금 미달"로 안내 | 위와 동일 | **P0** |
| 3 | 진행 차단이 없다 | 어느 화면에서도 "다음" 이 막히지 않음 | **P0** |
| 4 | 오류를 개수로만 표시 | "확인할 항목 5건" — 어디를 왜 고쳐야 하는지 없음 | P1 |
| 5 | `review-items` 미사용 | `confidence` 를 화면이 직접 해석 → HIGH로 틀린 값 통과 | P1 |
| 6 | 뒤로 가기 버튼 없음 | 브라우저 뒤로가기만 가능 | P1 |
| 7 | 드래그 앤 드롭 없음 | 파일 선택 버튼만 있음 | P2 |
| 8 | 원본 사진을 안 보여줌 | 손글씨는 `source_text` 도 AI가 읽은 것이라 대조 불가 | P1 |

**1~3번이 같은 뿌리다.** 값 자체의 유효성과 법정 기준 판정을 구분하지 않았다.

---

## 2단계: 백엔드에 구현한 것

### `POST /contracts/validation-state`

**프론트는 이것만 보고 버튼을 켜고 끈다.** 같은 규칙을 화면에 복사하지 말 것.

```ts
// 요청
{ terms: ContractTerms, worker_birth_date?: string | null }

// 응답
{
  can_proceed: false,
  blocking_fields: ["wage_amount"],
  counts: { error: 1, warning: 1, info: 0 },
  issues: [
    {
      field: "wage_amount",
      label: "임금 금액",
      severity: "error",          // error / warning / info
      value: "0000",              // 문제가 된 현재 값
      reason: "임금이 0원입니다. 무상 근로 계약은 성립하지 않습니다.",
      fix: "계약서에 적힌 실제 금액을 확인해 입력해 주세요.",
      blocks: true,               // 다음 단계를 막는가
      step: "review",             // 어느 화면에서 고치나
      source: "input"             // input(값 자체) / legal(법정 기준)
    }
  ]
}
```

`reason` 과 `fix` 를 화면에 그대로 쓰면 된다. 문구를 새로 만들 필요 없다.

### 차단 기준 — 값과 판정을 구분한다

| 상황 | severity | 진행 | 이유 |
|---|---|---|---|
| 임금 `0`, `0000`, 빈값, 음수, 문자 | **error** | 🚫 차단 | 계약으로 성립하지 않는다 |
| 임금 `50` (자릿수 오류 의심) | **error** | 🚫 차단 | 시급 하한 1,000원 미만 |
| 시각이 `25:00` | **error** | 🚫 차단 | 근로시간 계산이 전부 틀어진다 |
| 주 근무일 `0` 또는 `9` | **error** | 🚫 차단 | 불가능한 값 |
| 필수 항목 누락 | **error** | 🚫 차단 | 계약서가 성립 안 됨 |
| **최저임금 미달** | **warning** | ✅ 가능 | 사실이다. 알고도 진행할 수 있어야 한다 |
| 주휴일 누락 | **warning** | ✅ 가능 | 판정이 이미 누락으로 잡는다 |
| 임금이 범위 상한 초과 | warning | ✅ 가능 | 임금 형태를 잘못 골랐을 수 있다 |

⚠️ **최저임금 미달을 차단하지 않는 이유.**
그건 이 서비스가 발견하려는 바로 그 문제다. 막아버리면 사용자가
"계약서를 못 만드는" 상태가 되고, 사장님과 협의할 근거도 못 만든다.
대신 무엇을 무시하고 진행하는지 명확히 보여준다.

### 서버 측 재검증

프론트 검증은 우회할 수 있다. 그래서 **문서를 만드는 모든 경로에서 다시 본다.**

| 엔드포인트 | 차단 |
|---|---|
| `POST /contracts/preview` | **422 `INVALID_CONTRACT_VALUES`** ← 새로 추가 |
| `POST /contracts/analyze-sign` | 422 + 기존 409 세 가지 |

API를 직접 호출해도 0원짜리 계약서는 만들어지지 않는다.

---

## 3단계: 프론트에서 할 일

### P0-1. 진행 차단 (가장 급함)

각 화면의 "다음" 버튼을 `can_proceed` 로 제어한다.

```ts
const state = await fetch(`${BASE}/contracts/validation-state`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ terms, worker_birth_date: birthDate }),
}).then((r) => r.json());

<Button disabled={!state.can_proceed}>다음</Button>
```

**비활성화된 이유를 반드시 보여줄 것.** 버튼만 회색이면 사용자는 멈춘다.

```
다음 단계로 갈 수 없습니다
  🚫 임금 금액 — 임금이 0원입니다. 무상 근로 계약은 성립하지 않습니다.
     → 계약서에 적힌 실제 금액을 확인해 입력해 주세요.  [고치러 가기]
```

### P0-2. 오류 요약 → 해당 필드로 이동

`issues` 를 목록으로 띄우고, 클릭하면 해당 입력란으로 스크롤 + 포커스.

```ts
function focusField(field: string) {
  const el = document.querySelector<HTMLElement>(`[data-field="${field}"]`);
  el?.scrollIntoView({ behavior: "smooth", block: "center" });
  el?.focus();
}
```

입력란에 `data-field={name}` 만 달아두면 된다.

### P0-3. 값 수정 시 즉시 재계산

`onChange` 마다 호출하면 요청이 쏟아진다. **입력이 멈춘 뒤 400ms** 정도 두고 부른다.

### P1-1. `review-items` 연결

지금 화면이 `confidence` 를 직접 해석하고 있어서 **`박강헌` 처럼 HIGH로 틀린 값이 그냥 통과**한다.
`POST /contracts/review-items` 로 바꾸면 임금·신원 5개가 확인 대상으로 잡힌다.

상세는 [D_작업요청.md](D_작업요청.md) 3-1 참고.

### P1-2. 뒤로 가기

각 화면 좌상단에 이전 단계 버튼. 상태는 이미 `sessionStorage` 에 있어 값이 유지된다.

**이미 지나온 단계는 스텝 인디케이터에서 직접 클릭 가능하게 해도 된다.**
아직 안 간 단계는 막는다 — 순서가 의미를 갖기 때문이다(확인 없이 판정하면 안 됨).

```tsx
<StepIndicator
  current="review"
  visited={["upload", "review"]}   // 클릭 가능
  onNavigate={(step) => router.push(`/${step}`)}
/>
```

브라우저 뒤로가기와 충돌하지 않는다. Next.js `router.push` 가 히스토리를 쌓으므로
브라우저 뒤로가기도 같은 순서로 동작한다.

### P1-3. 원본 사진 나란히 보기

**손글씨에서는 `source_text` 도 AI가 읽은 결과다.** 사진이 없으면 대조가 불가능하다.
업로드한 파일을 `URL.createObjectURL` 로 review 화면에 띄운다.

⚠️ 사진은 `sessionStorage` 에 넣지 말 것 (용량 초과). 메모리에만 두고,
새로고침하면 "사진 다시 올리기" 버튼을 보여준다.

### P2-1. 드래그 앤 드롭

```tsx
const [dragging, setDragging] = useState(false);

<div
  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
  onDragLeave={() => setDragging(false)}
  onDrop={(e) => {
    e.preventDefault();
    setDragging(false);
    handleFile(e.dataTransfer.files[0]);   // ← drop 에서만 업로드
  }}
  onClick={() => inputRef.current?.click()}
  className={dragging ? "border-blue-500 bg-blue-50" : "border-gray-300"}
>
```

⚠️ **`onDragOver` 에서 업로드하지 말 것.** 파일을 올려놓기만 해도 업로드되면
의도치 않은 업로드가 생긴다. `onDrop` 에서만 처리한다.
`onDragOver` 는 **시각적 강조만** 담당한다.

함께 넣을 것: 미리보기, 파일명·크기, 형식·용량 안내, 취소·교체,
형식/용량 오류 메시지, 모바일 `capture="environment"`, 중복 업로드 방지, 실패 시 재시도.

### P2-2. 최종 검토 화면

`contract` 화면을 최종 검토로 쓰면 된다. 새 화면을 만들 필요 없다.

- 당사자 정보 · 핵심 조건 요약
- `issues` 목록 (error / warning 구분)
- 각 항목 "고치러 가기"
- PDF 미리보기
- **차단 오류가 있으면 생성 버튼 비활성 + 이유 표시**
- "미리보기와 서명본의 차이" 한 줄 안내

---

## 4단계: 검증 방법

### 백엔드 (완료)

```bash
cd backend && source .venv/bin/activate && python -m pytest -q
```

`app/validation/tests/test_severity.py` 21개가 이 기준을 고정한다.

### API 우회 차단 확인

```bash
# 0원짜리로 PDF 생성 시도 → 422 여야 한다
curl -s -X POST https://ai-builder-sprint-production.up.railway.app/contracts/preview \
  -H 'Content-Type: application/json' \
  -d '{"terms": {... "wage_amount": {"value": "0000", "confidence": "HIGH"} ...}}' \
  | head -5
```

### 프론트 (D가 확인)

- 시급 `0`, `0000`, 음수, 문자, 빈값 → 다음 버튼 비활성
- 최저임금 미달만 있는 경우 → 진행 가능하되 무시 항목 표시
- 오류 클릭 → 해당 입력란으로 이동·포커스
- 값 수정 → 오류 즉시 사라짐
- 뒤로 갔다 와도 입력값 유지
- 새로고침 후 복구
- 드래그 앤 드롭 / 잘못된 형식 / 용량 초과
- 중복 클릭으로 PDF 두 번 생성 안 되는지
- 키보드만으로 조작 · 스크린리더 오류 안내

---

## 평가하고 **넣지 않은** 것

해커톤 일정 기준으로 판단했다. 필요하면 다시 논의.

| 항목 | 판단 |
|---|---|
| 자동 임시저장 API | `sessionStorage` 로 충분. 서버 저장은 개인정보 책임이 생긴다 |
| 이탈 전 경고 (`beforeunload`) | 넣을 만하다. 30분. **P2** |
| 문서 버전 관리 | 계약서를 서버에 저장하지 않으므로 해당 없음 |
| 멱등성 키 | 중복 클릭은 프론트에서 버튼 비활성으로 막는 게 싸다 |
| 다크 모드 | 이번 대회 범위 아님 |
| 다국어 | 외국인 근로자 확장 시 필요. 지금은 아님 |
| 감사 로그 | 실서비스 요건. 데모에는 과함 |
| 권한 분리 | 로그인이 없으므로 해당 없음 |
| 최저임금 연도별 버전 관리 | `constants.py` 에 2026년 값 상수로 있음. 다년 지원은 후속 |

**최저임금 시점별 기준값**만 짚어둔다. 지금은 2026년 값 하나뿐인데,
계약 시작일이 2025년이면 그 해 기준을 써야 맞다. 실서비스에서는 필요하지만
이번 데모는 2026년 계약만 다루므로 후속으로 둔다.
