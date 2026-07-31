"use client";

import { useEffect, useState } from "react";
import { getEntitlements } from "@/lib/api";
import { MOEL_HOTLINE } from "@/lib/constants";
import type { Audience, Entitlement } from "@/lib/types";
import { Card } from "./ui";

/**
 * "몰라서 못 받는 것들" 카드.
 *
 * --- 왜 이 화면이 있는가 ---
 *
 * 근로계약서 미작성 이유 1위가 "작성해야 하는지 몰라서"(40.4%)다.
 * 나쁜 마음이 아니라 무지가 원인이고, 그건 계약서 작성만의 이야기가 아니다.
 * 미성년자·임산부에게는 법이 따로 정해 둔 보호가 있는데,
 * 그 존재 자체를 모르면 있으나 마나다.
 *
 * --- 개인정보 ---
 *
 * ⚠️ 임신 여부·장애 여부는 민감정보다.
 *    선택값은 **이 컴포넌트 안에만** 있고 서버로 보내지 않는다.
 *    백엔드는 전체 목록을 주고 필터링은 여기서 한다.
 *    그래서 서버는 사용자가 어느 대상에 해당하는지 알지 못한다.
 *    화면에도 그 사실을 밝힌다 — 밝히지 않으면 사용자는 선택을 망설인다.
 *
 * --- 판정이 아니다 ---
 *
 * ⚠️ verifiable=false 인 항목을 "위반"처럼 보이게 만들지 말 것.
 *    친권자 동의서를 안 받은 것은 사업주의 의무 위반이지만
 *    계약서로는 확인할 수 없다. 확인하지 않은 것을 단정하면 안 된다.
 */

const OPTIONS: { value: Audience; label: string; hint: string }[] = [
  { value: "MINOR", label: "만 18세 미만", hint: "청소년 근로자 보호 규정" },
  { value: "PREGNANT", label: "임신 중", hint: "임산부 보호 규정" },
  { value: "POSTPARTUM", label: "출산 후 1년 이내", hint: "육아 시간" },
  { value: "FEMALE", label: "여성", hint: "생리휴가" },
  { value: "DISABILITY", label: "장애가 있음", hint: "정당한 편의 제공" },
];

export function EntitlementsCard() {
  const [items, setItems] = useState<Entitlement[]>([]);
  const [selected, setSelected] = useState<Set<Audience>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    let alive = true;
    getEntitlements()
      .then((res) => {
        if (alive) setItems(res.items);
      })
      .catch(() => {
        if (alive) setError("권리 안내를 불러오지 못했어요.");
      });
    return () => {
      alive = false;
    };
  }, []);

  function toggle(value: Audience) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }

  function toggleDetail(code: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  if (error) return null; // 부가 정보다. 실패해도 화면을 어지럽히지 않는다
  if (items.length === 0) return null;

  // EVERYONE 은 항상, 나머지는 선택한 것만.
  const visible = items.filter(
    (item) => item.audience === "EVERYONE" || selected.has(item.audience),
  );

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="text-sm font-extrabold text-ink">
          <span aria-hidden="true">📌 </span>
          몰라서 못 받는 것들
        </h2>
        <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
          근로계약서를 안 쓰는 이유 1위는 &ldquo;작성해야 하는지 몰라서&rdquo;
          입니다. 법이 정해 둔 보호도 마찬가지예요. 해당하는 걸 고르면 알려
          드릴게요.
        </p>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="sr-only">해당하는 상황 선택</legend>
        <div className="flex flex-wrap gap-2">
          {OPTIONS.map((option) => {
            const on = selected.has(option.value);
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => toggle(option.value)}
                aria-pressed={on}
                title={option.hint}
                className={`rounded-full border px-3 py-2 text-xs font-bold transition ${
                  on
                    ? "border-brand bg-brand text-white"
                    : "border-brand-line bg-white text-ink-muted hover:border-brand/50"
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>

        {/* ⚠️ 이 문장을 지우지 말 것. 밝히지 않으면 사용자가 선택을 망설인다. */}
        <p className="text-xs leading-relaxed text-ink-muted">
          <span aria-hidden="true">🔒 </span>
          선택한 내용은 <strong>이 화면에서만</strong> 쓰이고 서버로 보내지
          않습니다. 저희는 회원님이 임신 중인지, 장애가 있는지 알지 못합니다.
        </p>
      </fieldset>

      <ul className="flex flex-col gap-3">
        {visible.map((item) => {
          const open = expanded.has(item.code);
          return (
            <li
              key={item.code}
              className="rounded-field border border-brand-line bg-white p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <p className="text-sm font-extrabold text-ink">
                    {item.label}
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-ink-muted">
                    {item.summary}
                  </p>
                </div>
                {/* 계약서로 확인한 항목만 표시. 나머지는 배지를 붙이지 않는다 —
                    확인하지 않은 것을 확인한 것처럼 보이게 하면 안 된다. */}
                {item.verifiable && (
                  <span className="shrink-0 rounded-full bg-brand-tint px-2 py-1 text-[11px] font-bold text-brand">
                    계약서로 확인
                  </span>
                )}
              </div>

              {item.employer_penalty && (
                <p className="mt-2 text-xs font-semibold text-amber-900">
                  <span aria-hidden="true">⚖️ </span>
                  {item.employer_penalty}
                </p>
              )}

              <button
                type="button"
                onClick={() => toggleDetail(item.code)}
                aria-expanded={open}
                className="mt-2 text-xs font-bold text-brand"
              >
                {open ? "접기" : "자세히 보기"}
              </button>

              {open && (
                <div className="mt-2 border-t border-brand-line pt-2">
                  <p className="whitespace-pre-line text-xs leading-relaxed text-ink-muted">
                    {item.detail}
                  </p>
                  <p className="mt-2 text-[11px] text-ink-muted">
                    근거: {item.legal_basis}
                  </p>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <p className="text-xs leading-relaxed text-ink-muted">
        법이 정한 내용을 옮긴 것이며 법률 자문이 아닙니다. 개별 상황은 고용노동부
        고객상담센터({MOEL_HOTLINE})에 문의할 수 있어요.
      </p>
    </Card>
  );
}
