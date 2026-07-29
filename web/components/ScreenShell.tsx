import Link from "next/link";
import type { ReactNode } from "react";

/**
 * 화면 공통 셸 — 상단 브랜드 헤더 + 진행 스텝퍼 + 제목.
 * 8개 화면이 공유한다.
 */
const STEPS = [
  { href: "/upload", label: "업로드" },
  { href: "/review", label: "확인·수정" },
  { href: "/result", label: "결과" },
  { href: "/contract", label: "요청서" },
  { href: "/sign", label: "서명" },
  { href: "/archive", label: "보관(준비 중)" },
];

/** 스텝 번호 (1~6) */
export type Step = 1 | 2 | 3 | 4 | 5 | 6;

export function BrandHeader() {
  return (
    <header className="sticky top-0 z-10 border-b border-brand-line/60 bg-white/80 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-3xl items-center justify-between px-5">
        <Link href="/" className="flex items-center gap-1.5 text-lg font-extrabold text-ink">
          <span aria-hidden="true" className="text-brand">
            ✓
          </span>{" "}
          페어사인
        </Link>
        <Link
          href="/archive"
          className="min-h-12 rounded-full px-3 py-3 text-sm font-semibold text-ink-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
        >
          보관함 준비 중
        </Link>
      </div>
    </header>
  );
}

export function ScreenShell({
  step,
  title,
  description,
  children,
}: {
  /** 현재 단계 (1~6). 미지정이면 스텝퍼 없음 */
  step?: Step;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <>
      <BrandHeader />
      <main className="mx-auto flex w-full max-w-3xl flex-col gap-7 px-5 pb-16 pt-8">
        <div className="flex flex-col gap-4">
          {step && (
            <ol
              aria-label="계약서 처리 단계"
              className="flex flex-wrap items-center gap-1.5"
            >
              {STEPS.map((s, i) => {
                const n = (i + 1) as Step;
                const active = n === step;
                const done = n < step;
                return (
                  <li
                    key={s.href}
                    aria-current={active ? "step" : undefined}
                    className={`rounded-full px-3 py-1 text-xs font-bold transition ${
                      active
                        ? "bg-brand text-white shadow-cta"
                        : done
                          ? "bg-brand-tint text-brand-deep"
                          : "border border-slate-300 bg-white text-ink-muted"
                    }`}
                  >
                    {n}. {s.label}
                  </li>
                );
              })}
            </ol>
          )}

          <div>
            <h1 className="text-3xl font-extrabold leading-tight tracking-tighter text-ink">
              {title}
            </h1>
            {description && (
              <p className="mt-2 leading-relaxed text-ink-muted">{description}</p>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-5">{children}</div>
      </main>
    </>
  );
}
