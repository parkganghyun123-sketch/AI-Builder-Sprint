import assert from "node:assert/strict";

import { generalQuestionResponseSchema } from "../lib/schemas";

const responseWithAction = (href: string) => ({
  topic: "WRITTEN_CONTRACT",
  answer: "가상 응답",
  limitations: "가상 한계",
  evidence: [],
  action: { label: "다음 행동", href },
  suggestions: [],
});

const approved = [
  { case: "INTERNAL", href: "/review?path=B" },
  {
    case: "NOT_RECEIVED",
    href: "https://www.moel.go.kr/policy/policydata/view.do?bbs_seq=20230700845",
  },
  { case: "GUIDANCE_1350", href: "https://1350.moel.go.kr/" },
];

for (const item of approved) {
  assert.equal(
    generalQuestionResponseSchema.safeParse(responseWithAction(item.href)).success,
    true,
    item.case,
  );
}

const unsafe = [
  "https://example.com/",
  "https://1350.moel.go.kr/other",
  "javascript:alert(1)",
  "data:text/html,unsafe",
  "//example.com/unsafe",
];

for (const href of unsafe) {
  assert.equal(generalQuestionResponseSchema.safeParse(responseWithAction(href)).success, false);
}

console.log("action href schema verification passed");
