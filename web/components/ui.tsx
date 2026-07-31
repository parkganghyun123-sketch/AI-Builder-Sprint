import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

/**
 * 공용 UI 프리미티브 — PaperPlane 스타일 토큰 기반.
 * pill 버튼(그라데이션) / 큰 라운드 카드 / 뱃지 / 섹션 라벨.
 */

type ButtonVariant = "primary" | "secondary" | "ghost";

const BUTTON_STYLES: Record<ButtonVariant, string> = {
  primary:
    "bg-brand text-white shadow-cta hover:bg-brand-deep border border-transparent",
  secondary:
    "bg-white text-ink border border-slate-400 hover:border-brand shadow-sm",
  ghost: "bg-transparent text-ink-muted hover:text-ink border border-transparent",
};

const BASE_BUTTON =
  "inline-flex min-h-12 items-center justify-center gap-1.5 rounded-full px-6 py-3 text-sm font-bold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-45";

/** 링크형 버튼 */
export function ButtonLink({
  href,
  variant = "primary",
  className = "",
  children,
}: {
  href: string;
  variant?: ButtonVariant;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`${BASE_BUTTON} ${BUTTON_STYLES[variant]} ${className}`}
    >
      {children}
    </Link>
  );
}

/** 실제 동작 버튼 */
export function Button({
  variant = "primary",
  className = "",
  type = "button",
  children,
  ...props
}: {
  variant?: ButtonVariant;
  className?: string;
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      className={`${BASE_BUTTON} ${BUTTON_STYLES[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

/** 큰 라운드 카드 */
export function Card({
  className = "",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={`rounded-card border border-brand-line bg-white p-6 shadow-card ${className}`}
    >
      {children}
    </div>
  );
}

/** 옅은 청록 pill 뱃지 */
export function Pill({
  className = "",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full bg-brand-tint px-4 py-1.5 text-sm font-bold text-brand-deep ${className}`}
    >
      {children}
    </span>
  );
}

/** 섹션 상단 소제목 라벨 ("1. 문제의식" 형태) */
export function SectionLabel({ children }: { children: ReactNode }) {
  return <p className="text-sm font-bold text-brand">{children}</p>;
}

/**
 * 로딩 자리표시 한 줄.
 *
 * ⚠️ 진행 중 화면을 텍스트 한 줄로만 바꾸면 "멈춘 건가?"로 읽힌다.
 *    올 내용의 모양을 미리 보여주면 기다리는 시간이 짧게 느껴진다.
 *
 * ⚠️ 애니메이션은 globals.css 의 .skeleton 이 담당한다. 그래서
 *    prefers-reduced-motion 설정을 켠 사용자에게는 자동으로 멈춘다.
 */
export function SkeletonLine({
  className = "",
  width = "w-full",
}: {
  className?: string;
  /** Tailwind 폭 클래스. 길이를 섞어야 진짜 글줄처럼 보인다. */
  width?: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={`skeleton h-4 rounded-full ${width} ${className}`}
    />
  );
}

/**
 * 카드 한 장 분량의 로딩 자리표시.
 *
 * 스크린리더에는 모양이 아니라 상태를 읽어준다 — 회색 막대는 정보가 아니다.
 */
export function SkeletonCard({
  label = "불러오는 중",
  lines = 3,
  className = "",
}: {
  label?: string;
  lines?: number;
  className?: string;
}) {
  const widths = ["w-2/3", "w-full", "w-4/5", "w-1/2"];
  return (
    <Card className={`flex flex-col gap-3 ${className}`}>
      <span aria-live="polite" className="sr-only">
        {label}
      </span>
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonLine key={i} width={widths[i % widths.length]} />
      ))}
    </Card>
  );
}

/**
 * 버튼 안에서 도는 표시.
 *
 * ⚠️ 버튼 폭이 바뀌지 않게 아이콘 자리만 차지한다. 누른 순간 버튼이
 *    출렁이면 잘못 눌렀나 싶어진다.
 */
export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
    />
  );
}
