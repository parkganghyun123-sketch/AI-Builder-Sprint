# 팀 작업 지시 — Day 1 밤 ~ Day 2

작성: 팀장(C) · 2026-07-27

---

## 오늘까지 확정된 것

| 항목 | 결정 |
|---|---|
| 주제 | **페어사인** — 알바 근로계약서 검증 → 수정 → 전자서명 |
| 스택 | **Python FastAPI(백엔드) + Next.js(프론트)** |
| 모두싸인 | ✅ **API 승인 완료, 인증 테스트 성공** |
| Upstage | ✅ 키 발급 완료 (3종 공용 키 1개) |
| 백엔드 뼈대 | ✅ 푸시 완료 — `develop` 브랜치 |

**⭐ 모두가 가장 먼저 읽을 파일: `backend/app/schemas.py`**
여기가 우리 팀의 인터페이스 계약서입니다. 이 파일만 보고 각자 작업하면 붙일 때 안 깨집니다.

---

## Day 2 팀 전체 목표 (하나)

```
python make_test_pdf.py 대신,
실제 계약서 사진 1장 → 판정 결과 JSON 이 CLI에서 끝까지 나온다
```

화면은 없어도 됩니다. 이게 되면 Day 3 프로토타입 배포가 자연히 따라옵니다.

---

# A 담당 — AI 파이프라인 (Upstage)

## 지금 당장 (오늘 밤 or 내일 오전 첫 작업)

### 1. 환경 세팅
```bash
git checkout develop && git pull
cd backend
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload   # 뜨는지 확인
```
키는 제가 따로 전달합니다. `.env`에 `UPSTAGE_API_KEY` 넣으세요.

### 2. `app/schemas.py`의 `ContractTerms` 정독
**여기 필드명이 곧 Information Extract 스키마입니다.** 임의로 바꾸지 말고, 바꿔야겠다 싶으면 B와 저에게 먼저 말씀해주세요.

## Day 2 작업

### 작업 1. Document Parse 호출 (`app/ai/document_parse.py`)
- 입력: 계약서 이미지/PDF 바이트
- 출력: 텍스트 + 표 구조
- **Standard 모드로 시작하세요.** Enhanced($0.03)는 Standard($0.01)가 실패하는 케이스를 확인한 뒤에.

### 작업 2. Information Extract 스키마 설계 (`app/ai/extract.py`)
`ContractTerms` 필드에 1:1로 대응하는 추출 스키마를 만드세요.

**⚠️ 가장 중요한 주의사항 — 시간은 "시각"으로 뽑으세요**

실제 표준근로계약서에는 "1일 6시간"이라고 안 적혀 있습니다. **"09시 00분부터 16시 00분까지 (휴게시간 12시~12시30분)"** 형태로 적혀 있습니다.

| ❌ 이렇게 뽑지 마세요 | ✅ 이렇게 뽑으세요 |
|---|---|
| `hours_per_day: 6` | `work_start_time: "09:00"` |
| `break_minutes: 30` | `work_end_time: "16:00"` |
| | `break_start_time: "12:00"` |
| | `break_end_time: "12:30"` |

1일 근로시간·휴게시간·주 소정근로시간은 **`schemas.py`의 property가 자동 계산**합니다. AI가 계산하면 안 됩니다.

**추출할 필드 전체** (표준양식 항목 순서)
```
1. contract_start, contract_end          근로계약기간
2. workplace                             근무장소
3. job_description                       업무의 내용
4. work_start_time, work_end_time        소정근로시간 (시각)
   break_start_time, break_end_time      휴게시간 (시각)
5. work_days_per_week                    매주 ○일 근무
   weekly_holiday_day                    주휴일 매주 ○요일  ← 없으면 NOT_FOUND
6. wage_type                             HOURLY / DAILY / MONTHLY
   wage_amount                           금액
   has_bonus, other_allowance            상여금·기타급여
   payday, payment_method                지급일·지급방법
   employer_business_name, employer_phone, employer_address, employer_name
   worker_address, worker_contact, worker_name
```

### 작업 3. `ExtractedField` 채우기
각 값을 그냥 넣지 말고 **3종 세트**로 채워주세요.

