# A·D 작업 항목

작성 기준: 2026-07-28. C(서명·백엔드)는 핵심 흐름 완료, B(검증)는 규칙·테스트 존재.

---

## 지금 상태

| 파트 | 상태 | 근거 |
|---|---|---|
| A — AI 파이프라인 | **미착수** | `backend/app/ai/` 에 `__init__.py` 만 있음 |
| B — 검증 엔진 | 구현됨 | `validation/rules.py`, `constants.py`, `tests/` 존재 |
| C — 서명·백엔드 | 구현됨 | PDF 생성 → 서명 요청 → 웹훅 동기화까지 동작 확인 |
| D — 프론트 | **미착수** | 저장소에 프론트 디렉터리 없음 |

README의 기능표는 B를 "미착수"로 적고 있으나 실제 코드와 다르다. 회의에서 함께 갱신할 것.

---

## 좋은 소식: A↔B 접점이 이미 코드에 있다

`backend/app/schemas.py` 의 `ContractTerms` 가 두 경로(사진/폼)의 공통 출력 형식이다.
A는 **이 형식을 채우기만** 하면 되고, B·C는 이미 이 형식을 받아 동작한다.

```python
class ExtractedField(BaseModel):
    value: str | int | None = None
    confidence: Confidence = NOT_FOUND   # HIGH / LOW / NOT_FOUND
    source_text: str | None = None       # 계약서 원문 중 근거가 된 부분
```

채워야 할 필드는 21개다.

| 그룹 | 필드 |
|---|---|
| 1. 계약기간 | `contract_start`, `contract_end` |
| 2. 근무장소 | `workplace` |
| 3. 업무내용 | `job_description` |
| 4. 소정근로시간 | `work_start_time`, `work_end_time`, `break_start_time`, `break_end_time` |
| 5. 근무일/휴일 | `work_days_per_week`, `weekly_holiday_day` |
| 6. 임금 | `wage_type`, `wage_amount`, `has_bonus`, `other_allowance`, `payday`, `payment_method` |
| 당사자 | `employer_business_name`, `employer_phone`, `employer_address`, `employer_name`, `worker_address`, `worker_contact`, `worker_name` |

**형식 주의**

- 시각은 `"09:00"` 형태 — PDF 생성기가 시·분으로 쪼갠다
- `weekly_holiday_day` 가 없으면 `confidence=NOT_FOUND` 로 둘 것. 임의로 채우면 B의 "주휴일 누락" 판정이 무력화된다
- `source_text` 는 화면에서 "왜 이렇게 읽었는지" 보여주는 근거다. 반드시 채울 것

---

## A — AI 파이프라인

### A-1. Upstage Document Parse 스파이크 (최우선)

실제 계약서 사진 1장으로 응답 구조를 먼저 확인한다. 구현 전에 응답을 눈으로 볼 것.

- `spikes/upstage_spike.py` 생성 (C의 `modusign_spike.py` 구조 참고)
- 확인할 것: 표 구조가 어떻게 반환되는지, 손글씨·흐린 사진에서 어떻게 깨지는지
- **산출물**: 실제 응답 JSON 샘플 1개를 저장소에 커밋

### A-2. Information Extract 스키마 정의

`ContractTerms` 21개 필드에 맞춘 추출 스키마를 작성한다.

- 필드명을 `ContractTerms` 와 **동일하게** 맞출 것 — 다르면 매핑 코드가 하나 더 생긴다
- `confidence` 를 모델이 직접 뱉게 할지, 코드가 후처리로 정할지 결정
- **산출물**: `backend/app/ai/schema.py`

### A-3. 추출 함수 구현

- `backend/app/ai/extract.py` — `이미지 bytes → ContractTerms`
- Parse → Extract 2단계 연결
- 실패 처리: API 오류, 계약서가 아닌 사진, 글자가 안 읽히는 경우
- **누락과 오독을 구분할 것.** 못 찾으면 `NOT_FOUND`, 자신 없으면 `LOW`

### A-4. 업로드 엔드포인트 (C와 협의 필요)

현재 `POST /contracts/analyze-sign` 은 이미 정리된 `terms` 를 받는다.
**사진을 올릴 곳이 없다.** 새로 만들어야 한다.

