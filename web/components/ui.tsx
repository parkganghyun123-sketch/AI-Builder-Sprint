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
