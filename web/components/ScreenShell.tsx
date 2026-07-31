"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getMe } from "@/lib/api";
import { clearToken, readToken } from "@/lib/auth";
import { startKakaoLogin } from "@/lib/kakaoLogin";
import type { Me } from "@/lib/types";

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
  { href: "/archive", label: "보관함" },
];

/** 스텝 번호 (1~6) */
export type Step = 1 | 2 | 3 | 4 | 5 | 6;

export function BrandHeader() {
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);
  const [loggingIn, setLoggingIn] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    // 토큰이 없으면 물어볼 것도 없다. 로그인하지 않은 사용자가 화면을
    // 넘길 때마다 401을 받아오는 요청을 만들지 않는다.
    if (!readToken()) {
      setMe(null);
      setChecked(true);
      return;
    }

    getMe()
      .then((user) => {
        if (!cancelled) setMe(user);
      })
      .catch(() => {
        if (!cancelled) setMe(null);
      })
      .finally(() => {
        if (!cancelled) setChecked(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function login() {
    setLoggingIn(true);
    setLoginError(null);
    try {
      // 인자를 주지 않으면 지금 보고 있는 화면으로 돌아온다.
      await startKakaoLogin();
    } catch (caught) {
      setLoggingIn(false);
      setLoginError(
        caught instanceof Error ? caught.message : "로그인 화면을 열지 못했어요. 다시 시도해 주세요.",
      );
    }
  }

  function logout() {
    clearToken();
    // 서버에 남은 상태는 없다 — 토큰만 지우면 로그아웃이다.
    // 홈으로 이동하며 새로 불러 헤더 상태를 확실히 초기화한다.
    window.location.href = "/";
  }

  return (
    <header className="sticky top-0 z-10 border-b border-brand-line/60 bg-white/80 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-3xl items-center justify-between px-5">
        <Link href="/" className="flex items-center gap-1.5 text-lg font-extrabold text-ink">
          <span aria-hidden="true" className="text-brand">
            ✓
          </span>{" "}
          페어사인
        </Link>
        <div className="flex items-center gap-1">
          {me ? (
            <>
              {/* ⚠️ 닉네임은 없을 수 있다.
                  카카오 동의항목을 '선택 동의'로 두면 사용자가 거부할 수 있고,
                  거부해도 로그인은 성립한다. 그대로 두면 "님" 만 남는다. */}
              <span className="px-2 text-sm font-semibold text-ink-muted">
                {me.nickname.trim() ? `${me.nickname}님` : "로그인됨"}
              </span>
              <Link
                href="/archive"
                className="min-h-12 rounded-full px-3 py-3 text-sm font-semibold text-ink-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
              >
                보관함
              </Link>
              <button
                type="button"
                onClick={logout}
                className="min-h-12 rounded-full px-3 py-3 text-sm font-semibold text-ink-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
              >
                로그아웃
              </button>
            </>
          ) : checked ? (
            <>
              {/* ⚠️ 예전에는 이 버튼이 /archive 로 가는 Link 였다.
                     그래서 "로그인"을 누르면 보관함으로 끌려가서 거기서
                     다시 "카카오로 계속하기"를 눌러야 했다. 두 번 눌러야 하고,
                     가려던 곳도 아닌 화면으로 이동한다.
                     로그인 버튼은 로그인을 시작해야 한다. */}
              <button
                type="button"
                onClick={login}
                disabled={loggingIn}
                className="min-h-12 rounded-full px-3 py-3 text-sm font-semibold text-ink-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand disabled:opacity-60"
              >
                {loggingIn ? "이동 중…" : "로그인"}
              </button>
              {loginError && (
                <span role="alert" className="px-2 text-xs text-red-900">
                  {loginError}
                </span>
              )}
            </>
          ) : null}
        </div>
      </div>
    </header>
  );
}

export function ScreenShell({
  step,
  title,
  description,
  backHref,
  children,
}: {
  /** 현재 단계 (1~6). 미지정이면 스텝퍼 없음 */
  step?: Step;
  title: string;
  description?: string;
  /**
   * "뒤로" 버튼이 갈 곳. 미지정이면 한 단계 이전으로 간다(1단계면 홈).
   * 경로 B(직접 입력)처럼 선형 이전 단계와 다른 경우에만 넘긴다.
   */
  backHref?: string;
  children: ReactNode;
}) {
  // 아직 안 간 단계는 클릭할 수 없다 — 순서가 의미를 가지므로(확인 없이 판정 금지).
  // 이미 지나온 단계(n < step)만 눌러서 돌아갈 수 있다.
  const backTo =
    backHref ?? (step && step > 1 ? STEPS[step - 2].href : "/");

  return (
    <>
      <BrandHeader />
      <main className="mx-auto flex w-full max-w-3xl flex-col gap-7 px-5 pb-16 pt-8">
        <div className="flex flex-col gap-4">
          {step && (
            <Link
              href={backTo}
              className="inline-flex min-h-11 w-fit items-center gap-1 rounded-full py-2 pr-3 text-sm font-semibold text-ink-muted transition hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
            >
              <span aria-hidden="true">←</span> 뒤로
            </Link>
          )}
          {step && (
            <ol
              aria-label="계약서 처리 단계"
              className="flex flex-wrap items-center gap-1.5"
            >
              {STEPS.map((s, i) => {
                const n = (i + 1) as Step;
                const active = n === step;
                const done = n < step;
                const chip = `block rounded-full px-3 py-1 text-xs font-bold transition ${
                  active
                    ? "bg-brand text-white shadow-cta"
                    : done
                      ? "bg-brand-tint text-brand-deep"
                      : "border border-slate-300 bg-white text-ink-muted"
                }`;
                return (
                  <li key={s.href} aria-current={active ? "step" : undefined}>
                    {done ? (
                      // 지나온 단계 — 클릭하면 그 단계로 돌아간다.
                      <Link
                        href={s.href}
                        className={`${chip} hover:bg-brand-tint/70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand`}
                      >
                        {n}. {s.label}
                      </Link>
                    ) : (
                      // 현재·이후 단계 — 이후 단계는 아직 갈 수 없다.
                      <span className={chip} aria-disabled={!active}>
                        {n}. {s.label}
                      </span>
                    )}
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
