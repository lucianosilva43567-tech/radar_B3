// Forja Fitness: autenticação obrigatória e fallback automático entre provedores.
import { createClient } from "jsr:@supabase/supabase-js@2";
const cors={"Access-Control-Allow-Origin":"*","Access-Control-Allow-Headers":"authorization, x-client-info, apikey, content-type","Access-Control-Allow-Methods":"POST, OPTIONS"};
const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{...cors,"Content-Type":"application/json"}});
const FORJA_GEMINI_MODELS = ['gemini-3.8-flash','gemini-2.5-flash-lite','gemini-3.8-flash-lite'];
const FORJA_OPENROUTER_MODELS = ['openrouter/free','deepseek/deepseek-chat-v3-0324:free','z-ai/glm-4.5-air:free','x-ai/grok-4.1-fast:free'];
const FORJA_AI_BUDGET_MS = 55000;
function forjaResponseText(data,provider,wantJSON){
  let text='';
  if(provider==='gemini'){
    const candidate=data?.candidates?.[0];
    if(candidate?.finishReason==='MAX_TOKENS')throw Error('incomplete');
    text=(candidate?.content?.parts||[]).filter(p=>!p.thought).map(p=>p.text||'').join('');
  }else{
    const choice=data?.choices?.[0];
    if(choice?.finish_reason==='length')throw Error('incomplete');
    const content=choice?.message?.content;
    text=typeof content==='string'?content:Array.isArray(content)?content.map(p=>p.text||'').join(''):'';
  }
  text=text.trim();if(!text)throw Error('empty');
  if(wantJSON){text=text.replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,'');let parsed;try{parsed=JSON.parse(text)}catch{throw Error('invalid_json')}if(!parsed||typeof parsed!=='object')throw Error('invalid_json');text=JSON.stringify(parsed)}
  return text;
}
async function forjaProviderRequest(url,headers,payload,timeoutMs,fetcher){
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{const response=await fetcher(url,{method:'POST',headers,body:JSON.stringify(payload),signal:controller.signal});const data=await response.json().catch(()=>({}));return {response,data}}
  finally{clearTimeout(timer)}
}
async function forjaRunChain({system,messages,json:wantJSON=false,geminiKey='',openrouterKey='',fetcher=fetch}){
  if(!geminiKey&&!openrouterKey)throw Error('Nenhuma chave disponível. Configure Gemini ou OpenRouter.');
  const deadline=Date.now()+FORJA_AI_BUDGET_MS,attempts=[];
  const instructions=system+(wantJSON?'\nRetorne apenas JSON válido, conciso e direto, sem markdown, comentários ou campos extras. Conclua dentro de 4096 tokens.':'\nSeja conciso e direto.');
  const targets=[];
  if(geminiKey)FORJA_GEMINI_MODELS.forEach((model,i)=>targets.push({provider:'gemini',model,timeout:i===0?15000:5000}));
  if(openrouterKey)FORJA_OPENROUTER_MODELS.forEach((model,i)=>targets.push({provider:'openrouter',model,timeout:i===0?45000:6000}));
  for(const target of targets){
    const remaining=deadline-Date.now();if(remaining<=0)break;
    let status=0;
    try{
      const isGemini=target.provider==='gemini';
      const url=isGemini?`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(target.model)}:generateContent`:'https://openrouter.ai/api/v1/chat/completions';
      const headers=isGemini?{'Content-Type':'application/json','x-goog-api-key':geminiKey}:{'Content-Type':'application/json',Authorization:'Bearer '+openrouterKey};
      const payload=isGemini?{
        systemInstruction:{parts:[{text:instructions}]},
        contents:messages.map(m=>({role:m.role==='assistant'?'model':'user',parts:[{text:m.content}]})),
        generationConfig:{temperature:.6,maxOutputTokens:4096,...(wantJSON?{responseMimeType:'application/json'}:{})}
      }:{model:target.model,messages:[{role:'system',content:instructions},...messages],max_tokens:4096,temperature:.6,stream:false};
      const {response,data}=await forjaProviderRequest(url,headers,payload,Math.min(target.timeout,remaining,Math.max(1,remaining-(target.provider==='openrouter'&&target.model==='openrouter/free'?18000:0))),fetcher);
      status=response.status;
      if(!response.ok||data?.error){attempts.push({provider:target.provider,model:target.model,status,reason:'provider_error'});continue}
      const text=forjaResponseText(data,target.provider,wantJSON);
      return {text,provider:target.provider,model:target.model};
    }catch(error){attempts.push({provider:target.provider,model:target.model,status,reason:error?.name==='AbortError'||error?.name==='TimeoutError'?'timeout':['invalid_json','empty','incomplete'].includes(error?.message)?error.message:'network_error'})}
  }
  const timedOut=Date.now()>=deadline;
  const error=new Error(timedOut?'A tentativa dos provedores atingiu o tempo limite. Tente novamente.':'Nenhum provedor respondeu. Os modelos podem estar sem cota, indisponíveis ou sem acesso para esta chave. Tente novamente ou confira a configuração das chaves.');
  error.attempts=attempts;error.status=attempts.some(a=>a.status===429)?429:503;throw error;
}

Deno.serve(async req=>{
  if(req.method==='OPTIONS')return new Response('ok',{headers:cors});
  if(req.method!=='POST')return json({error:'Método não permitido'},405);
  const supabase=createClient(Deno.env.get('SUPABASE_URL'),Deno.env.get('SUPABASE_ANON_KEY'),{global:{headers:{Authorization:req.headers.get('Authorization')||''}}});
  try{
    const {data:{user},error}=await supabase.auth.getUser();
    if(error||!user)return json({error:'Faça login no app para usar os provedores do servidor.'},401);
  }catch{return json({error:'Não foi possível validar sua sessão. Entre novamente.'},401)}
  let body;try{body=await req.json()}catch{return json({error:'Pedido inválido'},400)}
  if(!body||typeof body!=='object'||!Array.isArray(body.messages)||typeof (body.system??'')!=='string'||(body.json!==undefined&&typeof body.json!=='boolean'))return json({error:'Formato de pedido inválido'},400);
  const messages=body.messages.slice(-14);
  if(!messages.length||messages.some(m=>!m||!['user','assistant'].includes(m.role)||typeof m.content!=='string')||JSON.stringify(messages).length+(body.system||'').length>120000)return json({error:'Pedido vazio, inválido ou grande demais'},400);
  const geminiKey=Deno.env.get('GEMINI_API_KEY')||'',openrouterKey=Deno.env.get('OPENROUTER_API_KEY')||'';
  if(!geminiKey&&!openrouterKey)return json({error:'Configure GEMINI_API_KEY ou OPENROUTER_API_KEY nos Secrets do Supabase.'},503);
  try{return json(await forjaRunChain({system:body.system||'',messages,json:body.json===true,geminiKey,openrouterKey}))}
  catch(error){return json({error:error.message,attempts:error.attempts||[]},error.status||503)}
});
