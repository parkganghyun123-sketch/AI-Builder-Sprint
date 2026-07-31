"use client";

import { FormEvent, useState } from "react";
import { ApiError, askGeneralQuestion } from "@/lib/api";
import type { GeneralQuestionResponse } from "@/lib/types";
import { Button, ButtonLink } from "@/components/ui";

export function GeneralQuestionAssistant() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<GeneralQuestionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function close() {
    setOpen(false);
    setQuestion("");
    setAnswer(null);
    setError(null);
  }

  async function ask(rawQuestion: string) {
    const trimmed = rawQuestion.trim();
    if (!trimmed || loading) return;

    setQuestion(trimmed);
    setLoading(true);
    setError(null);
    try {
      setAnswer(await askGeneralQuestion(trimmed, answer?.topic ?? null));
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "질문을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await ask(question);
  }

  return (
    <div className="fixed bottom-5 right-5 z-30 sm:bottom-7 sm:right-7">
      {open && (
        <section
          aria-labelledby="general-question-title"
          className="mb-3 flex max-h-[min(42rem,calc(100vh-7rem))] w-[min(24rem,calc(100vw-2.5rem))] flex-col rounded-card border border-brand-line bg-white p-5 shadow-2xl"
          role="dialog"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-bold text-brand">계약서 없이 일반 기준 확인</p>
              <h2 id="general-question-title" className="mt-1 text-lg font-extrabold text-ink">
                페어사인에게 물어보기
              </h2>
            </div>
            <button
              aria-label="질문 창 닫기"
              className="flex h-9 w-9 items-center justify-center rounded-full text-xl text-ink-muted hover:bg-brand-tint focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
              onClick={close}
              type="button"
            >
              ×
            </button>
          </div>

          <p className="mt-2 text-sm leading-relaxed text-ink-muted">
            예: “1주일에 12시간 일하면 주휴수당을 받나요?” 계약서가 필요한 내용은 사진으로 이어서 확인할 수 있어요.
          </p>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {error && <p className="mt-3 text-sm text-red-900" role="alert">{error}</p>}

            {answer && (
              <div className="mt-4 border-t border-brand-line pt-4" aria-live="polite">
              <p className="font-semibold leading-relaxed text-ink">{answer.answer}</p>
              {answer.evidence.map((item, index) => (
                <div key={`${item.label}-${index}`} className="mt-3 rounded-field bg-brand-tint/50 p-3 text-sm">
                  <p className="font-bold text-brand-deep">{item.label}</p>
                  <p className="mt-1 leading-relaxed text-ink-muted">{item.value}</p>
                  {item.url && (
                    <a className="mt-2 inline-block font-bold text-brand underline underline-offset-2" href={item.url} rel="noreferrer" target="_blank">
                      공식 근거 보기
                    </a>
                  )}
                </div>
              ))}
              <p className="mt-3 text-xs leading-relaxed text-ink-muted">
                <span className="font-bold text-ink">확인 필요: </span>{answer.limitations}
              </p>
              {answer.action && (
                <ButtonLink className="mt-3 w-full" href={answer.action.href} variant="secondary">
                  {answer.action.label}
                </ButtonLink>
              )}
              {answer.suggestions.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {answer.suggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      className="rounded-full border border-brand-line px-2.5 py-1.5 text-left text-xs font-semibold text-brand-deep hover:bg-brand-tint focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
                      onClick={() => void ask(suggestion)}
                      type="button"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              )}
              </div>
            )}
          </div>

          <form className="mt-4 shrink-0 border-t border-brand-line pt-4" onSubmit={submit}>
            <label className="text-sm font-bold text-ink" htmlFor="general-question">
              {answer ? "이어서 질문하기" : "질문"}
            </label>
            <textarea
              id="general-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              maxLength={500}
              rows={answer ? 2 : 3}
              placeholder="궁금한 점을 입력하세요"
              className="mt-2 w-full rounded-field border border-slate-300 px-3 py-2.5 text-sm outline-none placeholder:text-ink-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
            <Button className="mt-2 w-full" disabled={!question.trim() || loading} type="submit">
              {loading ? "기준을 찾는 중…" : answer ? "다시 물어보기" : "물어보기"}
            </Button>
          </form>
        </section>
      )}

      <button
        aria-expanded={open}
        aria-label="페어사인에게 질문하기"
        className="flex h-14 w-14 items-center justify-center rounded-full bg-brand text-2xl text-white shadow-2xl transition hover:scale-105 hover:bg-brand-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <span aria-hidden="true">?</span>
      </button>
    </div>
  );
}
