import type { Config } from "tailwindcss";

/**
 * 디자인 토큰 — PaperPlane(paper-plane-jade.vercel.app) 스타일 참고.
 * 청록(teal)→하늘(sky) 그라데이션 + 네이비 텍스트 + 큰 라운드 카드.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "#102A43", // 본문 네이비
          muted: "#627D98", // 보조 텍스트
          soft: "#8FA6BC",
        },
        brand: {
          DEFAULT: "#22C7C7", // 청록 (주 브랜드)
          sky: "#38BDF8", // 하늘 (그라데이션 끝)
          deep: "#0891B2", // 진한 청록 (강조 텍스트)
          tint: "#F0FAFF", // 아주 옅은 배경
          line: "#D8EEF5", // 카드 테두리
        },
        // 문서 상태 뱃지 색
        status: {
          draft: "#627D98", // 작성 중 — 회색
          requested: "#F59E0B", // 확인 요청됨 — 주황
          confirmed: "#38BDF8", // 조건 확인됨 — 파랑
          signed: "#10B981", // 체결 완료 — 초록
        },
      },
      borderRadius: {
        card: "32px",
        field: "16px",
      },
      boxShadow: {
        card: "0 12px 30px 0 rgba(8, 145, 178, 0.08)",
        cta: "0 10px 24px 0 rgba(34, 199, 199, 0.24)",
      },
      backgroundImage: {
        brand: "linear-gradient(to right, #22C7C7, #38BDF8)",
        page:
          "linear-gradient(#F0FAFF 0%, #FFFFFF 45%, #F8FDFF 100%)",
      },
      letterSpacing: {
        tighter: "-0.025em",
      },
    },
  },
  plugins: [],
};

export default config;
