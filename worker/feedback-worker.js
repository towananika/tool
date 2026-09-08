// 間合い — 意見の受け口
//
// ユーザーから開発側への一方向。読み出しは管理トークンを持つ者だけができる。
// 投稿者に返信する経路は持たない（返信先を集めない＝個人情報を持たない設計）。
//
// デプロイ:
//   1. Cloudflare にログイン: npx wrangler login
//   2. KV を作る:            npx wrangler kv namespace create FEEDBACK
//      出力された id を wrangler.toml に貼る
//   3. 管理トークンを入れる:  npx wrangler secret put ADMIN_TOKEN
//   4. 出す:                 npx wrangler deploy
//   5. 表示された URL を index.html の FEEDBACK_ENDPOINT に書く
//
// 読む:
//   curl -H "Authorization: Bearer <ADMIN_TOKEN>" https://<URL>/admin/list

const MAX_TEXT = 1000;
const MAX_BODY = 8 * 1024;        // 8KB を超える投稿は受けない
const RATE_LIMIT = 5;             // 同一IPから1時間に5件まで
const RATE_WINDOW = 60 * 60;      // 秒

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // ブラウザからの直接POSTを許すためのCORS。GETでの一覧は許可しない
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors() });
    }

    if (url.pathname === "/admin/list" && request.method === "GET") {
      return adminList(request, env);
    }

    // ブラウザでURLを開いたときに、動いているかどうかだけ分かるようにする
    if (request.method === "GET") {
      return json({ ok: true, service: "maai-feedback" }, 200);
    }

    if (request.method !== "POST") {
      return json({ error: "not found" }, 404);
    }

    return receive(request, env);
  }
};

async function receive(request, env) {
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";

  // 連投を止める。IPそのものは保存せず、ハッシュだけを鍵に使う
  const ipKey = "rate:" + (await sha256(ip));
  const hit = parseInt((await env.FEEDBACK.get(ipKey)) || "0", 10);
  if (hit >= RATE_LIMIT) {
    return json({ error: "too many" }, 429);
  }

  const raw = await request.text();
  if (raw.length > MAX_BODY) return json({ error: "too large" }, 413);

  let body;
  try { body = JSON.parse(raw); } catch (e) { return json({ error: "bad json" }, 400); }

  const text = String(body.text || "").trim();
  if (!text) return json({ error: "empty" }, 400);
  if (text.length > MAX_TEXT) return json({ error: "too long" }, 400);

  // 同じ投稿が二重に届いても1件として扱う（圏外からの送り直しがあるため）。
  // 鍵に日付を含めると、日をまたいだ再送が別件になってしまうのでidだけで引く
  const id = String(body.id || "").slice(0, 64) || crypto.randomUUID();
  const key = "fb:" + id;

  const record = {
    id,
    at: Number(body.at) || Date.now(),
    receivedAt: Date.now(),
    text,
    usage: body.usage && typeof body.usage === "object" ? body.usage : null,
    country: request.headers.get("CF-IPCountry") || null,
    ua: (request.headers.get("User-Agent") || "").slice(0, 200)
  };

  await env.FEEDBACK.put(key, JSON.stringify(record));
  await env.FEEDBACK.put(ipKey, String(hit + 1), { expirationTtl: RATE_WINDOW });

  return json({ ok: true }, 200);
}

// 合言葉の総当たりを防ぐ。短い合言葉を使ってしまった場合の保険でもある
const ADMIN_TRIES = 10;           // 同一IPから1時間に10回まで
const ADMIN_WINDOW = 60 * 60;

// 文字を1つずつ比べて途中で抜けると、一致した文字数が応答時間に出る。
// 長さに関わらず最後まで比べることで、その手がかりを消す
function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string") return false;
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function adminList(request, env) {
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const tryKey = "admintry:" + (await sha256(ip));
  const tries = parseInt((await env.FEEDBACK.get(tryKey)) || "0", 10);
  if (tries >= ADMIN_TRIES) {
    return json({ error: "too many attempts" }, 429);
  }

  const auth = request.headers.get("Authorization") || "";
  const token = auth.replace(/^Bearer\s+/i, "");

  if (!env.ADMIN_TOKEN || !safeEqual(token, env.ADMIN_TOKEN)) {
    // 失敗した回数だけ数える。成功しても消さないのは、
    // 正しい合言葉を持っていても大量に叩く理由がないため
    await env.FEEDBACK.put(tryKey, String(tries + 1), { expirationTtl: ADMIN_WINDOW });
    // 総当たりの速度そのものを落とす
    await new Promise((r) => setTimeout(r, 700));
    return json({ error: "unauthorized" }, 401);
  }

  const list = await env.FEEDBACK.list({ prefix: "fb:" });
  const items = [];
  for (const k of list.keys) {
    const v = await env.FEEDBACK.get(k.name);
    if (v) items.push(JSON.parse(v));
  }
  items.sort((a, b) => b.receivedAt - a.receivedAt);
  return json({ count: items.length, items }, 200);
}

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: Object.assign({ "Content-Type": "application/json" }, cors())
  });
}

function cors() {
  return {
    "Access-Control-Allow-Origin": "https://towananika.github.io",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
  };
}

async function sha256(s) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
}
