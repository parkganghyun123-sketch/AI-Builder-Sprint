# PairSign Verified Knowledge Base

> Engineering knowledge base for deterministic checks and grounded wording.
> This document is not legal advice.

## 1. Scope and Reference Date

- Last reviewed: **2026-07-27**
- Jurisdiction: Republic of Korea
- Primary audience: first-time and young part-time workers
- Product scope: contract facts, selected statutory thresholds, deterministic
  calculations, missing-clause checks, and grounded explanations
- Out of scope: definitive legal conclusions, dispute strategy, eligibility
  that depends on unverified real-world facts, and general legal counseling

Time-sensitive values must store an effective period and source. Before using
this file after its review date, re-check every rule affected by a new law,
enforcement decree, official notice, or administrative interpretation.

## 2. Source Policy

Use sources in this order:

1. 국가법령정보센터 (`law.go.kr`)
2. 고용노동부 and 고용노동부 고객상담센터 (`moel.go.kr`)
3. 최저임금위원회 (`minimumwage.go.kr`)
4. Other government or public-agency material

News, blogs, search summaries, model knowledge, and user statements are not
authoritative legal sources. They may identify research questions but must not
create production constants or conclusions.

Each production rule must be traceable to:

- a `source_id` from the registry below,
- an `effective_from` date,
- an optional `effective_to` date,
- the input values used,
- the formula or comparison performed, and
- a limitation message when the available facts are incomplete.

## 3. Verified Standards

### KB-MW-2026: 2026 minimum wage

- Effective period: 2026-01-01 through 2026-12-31
- Hourly minimum wage: **10,320 KRW**
- Reference daily amount: **82,560 KRW** for 8 hours
- Reference monthly amount: **2,156,880 KRW** for 209 hours
- Source: `SRC-MINWAGE-2026`

Implementation boundary:

- Compare wages only after the wage basis and included items are known.
- Do not describe the monthly reference amount as every worker's expected pay.
- Display “2026년 적용 기준” with the result.

Safe wording:

> 계약서에서 확인된 시급은 {contract_hourly_wage}원입니다. 이를 2026년
> 적용 최저임금 시급 10,320원과 비교한 결과입니다.

### KB-CONTRACT-TERMS: written contract terms

근로기준법 제17조 requires the employer to state the following when entering
into an employment contract:

1. wages,
2. contractual working hours,
3. holidays under Article 55,
4. annual paid leave under Article 60, and
5. other working conditions prescribed by enforcement decree.

The Act also requires a written document containing the statutory written
items, including wage components, calculation and payment method, contractual
hours, holidays, and annual paid leave, to be delivered to the worker.

- Source: `SRC-LSA-17`
- Supporting standard-form source: `SRC-MOEL-CONTRACT-FORMS`

Implementation boundary:

- A missing-clause result means “not found in the confirmed input,” not that a
  legal violation has been conclusively established.
- Standard-form comparison must record which form and version was used.

Safe wording:

> 확인된 계약 내용에서는 {field_name} 항목을 찾지 못했습니다. 원본 문서와
> 고용노동부 표준근로계약서를 함께 확인해 주세요.

### KB-BREAK-2026-07: break time

As of 2026-07-27, 근로기준법 제54조 states:

- 4 hours of work: at least 30 minutes of break
- 8 hours of work: at least 1 hour of break
- the break is provided during working hours
- the worker may use the break freely

- Source: `SRC-LSA-54-CURRENT`

Known future change:

- An amendment announced for 2026-12-10 adds a limited exception for a
  four-hour work period when the worker explicitly requests not to use the
  break.
- This future rule must not be activated before its effective date.
- Source: `SRC-LSA-54-FUTURE`

Implementation boundary:

- Do not infer that time described as a break was freely usable.
- If start time, end time, or break duration is missing, return unknown.

### KB-WEEKLY-HOLIDAY-TIME: weekly-holiday time threshold

