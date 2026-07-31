"use client";

import { useEffect, useState } from "react";
import { ApiError, buildOwnerMessage } from "@/lib/api";
import { MOEL_HOTLINE } from "@/lib/constants";
import type { ContractTerms, OwnerMessage } from "@/lib/types";
import { Button, Card } from "./ui";

/**
 * "말 꺼내기" 문구 카드.
 *
 * --- 왜 이 화면이 있는가 ---
 *
 * 계약서가 최저임금 미달인 걸 *아는 것*과, 열여섯 살이 사장님에게
 * "이거 최저임금 안 맞는데요"라고 *말하는 것*은 전혀 다른 문제다.
 * 진짜 벽은 탐지가 아니라 대면이다.
 *
 * --- 왜 믿을 수 있는가 ---
 *
 * 문장의 숫자는 백엔드가 ValidationReport 에서 그대로 꺼내 쓰고,
 * 반환 전에 app/bridge/numbers.py 가 한 번 더 대조한다. LLM 이 문장을
 * 만들지 않으므로 환각이 구조적으로 불가능하다.
 *
 * ⚠️ 그래도 numbers_verified 가 false 면 표시하지 않는다.
 *    근거 없는 숫자를 사용자가 사장님에게 보내는 순간
 *    이 기능의 신뢰가 한 번에 무너진다. 안 보여주는 편이 낫다.
 */
export function OwnerMessageCard({
  terms,
  workerBirthDate,
}: {
  terms: ContractTerms;
  workerBirthDate: string | null;
}) {
  const [result, setResult] = useState<OwnerMessage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);

    buildOwnerMessage({ terms, worker_birth_date: workerBirthDate })
      .then((next) => {
        if (alive) setResult(next);
      })
      .catch((caught: unknown) => {
        if (!alive) return;
        setError(
          caught instanceof ApiError
            ? caught.message
            : "문구를 불러오지 못했어요.",
        );
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [terms, workerBirthDate]);

  async function copy() {
    if (!result?.message) return;
    try {
      await navigator.clipboard.writeText(result.message);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // 클립보드 권한이 없거나 https 가 아닌 환경. 사용자가 직접 선택할 수 있으므로
      // 실패를 오류로 키우지 않고 안내만 바꾼다.
      setError("자동 복사가 막혀 있어요. 문구를 직접 선택해 복사해 주세요.");
    }
  }

  if (loading) {
    return (
      <Card>
        <p aria-live="polite" className="text-sm text-ink-muted">
          사장님께 어떻게 말할지 문구를 준비하고 있어요…
        </p>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <p role="alert" className="text-sm text-ink-muted">
          {error}
        </p>
      </Card>
    );
  }

  // 문제가 없으면 할 말도 없다. 억지로 문구를 만들지 않는다.
  if (!result?.message) return null;

  // 숫자 대조에 실패한 문구는 내보내지 않는다.
  if (!result.numbers_verified) {
    return (
      <Card>
        <p role="alert" className="text-sm text-ink-muted">
          문구의 숫자를 판정 결과와 대조하지 못해 표시하지 않았습니다. 결과
          내용을 직접 확인해 주세요.
        </p>
      </Card>
    );
  }

  return (
    <Card className="border-brand/40 bg-brand-tint/30">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-extrabold text-ink">
            <span aria-hidden="true">💬 </span>
            사장님께 이렇게 말해보세요
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-ink-muted">
            고발이 아니라 문의입니다. 사장님도 모르고 있었을 수 있어요.
          </p>
        </div>
      </div>

      <blockquote className="mt-4 whitespace-pre-wrap rounded-field border border-brand-line bg-white px-4 py-4 text-sm leading-relaxed text-ink">
        {result.message}
      </blockquote>

      <Button type="button" onClick={copy} className="mt-4 w-full">
        {copied ? "복사했어요" : "문구 복사하기"}
      </Button>
      <p aria-live="polite" className="sr-only">
        {copied ? "문구를 클립보드에 복사했습니다." : ""}
      </p>

      <p className="mt-3 text-xs leading-relaxed text-ink-muted">
        이 문구의 숫자는 모두 위 판정 결과에서 가져왔습니다. 대화가 잘 풀리지
        않으면 고용노동부 고객상담센터({MOEL_HOTLINE})에 문의할 수 있어요.
      </p>
    </Card>
  );
}
