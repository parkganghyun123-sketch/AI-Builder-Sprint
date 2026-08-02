"use client";

import Link from "next/link";
import { FormEvent, useId, useState } from "react";
import { askContractQuestion, ApiError } from "@/lib/api";
import type {
  ChatConditionGroups,
  ChatResponse,
  ContractTerms,
  GroundedChatEvidenceKind,
} from "@/lib/types";

const INITIAL_SUGGESTIONS = [
  "나 지금 주휴수당 받을 수 있나요?",
  "계약서에 빠진 내용이 있나요?",
  "제 시급이 최저임금보다 낮나요?",
  "퇴직금 받을 수 있어?",
  "4대보험 가입 대상인가요?",
  "연차를 받을 수 있나요?",
  "해고예고수당 받을 수 있나요?",
  "수습기간에도 최저임금을 받을 수 있나요?",
];

const SUGGESTIONS_PER_PAGE = 4;

const EVIDENCE_META: Record<
  GroundedChatEvidenceKind,
  { icon: string; label: string }
> = {
  CONTRACT: { icon: "📄", label: "계약 조건" },
  LEGAL: { icon: "⚖️", label: "확인된 기준" },
  CALCULATION: { icon: "🧮", label: "백엔드 계산" },
};

const TOPIC_LABELS: Record<string, string> = {
  SMALL_TALK: "인사·일상대화",
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

const ANSWER_MODE_LABEL = {
  DETERMINISTIC_TEMPLATE: "검증 규칙 기반 답변",
  GROUNDED_GENERATION: "공식 KB 승인 문장",
  NATURAL_GROUNDED_GENERATION: "공식 근거 기반 AI 설명",
  OPENAI_GROUNDED_GENERATION: "GPT 근거 기반 맞춤 설명",
} as const;

function topicLabel(topic: string): string {
  return TOPIC_LABELS[topic] ?? "계약 조건 안내";
}

interface ConversationItem {
  id: number;
  question: string;
  response: ChatResponse;
}

const CONDITION_GROUP_META = [
  {
    key: "met",
    label: "계약에서 확인된 지표",
    icon: "✓",
    className: "border-emerald-200 bg-emerald-50 text-emerald-950",
  },
  {
    key: "unmet",
    label: "기준과 다른 지표",
    icon: "!",
    className: "border-red-200 bg-red-50 text-red-950",
  },
  {
    key: "needs_check",
    label: "추가 확인 항목",
    icon: "?",
    className: "border-amber-300 bg-amber-50 text-amber-950",
  },
] as const;

function ConditionGroups({ groups }: { groups: ChatConditionGroups }) {
  if (CONDITION_GROUP_META.every(({ key }) => groups[key].length === 0)) {
    return null;
  }

  return (
    <div className="mt-4 flex flex-col gap-3">
      {CONDITION_GROUP_META.map(({ key, label, icon, className }) => {
        const conditions = groups[key];
        if (conditions.length === 0) return null;

        return (
          <section key={key} className={`rounded-field border p-4 ${className}`}>
            <h3 className="text-sm font-extrabold">
              <span aria-hidden="true">{icon} </span>
              {label}
            </h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-relaxed">
              {conditions.map((condition, index) => (
                <li key={`${key}-${index}`}>{condition}</li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

export function ContractChat({
  terms,
  workerBirthDate,
}: {
  terms: ContractTerms;
  workerBirthDate: string | null;
}) {
  const inputId = useId();
  const [question, setQuestion] = useState("");
  const [conversation, setConversation] = useState<ConversationItem[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [failedQuestion, setFailedQuestion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [suggestionPage, setSuggestionPage] = useState(0);

  const loading = pendingQuestion !== null;
  const responseSuggestions =
    conversation.at(-1)?.response.suggested_questions.filter(
      (suggestion) => suggestion.trim().length > 0,
    ) ?? [];
  const latestSuggestions = Array.from(
    new Set([INITIAL_SUGGESTIONS[0], ...responseSuggestions, ...INITIAL_SUGGESTIONS]),
  );
  const suggestionPageCount = Math.ceil(
    latestSuggestions.length / SUGGESTIONS_PER_PAGE,
  );
  const visibleSuggestionPage = suggestionPage % suggestionPageCount;
  const visibleSuggestions = latestSuggestions.slice(
    visibleSuggestionPage * SUGGESTIONS_PER_PAGE,
    (visibleSuggestionPage + 1) * SUGGESTIONS_PER_PAGE,
  );

  async function sendQuestion(rawQuestion: string) {
    const normalized = rawQuestion.trim();
    if (!normalized || loading) return;

    setPendingQuestion(normalized);
    setFailedQuestion(null);
    setError(null);
    setQuestion("");

    try {
      const response = await askContractQuestion({
        question: normalized,
        terms,
        worker_birth_date: workerBirthDate,
      });
      setConversation((current) => [
        ...current,
        { id: Date.now(), question: normalized, response },
      ]);
    } catch (caught) {
      setFailedQuestion(normalized);
      setError(
        caught instanceof ApiError
          ? caught.message
          : "답변을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
      );
    } finally {
      setPendingQuestion(null);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendQuestion(question);
  }

  return (
    <section
      aria-labelledby="contract-chat-title"
      className="rounded-card border border-brand-line bg-white p-6 shadow-card"
    >
      <div className="flex flex-col gap-2">
        <p className="text-sm font-bold text-brand">계약 비서</p>
        <h2
          id="contract-chat-title"
          className="text-xl font-extrabold tracking-tight text-ink"
        >
          내 계약 조건이 궁금한가요?
        </h2>
        <p className="rounded-field border border-brand-line bg-brand-tint/60 px-4 py-3 text-sm leading-relaxed text-ink-muted">
          계약서에 적힌 내용과 검증된 기준만 설명합니다. 법률 자문이 아니며,
          계약서만으로 확인할 수 없는 상황은 답변 범위를 안내합니다.
        </p>
        <p className="text-xs leading-relaxed text-ink-muted">
          질문은 FairSign 백엔드로 전송됩니다. Upstage와 OpenAI에는 비식별 판정
          사실 카드·분류 키·검증된 KB 후보만 보냅니다. OpenAI 요청은 저장
          비활성화(store:false)로 전송합니다. 질문 원문, 계약서 파일·원문,
          이름·연락처·생년월일·사업장 정보는 보내지 않으며, 외부 제공자의 별도
          보관 정책이 적용될 수 있습니다.
        </p>
      </div>

      {conversation.length > 0 && (
        <ol className="mt-6 flex flex-col gap-5" aria-label="계약 비서 대화">
          {conversation.map(({ id, question: asked, response }) => (
            <li key={id} className="flex flex-col gap-3">
              <p className="ml-auto max-w-[90%] rounded-2xl rounded-br-sm bg-brand px-4 py-3 text-sm font-semibold leading-relaxed text-white">
                {asked}
              </p>
              <article className="rounded-card border border-brand-line bg-brand-tint/30 p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-bold text-brand-deep">
                    {topicLabel(response.topic)}
                  </span>
                  {response.intent === "OUT_OF_SCOPE" && (
                    <span className="text-xs font-bold text-amber-900">
                      계약서만으로 확인 어려움
                    </span>
                  )}
                  <span className="rounded-full border border-brand-line bg-white px-3 py-1 text-xs font-bold text-brand-deep">
                    {ANSWER_MODE_LABEL[response.answer_mode]}
                  </span>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm font-semibold leading-relaxed text-ink">
                  {response.answer}
                </p>

                {response.retrieved_knowledge.length > 0 && (
                  <section className="mt-4 rounded-field border border-brand-line bg-white/80 px-4 py-3">
                    <h3 className="text-xs font-extrabold text-brand-deep">
                      검색된 공식 KB 근거
                    </h3>
                    <ul className="mt-2 space-y-2 text-xs leading-relaxed text-ink-muted">
                      {response.retrieved_knowledge.map((knowledge) => (
                        <li key={knowledge.kb_id}>
                          <span className="font-bold text-ink">{knowledge.title}</span>
                          {knowledge.source_ids.length > 0 && (
                            <span> · {knowledge.source_ids.join(", ")}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {response.evidence.length > 0 && (
                  <dl className="mt-4 flex flex-col gap-3 border-t border-brand-line pt-4">
                    {response.evidence.map((item, index) => {
                      const meta = EVIDENCE_META[item.kind];
                      return (
                        <div key={`${item.kind}-${item.title}-${index}`}>
                          <dt className="text-xs font-extrabold text-brand-deep">
                            <span aria-hidden="true">{meta.icon} </span>
                            {meta.label} · {item.title}
                          </dt>
                          <dd className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-ink-muted">
                            {item.detail}
                          </dd>
                        </div>
                      );
                    })}
                  </dl>
                )}

                {response.condition_groups && (
                  <ConditionGroups groups={response.condition_groups} />
                )}

                {response.limitation && (
                  <p className="mt-4 rounded-field border border-amber-300 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-950">
                    <span className="font-extrabold">확인 한계: </span>
                    {response.limitation}
                  </p>
                )}

                <Link
                  href="/review"
                  className="mt-4 inline-flex min-h-12 items-center rounded-full border border-slate-400 bg-white px-5 py-3 text-sm font-bold text-ink transition hover:border-brand focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                >
                  계약 조건 확인·수정하기 →
                </Link>
              </article>
            </li>
          ))}
        </ol>
      )}

      {loading && (
        <div
          role="status"
          aria-live="polite"
          className="mt-5 rounded-field bg-slate-50 px-4 py-3 text-sm text-ink-muted"
        >
          계약 조건과 확인된 기준에서 근거를 찾고 있어요…
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="mt-5 flex flex-col gap-3 rounded-field border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900 sm:flex-row sm:items-center sm:justify-between"
        >
          <p>{error}</p>
          {failedQuestion && (
            <button
              type="button"
              onClick={() => void sendQuestion(failedQuestion)}
              className="min-h-12 shrink-0 rounded-full border border-red-300 bg-white px-5 py-3 font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              다시 시도
            </button>
          )}
        </div>
      )}

      <div className="mt-6">
        <p className="text-xs font-bold text-ink-muted">이런 질문을 해보세요</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {visibleSuggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={loading}
              onClick={() => void sendQuestion(suggestion)}
              className="min-h-12 rounded-full border border-brand-line bg-brand-tint/60 px-4 py-2 text-left text-sm font-bold text-brand-deep transition hover:border-brand disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              {suggestion}
            </button>
          ))}
        </div>
        {suggestionPageCount > 1 && (
          <button
            type="button"
            disabled={loading}
            onClick={() => setSuggestionPage((current) => current + 1)}
            className="mt-3 min-h-12 rounded-full px-4 py-2 text-sm font-bold text-brand-deep transition hover:bg-brand-tint disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            aria-label={`다른 추천 질문 보기, ${visibleSuggestionPage + 1}/${suggestionPageCount}페이지`}
          >
            다른 질문 보기 ({visibleSuggestionPage + 1}/{suggestionPageCount})
          </button>
        )}
      </div>

      <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-2 sm:flex-row">
        <label htmlFor={inputId} className="sr-only">
          계약 조건에 관해 질문하기
        </label>
        <input
          id={inputId}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={loading}
          maxLength={500}
          placeholder="예: 나 지금 주휴수당 받을 수 있나요?"
          className="min-h-14 flex-1 rounded-field border border-slate-400 bg-white px-4 py-3 text-ink outline-none placeholder:text-ink-muted focus:border-brand focus:ring-2 focus:ring-brand/20 disabled:bg-slate-50"
        />
        <button
          type="submit"
          disabled={loading || question.trim().length === 0}
          className="inline-flex min-h-14 items-center justify-center rounded-full bg-brand px-6 py-3 text-sm font-bold text-white shadow-cta transition hover:bg-brand-deep disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          질문하기
        </button>
      </form>
      <p className="mt-2 text-xs leading-relaxed text-ink-muted">
        대화 화면은 브라우저 저장소에 저장하지 않고, FairSign도 대화 내역을
        서버에 보관하지 않습니다. 다만 외부 제공자의 데이터 보관 정책은 아직
        검증되지 않았으며 별도로 적용될 수 있습니다.
      </p>
    </section>
  );
}