근로기준법 제18조제3항 states that Articles 55 and 60 do not apply to a
part-time worker whose average contractual weekly working hours over four
weeks, or the shorter employment period, are below 15 hours.

- Source: `SRC-LSA-18`

Product conclusion:

- PairSign may determine only whether the **contractual-time threshold** is met
  when the confirmed contract contains enough schedule information.
- PairSign must not conclude that the worker will receive a weekly-holiday
  allowance solely because the threshold is met.
- Attendance on contractual workdays and other real-world facts are not
  established by the contract alone.

Safe wording:

> 계약상 4주 평균 주 소정근로시간이 {weekly_hours}시간이므로 주휴 관련
> 시간 요건을 {result}합니다. 실제 적용 여부는 계약서만으로 확인되지 않는
> 사실관계에 따라 달라질 수 있습니다.

### KB-EXTRA-WORK: additional, night, and holiday work

근로기준법 제56조 contains premium-pay rules for overtime, night work, and
holiday work. Night work is work between 22:00 and 06:00. The Act's scope and
exceptions, including establishment size, can affect which provisions apply.

- Sources: `SRC-LSA-11`, `SRC-LSA-56`, `SRC-MOEL-UNDER-5`

MVP boundary:

- A contract alone does not prove actual additional work.
- Do not calculate or conclude additional-work premium entitlement unless the
  required facts and the applicable rule set have been explicitly verified.
- Questions involving substituted shifts, swapped workdays, absence,
  retrospective schedule changes, employer responsibility, or disputed
  attendance are `OUT_OF_SCOPE`.

Required facts for any future supported calculation include:

- confirmed contractual schedule,
- actual start, end, and freely usable break time,
- calendar date and whether the time falls between 22:00 and 06:00,
- the applicable holiday status,
- establishment-size applicability,
- relevant agreement or approved schedule change, and
- the rule version effective on the work date.

Safe MVP response:

> 이 질문은 계약서만으로 판단할 수 없습니다. 실제 근무기록과 사업장 적용
> 조건 등 추가 사실이 필요합니다. 고용노동부 고객상담센터 1350 또는
> 전문가에게 확인해 주세요.

## 4. Grounded Chatbot Policy

Supported intents:

| Intent | Allowed source |
|---|---|
| `FIELD_LOOKUP` | User-confirmed contract JSON |
| `CALCULATION` | Deterministic rule-engine output |
| `MISSING_CLAUSE` | Versioned standard-form comparison |
| `LEGAL_STANDARD` | Verified, effective `KB.md` entry |
| `OUT_OF_SCOPE` | Fixed refusal and official guidance |

Rules:

- The LLM may classify a question or rewrite already assembled content.
- The LLM must not calculate, decide, add a fact, or change a number.
- Do not send the full raw contract to the answer-rewriting model.
- If classification is ambiguous, ask the user to select a supported category.
- If a generated answer contains an unsupported fact or number, discard it and
  use a deterministic template.
- Every substantive answer card must show the contract source when applicable,
  legal source and reference date, calculation inputs and formula, limitation,
  and next action.

Fixed out-of-scope wording:

> 이 질문은 계약서만으로 판단할 수 없습니다. 개별 상황에 따라 답이 달라질
> 수 있어 고용노동부 고객상담센터 1350 또는 전문가에게 확인해 주세요.
> 대신 계약서에 적힌 급여·근무시간, 예상 금액 계산, 빠진 항목, 확인된 법정
> 기준에 대해서는 안내할 수 있습니다.

## 5. Document Status and Neutral Wording

An employee-entered draft must never appear to be an executed contract.

| Status | Required label | Required control |
|---|---|---|
| `DRAFT` | 작성 중 | Not described as sent or agreed |
| `CONFIRMATION_REQUESTED` | 근로조건 확인 요청서 | “확인 전 초안” watermark |
| `TERMS_CONFIRMED` | 조건 확인됨·서명 전 | Must not say executed |
| `EXECUTED` | 체결 완료 | Requires verified signature-completion state |

