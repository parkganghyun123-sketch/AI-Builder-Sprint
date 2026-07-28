import { CONFIDENCE_META } from "@/lib/constants";
import type { ExtractedField } from "@/lib/types";

/**
 * 추출 항목 입력칸.
 *
 * ⭐ confidence=LOW 는 노란색으로 강조해 사용자 확인을 유도한다 (작업지시 D).
 *    NOT_FOUND 는 "계약서에서 확인되지 않습니다" 문구를 띄우고 비워둔다.
 *    임의 값으로 채우지 않는다.
 */
export function FieldInput({
  label,
  field,
  placeholder,
  unit,
}: {
  label: string;
  field: ExtractedField;
  placeholder?: string;
  unit?: string;
}) {
  const meta = CONFIDENCE_META[field.confidence];
  const isLow = field.confidence === "LOW";

  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-center gap-2 text-sm font-bold text-ink">
        {label}
        {unit && <span className="font-medium text-ink-soft">({unit})</span>}
        {isLow && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-700">
            확인 필요
          </span>
        )}
      </span>

      <input
        type="text"
        defaultValue={field.value === null ? "" : String(field.value)}
        placeholder={placeholder}
        className={`w-full rounded-field border bg-white px-4 py-2.5 text-ink outline-none transition placeholder:text-ink-soft focus:border-brand focus:ring-2 focus:ring-brand/20 ${meta.inputClass}`}
      />

      {meta.hint && (
        <span
          className={`text-xs ${isLow ? "text-amber-600" : "text-ink-soft"}`}
        >
          {meta.hint}
        </span>
      )}

      {field.source_text && (
        <span className="text-xs text-ink-soft">
          📄 계약서: “{field.source_text}”
        </span>
      )}
    </label>
  );
}
