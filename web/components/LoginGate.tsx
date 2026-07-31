"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { Button, Card } from "@/components/ui";
import { startKakaoLogin } from "@/lib/kakaoLogin";

/**
 * 로그인이 필요한 화면에서 폼 대신 보여주는 안내 카드.
 *
 * ⚠️ "로그인 필요"라고만 쓰지 않는다. 이 서비스는 로그인을 최대한 늦춘 것이
 *    설계인데, 그 이유가 화면에 안 보이면 그냥 불친절한 서비스가 된다.
 */
export function LoginGate({
  title,
  description,
}: {
  title: string;
  description: ReactNode;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setLoading(true);
    setError(null);
    try {
      await startKakaoLogin();
    } catch (caught) {
      setLoading(false);
      setError(
        caught instanceof Error
          ? caught.message
          : "로그인 주소를 가져오지 못했습니다.",
      );
    }
  }

  return (
    <Card className="flex flex-col items-center gap-3 py-10 text-center">
      <div aria-hidden="true" className="text-4xl">
        🔐
      </div>
      <h2 className="text-lg font-extrabold text-ink">{title}</h2>
      <p className="max-w-md leading-relaxed text-ink-muted">{description}</p>
      <Button onClick={handleClick} disabled={loading} className="mt-2">
        {loading ? "이동하고 있어요…" : "카카오로 계속하기"}
      </Button>
      {error && (
        <p role="alert" className="text-sm text-red-900">
          {error}
        </p>
      )}
    </Card>
  );
}