Employer-facing wording must be neutral:

> 알바생이 입력한 내용입니다. 사실과 다르면 수정해 주세요.

Do not accuse an employer of illegality or intent. Describe only the confirmed
contract fact, comparison result, missing information, and available next step.

## 6. Privacy and Data Handling

Current MVP policy:

- Use synthetic documents and identities in tests, fixtures, screenshots, and
  demos.
- Do not collect a resident registration number or address in the MVP unless a
  separately reviewed integration makes it strictly necessary.
- Collect contact information only for an explicit delivery or signature step.
- Mask contact information after use in the UI.
- Do not log raw contract text, images, names, contact details, provider
  payloads containing personal data, API keys, or webhook secrets.
- Do not claim automatic deletion until retention behavior is implemented and
  verified.

Unresolved:

- final contract-image retention duration,
- deletion-job implementation and evidence,
- Modusign sandbox availability and identity requirements,
- electronic delivery and retention requirements.

Until resolved, mark these items `UNVERIFIED` and do not advertise them as
working guarantees.

## 7. Known Unknowns and Prohibited Conclusions

The following must not become deterministic production rules without an
official-source update and Contract Safety review:

- substituted shifts or swapped workdays and weekly-holiday attendance,
- whether a specific user can file or win a complaint,
- whether a dismissal is unfair,
- establishment-size classification inferred from casual user wording,
- electronic-signature legal-effect conclusions,
- Modusign identity or resident-number requirements,
- unimplemented image deletion or document-retention guarantees.

## 8. Source Registry

| ID | Official source | Used for |
|---|---|---|
| `SRC-MINWAGE-2026` | [최저임금위원회 2026년 적용 최저임금](https://www.minimumwage.go.kr/minWage/policy/decisionMain.do) | 2026 minimum wage and reference amounts |
| `SRC-LSA-FULL` | [국가법령정보센터 근로기준법](https://www.law.go.kr/LSW/lsInfoP.do?lsId=001872) | Current act and cross-checking |
| `SRC-LSA-17` | [근로기준법 제17조](https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1014516221) | Contract terms and written delivery |
| `SRC-LSA-18` | [근로기준법 제18조](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1027161153) | Part-time 15-hour threshold |
| `SRC-LSA-54-CURRENT` | [근로기준법 제54조 현행 조문](https://www.law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1032123587) | Current break rule |
| `SRC-LSA-54-FUTURE` | [근로기준법 2026-12-10 시행 예정 조문](https://www.law.go.kr/LSW/lsInfoP.do?ancNo=21373&ancYd=20260219&efYd=20260820&lsiSeq=283457) | Future break-rule change |
| `SRC-LSA-11` | [근로기준법 제11조](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1029727821) | General scope by establishment size |
| `SRC-LSA-56` | [근로기준법 제56조](https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1025589869) | Overtime, night, and holiday premiums |
| `SRC-MOEL-UNDER-5` | [고용노동부 1350의 5인 미만 적용 안내](https://1350.moel.go.kr/rtmview.do?id=1000000868) | Provisions generally not applied under five employees |
| `SRC-MOEL-CONTRACT-FORMS` | [고용노동부 표준근로계약서 및 임금명세서 서식](https://www.moel.go.kr/policy/policydata/view.do?bbs_seq=20230700845) | Official form families |
| `SRC-MOEL-CONTRACT-GUIDE` | [고용노동부 근로계약서 안내](https://moel.go.kr/mainpop2.do) | Written contract and official guidance |

## 9. Update Checklist

When changing a rule or visible legal explanation:

1. Open and verify the official source.
2. Record the review date and effective period.
3. Update the source registry and deterministic constant.
4. Add or update boundary-value tests.
5. Update user-facing wording and its limitation.
6. Request Contract Safety review.
7. Re-run chatbot `OUT_OF_SCOPE` and unsupported-number tests.
