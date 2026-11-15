// Função da IA do Forja: recebe o pedido do app, confere se o usuário está logado
// e chama o Gemini com a chave guardada como segredo no Supabase.
import { createClient } from "jsr:@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "Método não permitido" }, 405);

  // 1. Só usuários logados no app
  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: req.headers.get("Authorization") ?? "" } },
  });
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return json({ error: "Faça login no app para usar a IA" }, 401);

  // 2. Pedido
  let body: { system?: string; messages?: { role: string; content: string }[]; json?: boolean };
  try { body = await req.json(); } catch { return json({ error: "Pedido inválido" }, 400); }
  const messages = (body.messages ?? []).slice(-14);
  const size = JSON.stringify(messages).length + (body.system ?? "").length;
  if (!messages.length || size > 120_000) return json({ error: "Pedido vazio ou grande demais" }, 400);

  // 3. Gemini
  const key = Deno.env.get("GEMINI_API_KEY");
  if (!key) return json({ error: "Segredo GEMINI_API_KEY não configurado no Supabase" }, 500);
  const model = Deno.env.get("GEMINI_MODEL") ?? "gemini-2.5-flash";
  const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-goog-api-key": key },
    body: JSON.stringify({
      systemInstruction: { parts: [{ text: body.system ?? "" }] },
      contents: messages.map((m) => ({ role: m.role === "assistant" ? "model" : "user", parts: [{ text: String(m.content) }] })),
      generationConfig: { temperature: 0.7, maxOutputTokens: 16384, ...(body.json ? { responseMimeType: "application/json" } : {}) },
    }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return json({ error: d?.error?.message ?? `Gemini respondeu ${r.status}` }, 502);
  const text = (d?.candidates?.[0]?.content?.parts ?? []).map((p: { text?: string }) => p.text ?? "").join("");
  if (!text) return json({ error: "O Gemini não devolveu texto (pode ter sido bloqueado pelo filtro de segurança)" }, 502);
  return json({ text });
});
