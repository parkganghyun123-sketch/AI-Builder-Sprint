import { getLoginUrl } from "./api";
import { writeReturnTo } from "./auth";

/**
 * 카카오 로그인 화면으로 이동한다.
 *
 * 이동 직전 현재 경로를 저장해두고, 콜백에서 그 경로로 돌아온다.
 * 리액트 상태는 전체 페이지 이동으로 사라지지만, sessionStorage의
 * 계약 조건·검증 결과는 그대로 남아 입력을 다시 하지 않아도 된다.
 */
export async function startKakaoLogin(returnTo?: string): Promise<void> {
  writeReturnTo(
    returnTo ?? `${window.location.pathname}${window.location.search}`,
  );
  const { authorize_url } = await getLoginUrl();
  window.location.href = authorize_url;
}
