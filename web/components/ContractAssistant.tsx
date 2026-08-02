"use client";

import { FormEvent, useState } from "react";
import { askContractQuestion, ApiError } from "@/lib/api";
import type {
  ChatConditionGroups,
  ChatResponse,
  ContractTerms,
  GroundedChatEvidenceKind,
} from "@/lib/types";
import { Button, ButtonLink, Card, Pill } from "@/components/ui";

const EVIDENCE_LABEL: Record<GroundedChatEvidenceKind, string> = {
  CONTRACT: "계약서에서 확인한 내용",
  LEGAL: "공식 기준",
  CALCULATION: "계산 결과",
};

const TOPIC_LABELS: Record<string, string> = {
  WEEKLY_HOLIDAY: "주휴수당",
  MINIMUM_WAGE: "최저임금",
  BREAK_TIME: "휴게시간",
  WORKING_HOURS: "근로시간",
  WAGE: "임금",
  PAYDAY: "임금 지급일",
  CONTRACT_PERIOD: "근로계약기간",
  WORKPLACE: "근무장소",
  JOB: "업무 내용",
  MISSING_CLAUSES: "누락된 계약 항목",
  UNSUPPORTED: "확인할 수 없는 질문",
  SEVERANCE_PAY: "퇴직금",
  SOCIAL_INSURANCE: "4대보험",
  ANNUAL_LEAVE: "연차",
  DISMISSAL_NOTICE: "해고예고수당",
  PROBATION_MINIMUM_WAGE: "수습 최저임금",
};

function topicLabel(topic: string): string {
  return TOPIC_LABELS[topic] ?? "계약 조건 안내";
}

const CONDITION_GROUPS: {
  key: keyof ChatConditionGroups;
  label: string;
  className: string;
}[] = [
  {
    key: "met",
    label: "계약에서 확인된 내용",
    className: "border-emerald-200 bg-emerald-50 text-emerald-950",
  },
  {
    key: "unmet",
    label: "기준과 다른 내용",
    className: "border-red-200 bg-red-50 text-red-950",
  },
  {
    key: "needs_check",
    label: "더 확인할 내용",
    className: "border-amber-300 bg-amber-50 text-amber-950",
  },
];

export function ContractAssistant({
  terms,
  workerBirthDate,
}: {
  terms: ContractTerms;
  workerBirthDate: string | null;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(rawQuestion: string) {
    const trimmed = rawQuestion.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError(null);
    try {
      setAnswer(
        await askContractQuestion({
          terms,
          question: trimmed,
          worker_birth_date: workerBirthDate,
        }),
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "답변을 가져오지 못했어요. 잠시 뒤 다시 물어봐 주세요.",
      );
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(question);
  }

  return (
    <Card className="border-brand/40 bg-brand-tint/30">
      <div className="flex flex-col gap-2">
        <Pill>계약 비서 · 확인된 근거로 답변</Pill>
        <h2 className="text-xl font-extrabold tracking-tight text-ink">
          내 계약서에 대해 물어보세요
        </h2>
        <p className="text-sm leading-relaxed text-ink-muted">
          확인한 계약 조건과 공식 기준 안에서 필요한 내용을 골라 답해요. 새로운
          사실이나 금액을 만들지 않고, 정해진 계산 결과만 사용합니다.
        </p>
        <p className="text-xs leading-relaxed text-ink-muted">
          입력한 질문은 답변을 찾기 위해 페어사인으로 전송됩니다. 계약서 파일과
          원문, 이름·연락처·생년월일·사업장 정보는 외부 답변 서비스에 보내지
          않습니다. 개인정보를 뺀 확인 결과 일부만 답변을 정리하는 데 사용될 수
          있으며, 외부 서비스의 별도 보관 정책이 적용될 수 있습니다.
        </p>
      </div>

      <form className="mt-4 flex flex-col gap-3" onSubmit={submit}>
        <label className="text-sm font-bold text-ink" htmlFor="contract-question">
          질문
        </label>
        <textarea
          id="contract-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          maxLength={500}
          rows={3}
          placeholder="예: 나 지금 주휴수당 받을 수 있나요?"
          className="w-full rounded-field border border-slate-300 bg-white px-4 py-3 text-sm text-ink outline-none transition placeholder:text-ink-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
        <Button
          className="w-full sm:w-fit"
          disabled={!question.trim() || loading}
          type="submit"
        >
          {loading ? "근거를 찾는 중…" : "질문하기"}
        </Button>
      </form>

      {error && (
        <p
          className="mt-4 rounded-field bg-red-50 p-3 text-sm text-red-900"
          role="alert"
        >
          {error}
        </p>
      )}

      {answer && (
        <section
          className="mt-5 flex flex-col gap-4 border-t border-brand-line pt-5"
          aria-live="polite"
        >
          <div className="flex flex-wrap items-center gap-2">
            <Pill>{topicLabel(answer.topic)}</Pill>
            <span className="rounded-full border border-brand-line bg-white px-3 py-1 text-xs font-bold text-brand-deep">
              확인된 근거만 사용
            </span>
          </div>

          <div>
            <p className="text-sm font-bold text-brand-deep">답변</p>
            <p className="mt-1 whitespace-pre-wrap font-semibold leading-relaxed text-ink">
              {answer.answer}
            </p>
          </div>

          {answer.retrieved_knowledge.length > 0 && (
            <div className="rounded-field border border-brand-line bg-white/80 p-3">
              <h3 className="text-sm font-bold text-ink">답변에 사용한 공식 기준</h3>
              <ul className="mt-2 flex flex-col gap-2 text-sm">
                {answer.retrieved_knowledge.map((item) => (
                  <li key={item.kb_id}>
                    <span className="font-bold text-brand-deep">{item.title}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {answer.evidence.length > 0 && (
            <div>
              <h3 className="text-sm font-bold text-ink">답변 근거</h3>
              <ul className="mt-2 flex flex-col gap-2">
                {answer.evidence.map((item, index) => (
                  <li
                    key={`${item.kind}-${item.title}-${index}`}
                    className="rounded-field bg-white p-3 text-sm"
                  >
                    <span className="font-bold text-brand-deep">
                      {EVIDENCE_LABEL[item.kind]} · {item.title}
                    </span>
                    <p className="mt-1 whitespace-pre-wrap leading-relaxed text-ink-muted">
                      {item.detail}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {answer.condition_groups && (
            <div className="flex flex-col gap-2">
              {CONDITION_GROUPS.map(({ key, label, className }) => {
                const items = answer.condition_groups?.[key] ?? [];
                if (items.length === 0) return null;
                return (
                  <div key={key} className={`rounded-field border p-3 ${className}`}>
                    <h3 className="text-sm font-bold">{label}</h3>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-relaxed">
                      {items.map((item, index) => (
                        <li key={`${key}-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          )}

          {answer.limitation && (
            <div className="rounded-field bg-white/70 p-3 text-sm leading-relaxed text-ink-muted">
              <span className="font-bold text-ink">추가 확인 항목: </span>
              {answer.limitation}
            </div>
          )}

          <ButtonLink href="/review" variant="secondary" className="w-full sm:w-fit">
            계약 조건 확인·수정하기 →
          </ButtonLink>

          {answer.suggested_questions.length > 0 && (
            <div>
              <p className="text-sm font-bold text-ink">이렇게 물어보세요</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {answer.suggested_questions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => {
                      setQuestion(suggestion);
                      void ask(suggestion);
                    }}
                    className="rounded-full border border-brand-line bg-white px-3 py-2 text-left text-xs font-semibold text-brand-deep hover:bg-brand-tint focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </Card>
  );
}
