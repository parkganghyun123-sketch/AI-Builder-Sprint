"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ScreenShell } from "@/components/ScreenShell";
import { Button, Card } from "@/components/ui";
import { completeKakaoLogin } from "@/lib/api";
import { startKakaoLogin } from "@/lib/kakaoLogin";
import { clearReturnTo, readReturnTo, writeToken } from "@/lib/auth";
import { readSession } from "@/lib/session";

function CallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");

    if (!code || !state) {
      setError(
        "카카오 로그인 응답에 필요한 값이 없습니다. 처음부터 다시 시도해 주세요.",
      );
      return;
    }

    let cancelled = false;

    async function run() {
      try {
        // 처음 로그인하는 사용자의 기본 역할. 사업주 경로(EMPLOYER)로 들어온
        // 세션이면 사업주로, 그 외에는 근로자로 시작한다. 이미 있는 사용자는
        // 백엔드가 역할을 바꾸지 않는다.
        const session = readSession();
        const role = session.entryPath === "EMPLOYER" ? "EMPLOYER" : "WORKER";

        const response = await completeKakaoLogin({
          code: code as string,
          state: state as string,
          role,
        });
        if (cancelled) return;

        writeToken(response.access_token);
        const returnTo = readReturnTo() ?? "/";
        clearReturnTo();
        router.replace(returnTo);
      } catch (caught) {
        if (!cancelled) {
          setError(
            caught instanceof Error
              ? caught.message
              : "로그인을 완료하지 못했습니다.",
          );
        }
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [searchParams, router]);

  async function retry() {
    // 카카오 인가 코드는 한 번만 쓸 수 있다. 같은 code로 다시 시도하지 않고
    // 로그인 주소를 새로 받아 처음부터 다시 진행한다.
    setRetrying(true);
    setError(null);
    try {
      await startKakaoLogin(readReturnTo() ?? "/");
    } catch (caught) {
      setRetrying(false);
      setError(
        caught instanceof Error
          ? caught.message
          : "로그인 주소를 가져오지 못했습니다.",
      );
    }
  }

  return (
    <ScreenShell title="카카오 로그인 처리 중">
      <Card>
        {error ? (
          <div role="alert" className="flex flex-col gap-3">
            <p className="font-bold text-red-900">
              로그인을 완료하지 못했어요
            </p>
            <p className="text-sm leading-relaxed text-ink-muted">{error}</p>
            <Button onClick={retry} disabled={retrying} className="w-fit">
              {retrying ? "이동하고 있어요…" : "다시 시도"}
            </Button>
          </div>
        ) : (
          <p aria-live="polite" className="text-sm text-ink-muted">
            로그인을 완료하고 있어요…
          </p>
        )}
      </Card>
    </ScreenShell>
  );
}

export default function KakaoCallbackPage() {
  return (
    <Suspense>
      <CallbackContent />
    </Suspense>
  );
}