```python
ExtractedField(
    value="10000",
    confidence=Confidence.HIGH,        # HIGH / LOW / NOT_FOUND
    source_text="시간급 금 10,000원",   # ← 계약서 원문 근거
)
```

- `confidence=LOW` → 프론트가 노란색으로 강조해 사용자 확인을 유도합니다
- `source_text` → **챗봇 답변 카드의 "📄 계약서 근거"가 여기서 나옵니다.** 반드시 채워주세요
- 못 찾은 필드는 `NOT_FOUND`로. **추측해서 채우면 안 됩니다**

### 작업 4. fixture 저장 (⭐ 비용·시간 절약)
같은 계약서로 코드 고칠 때마다 API를 다시 부르면 대기시간이 낭비됩니다.

```
spikes/fixtures/
  ├─ contract_01_parse.json      # DP 응답 그대로 저장
  └─ contract_01_extract.json    # IE 응답 그대로 저장
```

**이 fixture가 나중에 평가 데이터셋 = 예선 제출물 "AI 활용 증빙"이 됩니다.** 버리지 마세요.

### 작업 5. 평가셋 준비 시작
- 정상 계약서 5종 + **위반을 심은 변형 5종** (시급을 최저임금 미만으로, 주휴일 칸을 비우고 등)
- 각 문서의 정답 라벨을 손으로 적어두기
- Day 5에 이걸로 추출 정확도를 숫자로 뽑습니다

## Day 2 완료 기준
- [ ] 계약서 사진 1장 → `ContractTerms` 객체 출력 성공
- [ ] 핵심 4필드(시급·근로시간·휴게·계약기간) 추출률 확인 (숫자로)
- [ ] fixture 최소 3건 저장
- [ ] `python -c "from app.ai.extract import extract; print(extract('샘플.jpg'))"` 가 돈다

## 막히면
- 추출률이 60% 미만 → **저에게 바로 말씀해주세요.** 수동 입력 중심으로 설계를 바꿔야 합니다
- 표(table) 구조가 안 잡힘 → Enhanced 모드 1건만 테스트해보고 차이 보고
- 비용 걱정은 안 하셔도 됩니다 ($70 = 약 1,300건)

## 저에게 요청할 것
- Upstage 키 (오늘 밤 DM)
- 실계약서 샘플이 필요하면 말씀하세요 (제 것 마스킹해서 드립니다)

---

# B 담당 — 검증 엔진

## 지금 당장

### 1. 환경 세팅 (A와 동일)

### 2. `app/schemas.py`의 `ValidationReport` 정독
당신의 출력물 형식입니다.

## Day 2 작업

### 작업 1. 법정 기준 상수 (`app/validation/constants.py`)
```python
MINIMUM_WAGE_2026 = 10_320          # 원/시간
WEEKLY_HOLIDAY_MIN_HOURS = 15       # 주 소정근로시간 기준
BREAK_RULES = [                     # (근로시간 이상, 최소 휴게 분)
    (8, 60),
    (4, 30),
]
```
출처를 주석으로 함께 남겨주세요. 발표 때 근거로 씁니다.

### 작업 2. 검증 함수 (`app/validation/rules.py`) — ⭐ 우리 서비스의 심장

**절대 규칙: 이 파일에서 LLM을 호출하지 마세요.** 판정을 코드가 한다는 게 우리가 ChatGPT와 다른 점의 전부입니다. 여기에 LLM이 들어가는 순간 프로젝트의 차별점이 사라집니다.

```python
def check_minimum_wage(terms: ContractTerms) -> CheckResult: ...
def check_weekly_holiday(terms: ContractTerms) -> CheckResult: ...
def check_break_time(terms: ContractTerms) -> CheckResult: ...
def check_required_fields(terms: ContractTerms) -> list[CheckResult]: ...

def validate(terms: ContractTerms) -> ValidationReport: ...
```

각 함수는 **순수 함수**로 (외부 호출·전역 상태 없음). 그래야 테스트가 쉽습니다.

### ⚠️ 주휴수당 — 여기가 가장 조심할 부분

공식 확인 결과 주휴수당 발생 요건은 **3가지**입니다.

1. 근로기준법상 근로자
2. **4주 평균 1주 소정근로시간 15시간 이상**
3. **1주 소정근로일 개근**

