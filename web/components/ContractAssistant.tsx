"use client";

import { FormEvent, useState } from "react";
import { askContractAssistant, ApiError } from "@/lib/api";
import type { ContractChatResponse, ContractTerms } from "@/lib/types";
import { Button, ButtonLink, Card, Pill } from "@/components/ui";

const KIND_LABEL = {
  CONTRACT: "계약서 근거",
  VALIDATION: "확인 결과",
  LEGAL_STANDARD: "법정 기준",
  OFFICIAL_GUIDANCE: "공식 안내",
} as const;

export function ContractAssistant({ terms }: { terms: ContractTerms }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<ContractChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError(null);
    try {
      setAnswer(await askContractAssistant({ terms, question: trimmed }));
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

  return (
    <Card className="border-brand/40 bg-brand-tint/30">
      <div className="flex flex-col gap-2">
        <Pill>계약 비서</Pill>
        <h2 className="text-xl font-extrabold tracking-tight text-ink">
          내 계약서에 대해 물어보세요
        </h2>
        <p className="text-sm leading-relaxed text-ink-muted">
          확인한 계약 조건과 검토 결과 안에서만 답해요. 개별 분쟁이나 실제 근무기록이 필요한 질문은 답하지 않습니다.
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
          placeholder="예: 최저임금 기준을 알려주세요"
          className="w-full rounded-field border border-slate-300 bg-white px-4 py-3 text-sm text-ink outline-none transition placeholder:text-ink-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
        <Button className="w-full sm:w-fit" disabled={!question.trim() || loading} type="submit">
          {loading ? "근거를 찾는 중…" : "질문하기"}
        </Button>
      </form>

      {error && (
        <p className="mt-4 rounded-field bg-red-50 p-3 text-sm text-red-900" role="alert">
          {error}
        </p>
      )}

      {answer && (
        <section className="mt-5 flex flex-col gap-4 border-t border-brand-line pt-5" aria-live="polite">
          <div>
            <p className="text-sm font-bold text-brand-deep">답변</p>
            <p className="mt-1 font-semibold leading-relaxed text-ink">{answer.answer}</p>
          </div>

          {answer.evidence.length > 0 && (
            <div>
              <h3 className="text-sm font-bold text-ink">근거</h3>
              <ul className="mt-2 flex flex-col gap-2">
                {answer.evidence.map((item, index) => (
                  <li key={`${item.kind}-${item.label}-${index}`} className="rounded-field bg-white p-3 text-sm">
                    <span className="font-bold text-brand-deep">{KIND_LABEL[item.kind]} · {item.label}</span>
                    <p className="mt-1 leading-relaxed text-ink-muted">{item.value}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="rounded-field bg-white/70 p-3 text-sm leading-relaxed text-ink-muted">
            <span className="font-bold text-ink">확인할 수 있는 범위: </span>
            {answer.limitations}
          </div>

          {answer.action && (
            <ButtonLink href={answer.action.href} variant="secondary" className="w-full sm:w-fit">
              {answer.action.label}
            </ButtonLink>
          )}

          {answer.suggestions.length > 0 && (
            <div>
              <p className="text-sm font-bold text-ink">이렇게 물어보세요</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {answer.suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => setQuestion(suggestion)}
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
