/**
 * 로그인 토큰 저장.
 *
 * ⚠️ sessionStorage 를 쓴다. localStorage 는 탭을 닫아도 남아
 *    PC방·공용 PC에서 다음 사람에게 로그인이 넘어간다.
 */
const TOKEN_KEY = "fairsign:token:v1";

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function writeToken(token: string): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(TOKEN_KEY);
}

/**
 * 로그인 전에 있던 화면으로 돌아가기 위한 경로.
 *
 * 카카오 로그인은 전체 페이지 이동(리다이렉트)이라 리액트 상태가 사라진다.
 * 로그인 후 홈으로 튕기면 입력한 조건 20여 개를 다시 채워야 하므로,
 * 이동 직전 경로를 별도 키로 저장해뒀다가 콜백에서 복귀에 쓴다.
 */
const RETURN_TO_KEY = "fairsign:return-to";

export function writeReturnTo(path: string): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(RETURN_TO_KEY, path);
}

export function readReturnTo(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(RETURN_TO_KEY);
}

export function clearReturnTo(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(RETURN_TO_KEY);
}
