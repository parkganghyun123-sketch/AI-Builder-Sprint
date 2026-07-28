import { useId } from "react";
import { CONFIDENCE_META } from "@/lib/constants";
import type { ExtractedField } from "@/lib/types";

export interface FieldOption {
  value: string;
  label: string;
}

/**
 * 추출 항목 입력칸. LOW는 확인 필요 상태를 텍스트·테두리로 함께 표시하고,
 * NOT_FOUND는 빈칸으로 유지한다.
 */
export function FieldInput({
  label,
  field,
  onChange,
  placeholder,
  unit,
  type = "text",
  inputMode,
  options,
}: {
  label: string;
  field: ExtractedField;
  onChange: (value: string) => void;
  placeholder?: string;
  unit?: string;
  type?: "text" | "date" | "time" | "tel";
  inputMode?: "numeric" | "text" | "tel";
  options?: FieldOption[];
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const meta = CONFIDENCE_META[field.confidence];
  const isLow = field.confidence === "LOW";
  const value = field.value === null ? "" : String(field.value);
  const describedBy =
    meta.hint || field.source_text ? hintId : undefined;
  const controlClass = `min-h-14 w-full rounded-field border bg-white px-4 py-3 text-ink outline-none transition placeholder:text-ink-muted focus:border-brand focus:ring-2 focus:ring-brand/20 ${meta.inputClass}`;

  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={id}
        className="flex flex-wrap items-center gap-2 text-sm font-bold text-ink"
      >
        {label}
        {unit && <span className="font-medium text-ink-muted">({unit})</span>}
        {isLow && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-900">
            확인 필요
          </span>
        )}
      </label>

      {options ? (
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby={describedBy}
          className={controlClass}
        >
          <option value="">선택해 주세요</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={type}
          inputMode={inputMode}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          aria-describedby={describedBy}
          className={controlClass}
        />
      )}

      {(meta.hint || field.source_text) && (
        <div id={hintId} className="flex flex-col gap-1">
          {meta.hint && (
            <span
              className={`text-xs ${
                isLow ? "font-semibold text-amber-900" : "text-ink-muted"
              }`}
            >
              {meta.hint}
            </span>
          )}
          {field.source_text && (
            <span className="text-xs leading-relaxed text-ink-muted">
              <span aria-hidden="true">📄 </span>
              계약서 근거: “{field.source_text}”
            </span>
          )}
        </div>
      )}
    </div>
  );
}
