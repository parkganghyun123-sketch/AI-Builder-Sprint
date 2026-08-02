import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "페어사인 — 알바 근로계약서 확인·서명",
  description:
    "알바 근로계약서에서 읽은 조건을 확인하고, 지원하는 기준과 비교해 전자서명 요청까지 이어갑니다.",
  icons: {
    icon: [
      {
        url: "/brand/fairsign-mark-transparent.png",
        type: "image/png",
      },
    ],
    shortcut: "/brand/fairsign-mark-transparent.png",
    apple: "/brand/fairsign-mark-transparent.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
