// 일회성 도달 확인용. 서울(icn1)에서 실행되는 함수가 apis.data.go.kr 에
// 닿는지만 본다. 서비스키를 쓰지 않는다 — 인증오류가 돌아와도 "연결은 됐다"는
// 뜻이므로 도달 여부 판정에는 충분하고, 키를 다룰 이유가 없다.
//
// 확인이 끝나면 이 파일은 삭제한다.

const TARGET =
  "https://apis.data.go.kr/B551178/parking-realtime-status/info" +
  "?pageNo=1&numOfRows=1&type=json";

const TIMEOUT_MS = 15000;

module.exports = async (req, res) => {
  const started = Date.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  const result = {
    // icn1 이 아니면 리전 고정이 안 먹은 것이고, 그 경우 결과는 무의미하다.
    region: process.env.VERCEL_REGION || "(unknown)",
  };

  try {
    const response = await fetch(TARGET, { signal: controller.signal });
    const body = await response.text();
    result.reachable = true;
    result.status = response.status;
    result.elapsed_ms = Date.now() - started;
    result.body_head = body.slice(0, 300);
  } catch (err) {
    result.reachable = false;
    result.elapsed_ms = Date.now() - started;
    result.error = `${err.name}: ${err.message}`;
  } finally {
    clearTimeout(timer);
  }

  res.setHeader("content-type", "application/json; charset=utf-8");
  res.status(200).send(JSON.stringify(result, null, 2));
};
