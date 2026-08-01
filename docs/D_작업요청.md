# D 작업 요청 — 프론트 API 연결

> 2026-07-29 · 백엔드는 전 구간 동작 확인 완료.
> **화면이 붙지 않으면 A·B·C가 만든 게 심사위원에게 안 보입니다.**
> 서사 배경은 [팀_공유_0729.md](팀_공유_0729.md) (5분).

---

## 오늘의 목표 하나

**화면에서 사진 넣고 서명까지 한 번 완주.** 그 외는 전부 부차적입니다.

---

## 0. 먼저 확인

```bash
curl -s https://ai-builder-sprint-production.up.railway.app/health
```

`upstage: true`, `modusign: true` 면 백엔드는 준비된 겁니다.
응답 실물을 보고 싶으면 이걸 돌리세요 — 화면에 뭐가 오는지 그대로 나옵니다.

```bash
cd ~/AI-Builder-Sprint
set -a; source .env; set +a
python3 spikes/full_pipeline.py
```

---

## 1. `/contracts/extract` 추가 (가장 먼저)

`web/lib/api.ts` 에 이 엔드포인트만 빠져 있습니다. 파일 업로드라 `FormData` 를 씁니다.

```ts
export async function extractContract(file: File): Promise<ContractTerms> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/contracts/extract`, {
    method: "POST",
    body: form,        // ⚠️ Content-Type 을 직접 넣지 마세요. boundary 가 깨집니다
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

⚠️ **Upstage 응답에 20초쯤 걸립니다.** 로딩 표시 없으면 사용자가 멈춘 줄 압니다.

---

## 2. mock 제거 — 화면 순서대로

`upload → review → result → sign → complete`

**한 화면 끝낼 때마다 실제로 눌러보고** 다음으로 넘어가세요.
한꺼번에 바꾸면 어디서 깨졌는지 못 찾습니다.

| 화면 | 호출 |
|---|---|
| `upload` | `extractContract(file)` |
| `review` | `POST /contracts/review-items` (아래 3번) |
| `result` | `POST /contracts/validate` |
| `sign` | `POST /contracts/analyze-sign` (아래 4번) |
| `complete` | `GET /contracts/{id}/status` 폴링 |

---

## 3. review 화면 — 이 제품의 핵심

AI가 잘못 읽은 값을 사용자가 고치는 자리입니다.
**여기가 "AI는 읽기만 한다"를 눈으로 보여주는 화면입니다.**

### 3-1. `confidence` 를 직접 해석하지 마세요

`POST /contracts/review-items` 를 쓰세요. 서버가 **무엇을 왜 확인받아야 하는지**
정해서 내려줍니다.

```ts
// 요청
{ terms: ContractTerms }

// 응답
{
  items: [
    {
      field: "wage_amount",
      label: "임금 금액",
      value: "0000",
      confidence: "LOW",
      source_text: "- 시간(일, 월)급 : 시간급 금 10,000원",
      priority: "high",              // high면 서명이 막힙니다
      reasons: [
        "읽은 값이 정확한지 확신할 수 없습니다",
        "법정 기준 판정에 사용되는 항목입니다",
        "숫자를 잘못 읽어도 코드가 알아낼 수 없어 직접 확인이 필요합니다"
      ],
      affects_judgment: true,
      printed_on_contract: false
    }
  ],
  must_confirm: ["wage_amount", "wage_type", "worker_name", ...]
}
```

`reasons` 를 화면에 그대로 쓰시면 됩니다. 문구를 새로 만들 필요 없습니다.

### 3-2. 신원 항목은 체크박스가 아니라 **입력칸**으로

⚠️ **이게 가장 중요한 요청입니다.**

실측에서 AI가 `박강현` 을 `박강헌` 으로 읽었는데 **신뢰도는 HIGH** 였습니다.
값이 실존할 법한 이름이라 코드가 이상하다고 판단할 방법이 없습니다.

그런데 화면에 `박강헌` 을 미리 채워두고 "맞나요?" 라고 물으면
**사람은 웬만하면 그냥 누릅니다.** 관문이 무력해집니다.

**빈칸을 주고 직접 쓰게 하세요.** AI가 읽은 값은 옆에 참고로만 보여주고요.

```
근로자 성명

  [                    ]  ← 빈칸. 직접 입력

  AI가 읽은 값: 박강헌
  계약서 원문: (사진의 해당 위치)
```

대상: `worker_name`, `employer_name`, `employer_business_name`

### 3-3. 원본 사진을 나란히 보여주세요

⚠️ **손글씨는 `source_text` 도 AI가 읽은 결과입니다.**
`박강헌` 이 틀렸는데 근거도 `박강헌` 으로 나오면 사용자가 확인할 방법이 없습니다.

업로드한 사진을 화면 한쪽에 띄우고, 항목을 누르면 해당 위치가 보이게 하면 가장 좋습니다.
그게 어려우면 **사진 전체라도 옆에 띄워주세요.** 없는 것보다 훨씬 낫습니다.

### 3-4. 표시 규칙

| 상태 | 화면 |
|---|---|
| `priority: "high"` | 강조. **확인 전까지 다음 단계 버튼 비활성** |
| `confidence: "LOW"` | 주의 표시 |
| `confidence: "NOT_FOUND"` | 빈칸 + 입력 유도 |

모든 항목은 수정 가능해야 합니다.

---

## 4. 409 처리 — 세 가지입니다

`analyze-sign` 이 막는 경우가 셋입니다. `detail.code` 로 구분하세요.

### `UNCONFIRMED_FIELDS`

```json
{
  "code": "UNCONFIRMED_FIELDS",
  "message": "확인이 필요한 항목이 남아 있습니다.",
  "fields": ["임금 금액", "근로자 성명"]
}
```

→ review 화면으로 되돌리고, 확인 마친 뒤 `confirmed_fields` 에 담아 재요청.

```ts
{ ...body, confirmed_fields: ["wage_amount", "worker_name", ...] }
```

### `NAME_MISMATCH`

```json
{
  "code": "NAME_MISMATCH",
  "conflicts": [
    { "label": "근로자 성명", "on_contract": "박강헌", "typed": "박강현" }
  ]
}
```

→ **두 값을 나란히 보여주고 사용자가 고르게 하세요.**
어느 쪽이 맞는지 서버는 모릅니다. AI가 잘못 읽었을 수도, 입력이 잘못됐을 수도,
계약서에 정말 다른 이름이 적혀 있었을 수도 있습니다.

### code 없음 = 법정 기준 위반

```json
{
  "message": "법정 기준에 미달하거나 누락된 항목이 있습니다.",
  "problems": ["최저임금", "주휴 시간 요건·주휴일"]
}
```

→ 위반 화면 → "알고도 진행" 선택 시 `proceed_with_violations: true` 로 재요청.

**이게 데모의 하이라이트입니다.** 그냥 통과시키지 마세요.

---

## 5. "말 꺼내기" 문구 — 우리 차별점

`POST /contracts/message` 로 판정 결과를 사장님께 보낼 문구로 바꿉니다.

```json
{
  "message": "사장님, 안녕하세요. 계약서 다시 보다가...",
  "lines": ["계약서에 적힌 시급이 10,000원인데...", "..."],
  "numbers_verified": true
}
```

위반이 없으면 `message` 가 `null` 입니다. 그때는 카드를 띄우지 마세요.

**복사 버튼 필수.** 사용자가 카카오톡에 붙여넣어야 의미가 있습니다.
`lines` 를 쓰면 항목별로 나눠 보여줄 수도 있습니다.

> 대회 주제가 "AI로 인간다움을 표현" 입니다. 이 화면이 거기에 정면으로 꽂힙니다.
> 잘 보이게 만들어주세요.

---

## 6. archive(보관함) — 서사의 마지막 장면

**"원래 사장님만 갖고 있던 계약서를 양쪽이 갖게 된다"** 를 보여주는 화면입니다.
근로기준법 제17조 교부 의무가 여기서 완성됩니다.

### 로그인도 DB도 필요 없습니다

서명 요청이 성공하면 받은 `document_id` 를 **브라우저에 저장**하고,
보관함에서 그 목록을 읽어 각각 상태를 조회하면 됩니다.

```ts
// 서명 요청 성공 직후
const saved = JSON.parse(localStorage.getItem("fairsign:contracts") ?? "[]");
saved.unshift({
  id: result.document_id,
  title: `근로계약서_${workerName}`,
  createdAt: new Date().toISOString(),
});
localStorage.setItem("fairsign:contracts", JSON.stringify(saved));
```

```ts
// 보관함 화면
const saved = JSON.parse(localStorage.getItem("fairsign:contracts") ?? "[]");
const rows = await Promise.all(
  saved.map((c) => fetch(`${BASE}/contracts/${c.id}/status`).then((r) => r.json()))
);
```

`GET /contracts/{id}/status` 가 이미 필요한 걸 다 줍니다.

```json
{
  "document_id": "...",
  "status": "COMPLETED",
  "signed": 2,
  "total": 2,
  "download_url": "https://...",   // COMPLETED일 때만. 10분 유효
  "cors_origins": []
}
```

⚠️ **`download_url` 은 유효시간 10분입니다.** 저장하지 말고 화면 열 때마다 조회하세요.

**백엔드는 추가 개발이 없습니다.** 기존 엔드포인트로 끝납니다.

---

## 우선순위

시간이 부족하면 아래에서부터 버리세요.

| 순위 | 항목 | 이유 |
|---|---|---|
| 1 | `extract` 연결 + upload 화면 | 여기 막히면 아무것도 안 보임 |
| 2 | review 화면 (3-1, 3-2) | 제품의 핵심 |
| 3 | result + sign + 409 처리 | 완주에 필요 |
| 4 | archive 보관함 | 서사의 결론. 30분 |
| 5 | 말 꺼내기 문구 카드 | 차별점이지만 30분이면 붙음 |
| 6 | 원본 사진 나란히 보기 (3-3) | 있으면 좋음 |
| 7 | 경로 B 직접 입력 폼 | 이번엔 버려도 됨 |

---

## 막히면

C에게 바로 물어보세요. **D가 막히는 게 팀 전체가 막히는 것**이라
C는 본인 작업보다 이걸 우선합니다.

CORS 에러가 나면 `/health` 의 `cors_origins` 부터 확인하세요.
`localhost:3000` 과 `127.0.0.1:3000` 은 항상 허용돼 있습니다.
