const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.join(__dirname,'..'),edge=fs.readFileSync(path.join(root,'supabase/functions/forja-ia/index.ts'),'utf8'),html=fs.readFileSync(path.join(root,'index.html'),'utf8');
function helper(source,end){return source.slice(source.indexOf('const FORJA_GEMINI_MODELS'),source.indexOf(end,source.indexOf('const FORJA_GEMINI_MODELS'))).trim()}
const edgeHelper=helper(edge,'Deno.serve'),clientHelper=helper(html,'async function ask(');
assert.equal(clientHelper,edgeHelper,'Cadeias local e servidor precisam ser equivalentes');
const models=['gemini-3.8-flash','gemini-2.5-flash-lite','gemini-3.8-flash-lite','openrouter/free','deepseek/deepseek-chat-v3-0324:free','z-ai/glm-4.5-air:free','x-ai/grok-4.1-fast:free'];
function response(text,provider='openrouter'){return provider==='gemini'?{candidates:[{content:{parts:[{text}]},finishReason:'STOP'}]}:{choices:[{message:{content:text},finish_reason:'stop'}]}}
async function verify(){
 const ctx=vm.createContext({fetch:()=>{throw Error('Rede real proibida nos testes')},AbortController,setTimeout,clearTimeout,Date,Response});vm.runInContext(edgeHelper,ctx);const api=vm.runInContext('({run:forjaRunChain,request:forjaProviderRequest})',ctx);
 const request={system:'Teste de sistema',messages:[{role:'user',content:'Pedido de teste'}],json:true,geminiKey:'test-gemini-key',openrouterKey:'test-openrouter-key'};
 let calls=[];
 let result=await api.run({...request,fetcher:async(url,options)=>{const body=JSON.parse(options.body);calls.push({url,body});return new Response(JSON.stringify(calls.length<4?{error:{message:'quota'}}:response('{"ok":true}')),{status:calls.length<4?429:200})}});
 assert.equal(calls.length,4);assert.equal(result.provider,'openrouter');assert.equal(result.model,'openrouter/free');assert.equal(JSON.parse(result.text).ok,true);
 assert(calls[0].url.includes(models[0]));assert(calls[1].url.includes(models[1]));assert(calls[2].url.includes(models[2]));assert.equal(calls[3].url,'https://openrouter.ai/api/v1/chat/completions');assert.equal(calls[3].body.messages[0].role,'system');assert(calls[3].body.messages[0].content.includes('JSON válido'));assert.equal(calls[3].body.messages[1].content,'Pedido de teste');
 calls=[];result=await api.run({...request,geminiKey:'',fetcher:async(url,options)=>{let body=JSON.parse(options.body);calls.push(body.model);return new Response(JSON.stringify(calls.length<3?{error:{message:'model unavailable'}}:response('{"meals":[]}')),{status:calls.length<3?404:200})}});assert.deepEqual(calls,models.slice(3,6));assert.equal(result.model,'z-ai/glm-4.5-air:free');
 let n=0;result=await api.run({...request,openrouterKey:'',fetcher:async()=>new Response(JSON.stringify(++n===1?response('resposta sem JSON','gemini'):response('```json\n{"valid":true}\n```','gemini')))});assert.equal(n,2);assert.equal(JSON.parse(result.text).valid,true);
 n=0;result=await api.run({...request,openrouterKey:'',fetcher:async()=>{if(++n===1)throw new DOMException('timeout','AbortError');return new Response(JSON.stringify(response('{"ok":true}','gemini')))}});assert.equal(n,2);assert.equal(result.provider,'gemini');
 calls=[];await assert.rejects(api.run({...request,fetcher:async(url,options)=>{calls.push(url.includes('googleapis')?decodeURIComponent(url.split('/models/')[1].split(':generateContent')[0]):JSON.parse(options.body).model);return new Response('{}',{status:503})}}),error=>{assert.deepEqual(calls,models);assert.equal(error.attempts.length,7);assert(!JSON.stringify(error.attempts).includes('test-openrouter-key'));return true});
 await assert.rejects(api.request('https://example.invalid',{}, {},5,(url,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('timeout','AbortError'))))),{name:'AbortError'});
 let handler,authenticated=false,networkCalls=0;
 const env={SUPABASE_URL:'https://example.supabase.co',SUPABASE_ANON_KEY:'test-public-key',GEMINI_API_KEY:'test-gemini-key',OPENROUTER_API_KEY:'test-openrouter-key'};
 const server=vm.createContext({Deno:{env:{get:k=>env[k]},serve:fn=>handler=fn},createClient:()=>({auth:{getUser:async()=>({data:{user:authenticated?{id:'test-user'}:null},error:null})}}),fetch:async()=>{networkCalls++;return new Response(JSON.stringify(response('{"ok":true}','gemini')))},AbortController,setTimeout,clearTimeout,Date,Response});
 vm.runInContext(edge.replace(/^import .*;\n/m,''),server);
 const req=body=>new Request('https://example.supabase.co/functions/v1/forja-ia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 let res=await handler(req({messages:request.messages}));assert.equal(res.status,401);assert.equal(networkCalls,0);
 authenticated=true;res=await handler(req({messages:[{role:'system',content:'não permitido'}]}));assert.equal(res.status,400);assert.equal(networkCalls,0);
 res=await handler(req({messages:request.messages,json:true,system:'teste'}));assert.equal(res.status,200);assert.equal((await res.json()).provider,'gemini');
 console.log('OK: fallback ordenado dos 7 modelos, cota, indisponibilidade, JSON inválido, timeout, mensagens OpenAI e autenticação da Edge Function.');
}
module.exports=verify().catch(error=>{console.error(error);process.exitCode=1});
