import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "페어사인 — 알바 근로계약서 확인·서명",
  description:
    "알바 근로계약서를 사진 한 장으로 확인하고, 고치고, 전자서명까지.",
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