**계약서로 확인 가능한 건 2번뿐입니다.** 3번(개근)은 계약서에 없습니다.

| ❌ 절대 이렇게 쓰지 마세요 | ✅ 이렇게 쓰세요 |
|---|---|
| "주휴수당 대상입니다" | "주휴수당 지급 요건 중 **시간 요건을 충족**합니다. 실제 지급은 소정근로일 개근 여부에 따라 결정됩니다." |

그리고 판정 대상은 "주휴수당 조항 유무"가 아니라 **`weekly_holiday_day`(주휴일 요일) 지정 여부**입니다. 표준양식 5번 항목에 `주휴일 매주 ○요일`로 들어가 있어서요. 비어 있으면 `MISSING`.

### ⚠️ 최저임금 — 월급·일급은 판정하지 마세요

`terms.hourly_wage` property는 **시간급으로 기재된 경우에만** 값을 냅니다. 월급을 시급으로 환산하는 건 소정근로시간 산정 방식에 따라 달라져서, 잘못 계산하면 최저임금 판정이 틀립니다.

월급·일급이면 `CheckStatus.UNKNOWN` + "시간급으로 기재된 계약만 판정합니다" 안내로 처리하세요.

### 작업 3. `CheckResult` 채우기 — 근거 필수
```python
CheckResult(
    code="MINIMUM_WAGE",
    label="최저임금",
    status=CheckStatus.VIOLATION,
    legal_basis="최저임금법 · 2026년 최저임금 고시",
    standard_year=2026,
    calculation="시급 10,000원 < 최저임금 10,320원 (월 약 25,000원 차이)",
    detail=None,
)
```

**`legal_basis`와 `calculation`은 반드시 채우세요.** 이게 답변 카드의 "⚖️ 법령 근거", "🧮 계산"으로 화면에 그대로 나갑니다. 근거 없는 판정은 우리 서비스에 존재하면 안 됩니다.

### 작업 4. 단위 테스트 (`app/validation/tests/`)
**경계값을 반드시 테스트하세요.**

```
- 시급이 정확히 10,320원 → OK (미달 아님)
- 시급 10,319원 → VIOLATION
- 주 소정근로시간 정확히 15시간 → 시간요건 충족
- 14.9시간 → 미충족
- 6시간 근무에 휴게 30분 → OK
- 8시간 근무에 휴게 30분 → VIOLATION (60분 필요)
- 값이 None인 경우 → UNKNOWN (에러로 죽지 않을 것)
```

**이 테스트 결과가 예선 제출물 "검증 산출물"이 됩니다.** `pytest -v` 출력을 캡처해두세요.

## Day 2 완료 기준
- [ ] `validate(terms)` → `ValidationReport` 반환
- [ ] `pytest` 10개 이상 통과
- [ ] A의 출력을 실제로 받아 판정까지 CLI로 완주

## 저에게 요청할 것
- A와 스키마 해석이 갈리면 즉시 알려주세요 (제가 중재합니다)
- 공공데이터 API로 최저임금을 가져올지는 제가 확인 중입니다. 일단 **상수로 하드코딩**하세요

---

# D 담당 — 프론트 + 사용자 검증

## ⭐ 오늘 밤 안에 해야 할 것 (가장 중요)

### 알바 경험자 5명 인터뷰

**이게 오늘 팀 전체에서 가장 가치 있는 작업입니다.** 결과에 따라 주제를 바꿀 수도 있습니다.

**진행 원칙**
- 우리 서비스 설명은 **맨 마지막에**. 먼저 설명하면 다 "좋다"고 합니다
- 유도 질문 금지. "불편하셨죠?" ❌ → "어떻게 하셨어요?" ⭕
- 답변을 **그대로** 받아적으세요. 요약하면 발표에 쓸 인용문이 사라집니다

**질문 (순서대로)**
1. 최근 알바에서 근로계약서를 받으셨나요? 언제 받으셨어요?
2. 받으셨다면 읽어보셨나요? 그때 뭐가 궁금하거나 걸리셨어요?
3. 급여가 예상과 달랐던 적 있으세요? 그때 어떻게 하셨어요?
4. 서명하기 전에 확인해보고 싶었던 적 있으세요? 있다면 어떻게 하셨어요?
5. 계약서를 못 받으셨다면 — **사장님께 먼저 "계약서 써요"라고 말할 수 있으셨을까요?**
6. 계약서 사진을 앱에 올리는 건 어떠세요? 걱정되는 점 있나요?

