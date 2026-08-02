"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError, askGeneralQuestion } from "@/lib/api";
import type { GeneralQuestionResponse } from "@/lib/types";
import { Button, ButtonLink } from "@/components/ui";

export function GeneralQuestionAssistant() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<GeneralQuestionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const answerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!answer) return;

    answerRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, [answer]);

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
          : "답변을 가져오지 못했어요. 잠시 뒤 다시 물어봐 주세요.",
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
    <>
      {open && (
        <section
          id="general-question-dialog"
          aria-labelledby="general-question-title"
          className="fixed bottom-24 right-5 z-50 flex max-h-[min(42rem,calc(100dvh-7rem))] w-[min(24rem,calc(100vw-2.5rem))] flex-col rounded-card border border-brand-line bg-white p-5 shadow-2xl sm:bottom-28 sm:right-7"
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
              <div
                ref={answerRef}
                className="mt-4 scroll-mt-2 border-t border-brand-line pt-4"
                aria-live="polite"
              >
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
        aria-controls="general-question-dialog"
        aria-expanded={open}
        aria-label={open ? "질문 창 닫기" : "페어사인에게 질문하기"}
        className="group fixed bottom-5 right-5 z-[60] flex h-16 w-16 items-center justify-center rounded-full bg-[radial-gradient(circle_at_35%_25%,#8BE8D3_0%,#22C7A8_46%,#006A6A_100%)] p-2 shadow-[0_14px_32px_rgba(0,106,106,0.28)] transition hover:scale-105 hover:shadow-[0_16px_36px_rgba(0,106,106,0.36)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand sm:bottom-7 sm:right-7"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <span
          aria-hidden="true"
          className="fairsign-chat-sparkle-shell relative block h-full w-full rounded-full bg-white shadow-[inset_0_0_0_1px_rgba(0,106,106,0.08),0_3px_10px_rgba(0,88,88,0.18)]"
        >
          <svg
            className="fairsign-chat-sparkle fairsign-chat-sparkle-main absolute left-[7px] top-[5px] h-7 w-7 text-[#22AFA2]"
            viewBox="0 0 24 24"
          >
            <path
              d="M12 1.5c.8 5.9 4.6 9.7 10.5 10.5-5.9.8-9.7 4.6-10.5 10.5C11.2 16.6 7.4 12.8 1.5 12 7.4 11.2 11.2 7.4 12 1.5Z"
              fill="currentColor"
            />
          </svg>
          <svg
            className="fairsign-chat-sparkle fairsign-chat-sparkle-side absolute right-[6px] top-[15px] h-5 w-5 text-brand-deep"
            viewBox="0 0 24 24"
          >
            <path
              d="M12 1.5c.8 5.9 4.6 9.7 10.5 10.5-5.9.8-9.7 4.6-10.5 10.5C11.2 16.6 7.4 12.8 1.5 12 7.4 11.2 11.2 7.4 12 1.5Z"
              fill="currentColor"
            />
          </svg>
          <svg
            className="fairsign-chat-sparkle fairsign-chat-sparkle-small absolute bottom-[6px] left-[17px] h-4 w-4 text-[#67DCC2]"
            viewBox="0 0 24 24"
          >
            <path
              d="M12 1.5c.8 5.9 4.6 9.7 10.5 10.5-5.9.8-9.7 4.6-10.5 10.5C11.2 16.6 7.4 12.8 1.5 12 7.4 11.2 11.2 7.4 12 1.5Z"
              fill="currentColor"
            />
          </svg>
        </span>
      </button>
    </>
  );
}
