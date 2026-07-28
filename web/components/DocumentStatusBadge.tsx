import { DOCUMENT_STATUS_META } from "@/lib/constants";
import type { DocumentStatus } from "@/lib/types";

/**
 * 문서 상태 뱃지 (8종) — 혼자 입력한 문서가 체결된 계약서로 오인되지 않도록
 * 상태·문구·색을 명확히 표시한다.
 *
 * 서명 전 문서는 "계약서"가 아니라 "근로조건 확인 요청서"로 부른다.
 */
export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const meta = DOCUMENT_STATUS_META[status];

  return (
    <div
      className={`flex items-start gap-3 rounded-field border px-4 py-3.5 ${meta.className}`}
    >
      <span className="mt-0.5 text-base leading-none">{meta.icon}</span>
      <div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-extrabold">{meta.title}</span>
          {meta.watermark && (
            <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] font-bold">
              확인 전 초안
            </span>
          )}
        </div>
        <p className="mt-1 text-sm leading-relaxed opacity-90">{meta.message}</p>
      </div>
    </div>
  );
}