```
POST /contracts/extract
  요청: multipart/form-data (image)
  응답: ContractTerms
```

D가 이 엔드포인트에 의존하므로 **회의에서 형태를 확정**할 것.

### A-5. 정확도 평가셋

심사 제출물이자, 정확도를 주장할 근거다.

- 계약서 샘플 10~20장 + 사람이 만든 정답 라벨
- 필드별 정확도 측정 스크립트
- **산출물**: `backend/app/evaluation/`
- 시간이 없으면 샘플 수를 줄이되 **0장은 안 된다** — "AI 정확도" 질문에 답할 수 없다

---

## D — 프론트엔드

### D-1. API 계약 확정 (최우선, C와 함께)

`/docs` 를 같이 보면서 요청·응답 형태를 고정한다. 화면 만들기 전에 끝낼 것.

특히 합의할 것:

- **409 처리** — `analyze-sign` 은 위반 항목이 있으면 409로 막는다.
  프론트는 이를 받아 위반 화면을 띄우고, 사용자가 "알고도 진행"을 누르면
  `proceed_with_violations=true` 로 재요청해야 한다
- `report.checks` 배열의 상태값(`VIOLATION` / `MISSING` / `OK`)을 화면에 어떻게 표시할지
- 서명 상태 폴링 주기 — `GET /contracts/{id}/status`

### D-2. 화면 1 — 사진 업로드

- 카메라 촬영 / 파일 선택
- 업로드 중 표시 (Document Parse 는 즉시 응답하지 않는다)

### D-3. 화면 2 — 추출 결과 확인·수정 (가장 중요)

**이 화면이 서비스의 핵심이다.** AI가 잘못 읽은 값을 사용자가 고치는 자리다.

- 21개 항목을 카드로 표시
- `confidence == LOW` 인 항목은 **시각적으로 강조**해 확인을 유도
- `confidence == NOT_FOUND` 는 빈칸으로 두고 입력 유도
- `source_text` 를 함께 보여줘 "왜 이렇게 읽었는지" 확인 가능하게
- 모든 항목은 **수정 가능**해야 한다

### D-4. 화면 3 — 검증 결과

- 위반·누락 항목을 근거(조문·계산식)와 함께 표시
- 판정은 코드가 한 것이므로 계산식을 그대로 보여줄 수 있다 — 이 점을 화면에서 드러낼 것
- "수정하러 가기" / "알고도 진행" 두 갈래

### D-5. 화면 4 — 서명 요청·진행 상황

- 근로자·사업주 이름·이메일 입력
- 발송 후 진행 상황 (`1/2 서명` → `2/2 서명 완료`)
- 완료 시 다운로드 링크 (유효시간 10분이므로 클릭 시점에 조회할 것)

### D-6. 경로 B — 직접 입력 폼

계약서를 못 받은 경우. 사진 없이 같은 `ContractTerms` 를 만든다.
우선순위는 낮다. 화면 1~4가 끝난 뒤 착수.

### D-7. 사용자 인터뷰

실제 아르바이트 경험자 대상. 발표 자료의 근거가 된다.
개발과 병행 가능하므로 일정 초반에 배치할 것.

---

## 회의에서 정할 것

1. **A 담당자가 어디까지 진행했는가** — 미착수라면 A-1부터 오늘 시작
2. `POST /contracts/extract` 엔드포인트 형태 (A·C·D 3자 합의)
3. `confidence` 를 누가 정하는가 — 모델인가 후처리 코드인가 (A↔D 접점)
4. 화면 범위 — 4종을 다 만들 것인가, 1~3만 먼저 할 것인가
5. **데모 리허설 일정** — 서명 왕복에 5분씩 걸린다. 당일 첫 시연은 실패한다

---

## 남은 기술 부채 (C)

우선순위 낮음. 데모에는 지장 없음.

- `_store` 가 메모리 딕셔너리 — 재배포 시 상태 소실. 데모 직전 배포 금지
- `WEBHOOK_PATH_TOKEN` 미설정 상태 (코드는 있음, 환경변수만 넣으면 켜짐)
- README 기능표가 실제 코드와 불일치 (B 상태)
