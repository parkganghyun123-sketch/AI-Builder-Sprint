import Link from "next/link";
import { BrandHeader } from "@/components/ScreenShell";
import { ButtonLink, Card, Pill, SectionLabel } from "@/components/ui";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { GeneralQuestionAssistant } from "@/components/GeneralQuestionAssistant";

/**
 * 홈 / 랜딩 (단계 1 접속).
 * 두 진입 경로(A: 계약서 사진 / B: 조건 직접 입력)를 선택한다.
 * 로그인·회원가입 없음 (세션만).
 */
const PROBLEMS = [
  {
    icon: "🧾",
    text: "계약서를 받아도 **어떤 조건을 확인해야 하는지** 알기 어려워요.",
  },
  {
    icon: "🤔",
    text: "사장님을 기다리게 하기 눈치 보여서 그냥 사인하게 돼요.",
  },
  {
    icon: "📄",
    text: "한 달 뒤 급여가 이상해도 따질 근거 문서가 없어요.",
  },
];

const BENEFITS = [
  {
    icon: "🔍",
    title: "사진 한 장으로",
    body: "시급·근로시간·휴게시간을 자동으로 읽어내 카드로 보여줘요.",
  },
  {
    icon: "⚖️",
    title: "검증 결과는 재현 가능하게",
    body: "FairSign이 지원하는 법정 기준 대조는 같은 확인값에 같은 결과를 돌려줘요. 사진 추출값은 사람이 확인합니다.",
  },
  {
    icon: "✍️",
    title: "서명까지",
    body: "확인한 조건으로 요청서를 만들고 모두싸인 서명 단계까지 이어가요.",
  },
];

export default function HomePage() {
  return (
    <>
      <BrandHeader />

      {/* Hero */}
      <section className="mx-auto w-full max-w-3xl px-5 pb-10 pt-16 text-center">
        <Pill>알바 근로계약서 확인 · 서명</Pill>

        <h1 className="mt-6 text-[2.75rem] font-extrabold leading-[1.15] tracking-tighter text-ink sm:text-5xl">
          사인하기 전에,
          <br />
          <span className="text-brand">계약 조건을 확인해볼까요?</span>
        </h1>

        <p className="mx-auto mt-5 max-w-xl leading-relaxed text-ink-muted">
          계약서에서 읽은 조건을 사람이 확인하고, FairSign이 지원하는 법정
          기준과 백엔드 코드로 비교해 근거와 함께 보여드려요.
        </p>

        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <ButtonLink href="/upload">계약서 확인하기</ButtonLink>
          <ButtonLink href="#how" variant="secondary">
            어떻게 동작하나요?
          </ButtonLink>
        </div>
      </section>

      {/* 두 경로 선택 */}
      <section className="mx-auto w-full max-w-3xl px-5 py-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <Link href="/upload" className="group">
            <Card className="h-full transition group-hover:border-brand/50 group-hover:shadow-cta">
              <div className="text-2xl">📷</div>
              <div className="mt-3 font-extrabold text-ink">
                계약서를 받았어요
              </div>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
                사진으로 올리면 조건을 자동으로 읽어드려요.
              </p>
              <span className="mt-4 inline-block text-sm font-bold text-brand">
                사진 올리기 →
              </span>
            </Card>
          </Link>

          <Link href="/review?path=B" className="group">
            <Card className="h-full transition group-hover:border-brand/50 group-hover:shadow-cta">
              <div className="text-2xl">✏️</div>
              <div className="mt-3 font-extrabold text-ink">
                계약서를 못 받았어요
              </div>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
                사장님이 말한 조건을 직접 입력해요.
              </p>
              <span className="mt-4 inline-block text-sm font-bold text-brand">
                조건 입력하기 →
              </span>
            </Card>
          </Link>
        </div>
      </section>

      {/* 1. 문제의식 */}
      <section className="mx-auto w-full max-w-3xl px-5 py-14 text-center">
        <SectionLabel>1. 이런 적 있으셨나요</SectionLabel>
        <h2 className="mt-3 text-2xl font-extrabold tracking-tighter text-ink sm:text-3xl">
          첫 알바 첫날, 계약서를 받았는데
        </h2>

        <div className="mt-8 flex flex-col gap-3 text-left">
          {PROBLEMS.map((p) => (
            <Card key={p.icon} className="flex items-center gap-4 py-5">
              <span className="text-2xl">{p.icon}</span>
              <p className="leading-relaxed text-ink-muted">
                {p.text.split("**").map((chunk, i) =>
                  i % 2 === 1 ? (
                    <strong key={i} className="font-bold text-ink">
                      {chunk}
                    </strong>
                  ) : (
                    chunk
                  ),
                )}
              </p>
            </Card>
          ))}
        </div>

        <p className="mt-8 font-bold text-brand-deep">
          페어사인이 서명 전에 확인해 드릴게요.
        </p>
      </section>

      {/* 2. 무엇이 다른가 */}
      <section id="how" className="mx-auto w-full max-w-3xl px-5 py-14 text-center">
        <SectionLabel>2. 페어사인이 하는 일</SectionLabel>
        <h2 className="mt-3 text-2xl font-extrabold tracking-tighter text-ink sm:text-3xl">
          확인에서 끝나지 않아요 ✍️
        </h2>

        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          {BENEFITS.map((b) => (
            <Card key={b.title} className="text-center">
              <div className="text-3xl">{b.icon}</div>
              <h3 className="mt-3 font-extrabold text-ink">{b.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-muted">
                {b.body}
              </p>
            </Card>
          ))}
        </div>
      </section>

      {/* 3. 흐름 */}
      <section className="mx-auto w-full max-w-3xl px-5 py-14 text-center">
        <SectionLabel>3. 이렇게 진행돼요</SectionLabel>
        <h2 className="mt-3 text-2xl font-extrabold tracking-tighter text-ink sm:text-3xl">
          사진 한 장에서 서명 요청까지
        </h2>

        <Card className="mt-8">
          <ol className="flex flex-col gap-3 text-left">
            {[
              "계약서 사진 올리기",
              "읽어낸 조건 확인·수정 (사람이 최종 확정)",
              "법정 기준 검증 — 근거와 계산식까지",
              "근로조건 확인 요청서 미리보기",
              "모두싸인 전자서명 요청",
              "보관함 기능은 준비 중",
            ].map((label, i) => (
              <li key={label} className="flex items-center gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-tint text-xs font-extrabold text-brand-deep">
                  {i + 1}
                </span>
                <span className="text-ink">{label}</span>
              </li>
            ))}
          </ol>
        </Card>

        <div className="mt-8">
          <ButtonLink href="/upload">지금 확인해보기</ButtonLink>
        </div>
      </section>

      <footer className="mx-auto w-full max-w-3xl px-5 pb-16">
        <LegalDisclaimer />
        <p className="mt-4 text-center text-xs text-ink-soft">
          ✓ 페어사인 · AI BUILDER SPRINT 2026
        </p>
      </footer>

      <GeneralQuestionAssistant />
    </>
  );
}