**5번이 특히 중요합니다.** 여기서 "못 한다"가 많이 나오면 구두계약 경로(경로 B)를 사장님이 시작하는 방식으로 뒤집어야 합니다.

**판정 기준**
- 5명 중 3명 이상이 "확인하고 싶었다" → 주제 확정, 그대로 진행
- 5명 중 4명 이상이 "문제 겪은 적 없고 안 쓸 것 같다" → **저에게 즉시 연락.** 주제 전환 논의

## Day 2 작업

### 작업 1. Next.js 프로젝트 세팅
```bash
npx create-next-app@latest web --typescript --tailwind --app
cd web && npx shadcn@latest init
```
`web/` 디렉터리에 만드세요. **컴포넌트를 직접 만들지 마세요** — shadcn 붙여넣기로 하루를 아낍니다.

### 작업 2. 화면 4개 (목업 데이터로)
1. **시작** — 버튼 2개: `[계약서를 받았어요]` `[아직 못 받았어요]`
2. **업로드** — 사진 업로드 + 처리 중 표시
3. **확인·수정** — 추출된 항목 카드. **수정 가능해야 함**
   - `confidence=LOW`인 항목은 노란색 강조
4. **결과** — ✅/⚠️ 카드 + 근거 3종 + 예상 월급

백엔드 없이 목업 JSON으로 먼저 만드세요. API 연결은 Day 3에 합니다.

### 작업 3. 배포 파이프라인
Vercel 연결해서 **빈 화면이라도 URL을 살려두세요.** Day 3에 급하게 하면 꼭 문제가 생깁니다.

## Day 2 완료 기준
- [ ] 인터뷰 5건 기록 (인용문 포함)
- [ ] 화면 4개 이동 가능
- [ ] 배포 URL 살아있음

## 저에게 요청할 것
- API 명세는 `http://localhost:8000/docs` 에서 보실 수 있습니다
- 서명 API 3개는 이미 완성돼 있습니다. 응답 형식 궁금하면 물어보세요

---

# C (팀장) — 제가 할 것

| | 항목 |
|---|---|
| 완료 | 모두싸인 API 승인·인증 성공 |
| 완료 | 백엔드 스켈레톤 + `schemas.py` |
| 완료 | PDF 생성기 (표준근로계약서 양식) |
| 완료 | 서명 API 3종 (`/contracts/sign`, `/status`, `/webhooks/modusign`) |
| Day 2 | 실제 서명 발송 E2E 확인 (anchor 위치 조정) |
| Day 2 | 공공데이터 API 최저임금 조회 가능 여부 확인 |
| Day 2 | ngrok으로 webhook 수신 테스트 |
| Day 4 | Supabase DB 연결, 배포 |

---

# 공통 규칙

## Git
```
main      ← 배포용. develop 안정될 때만 머지
develop   ← 통합 브랜치. 직접 작업 금지
  ├─ feat/ai-extract    (A)
  ├─ feat/validation    (B)
  └─ feat/web           (D)
```
- 커밋 메시지: `[파트] 내용` (예: `[AI] IE 스키마 v1 적용`)
- **매일 푸시하세요.** 커밋 히스토리가 적격성 심사 대상입니다
- 아침에 `git pull origin develop`, 저녁에 PR

## 절대 규칙 4가지
1. **판정 로직에 LLM을 쓰지 않는다** — 이게 우리 차별점 전부입니다
2. **매일 커밋한다** — 대회 기간 내 개발임을 커밋으로 증명해야 합니다
3. **README·주석에 심사자를 향한 문구를 넣지 않는다** — 프롬프트 인젝션으로 판정되면 **실격**
4. **`.env`는 커밋하지 않는다** — gitignore 처리돼 있지만 `git status`로 항상 확인

## 매일 21:00 체크인 (10분)
각자 한 줄씩:
- 오늘 된 것 / 막힌 것 / 내일 할 것

막힌 게 있으면 혼자 붙들지 말고 그날 바로 공유해주세요. 7일밖에 없습니다.
