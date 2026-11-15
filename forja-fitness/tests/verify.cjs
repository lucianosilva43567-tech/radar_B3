const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
let source = html.match(/<script>\n([\s\S]*?)<\/script>/)[1].replace(/render\(\);init\(\);\s*$/, '');
const nodes = new Map(), storage = new Map();
const localStorage = {getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
const sandbox = {
 document:{querySelector:s=>{if(!nodes.has(s)) nodes.set(s,{hidden:true,textContent:'',innerHTML:'',open:false,showModal(){this.open=true},close(){this.open=false}});return nodes.get(s)},querySelectorAll:()=>[],addEventListener:()=>{}},
 window:{FORJA_CONFIG:{},addEventListener:()=>{}},localStorage,sessionStorage:localStorage,
 navigator:{onLine:true},crypto:require('node:crypto').webcrypto,structuredClone,
 setInterval:()=>{},setTimeout:()=>{},clearTimeout:()=>{},console,Date,URL,Blob,
};
vm.createContext(sandbox);vm.runInContext(source,sandbox);
function check(code){vm.runInContext(code,sandbox)}
check(`
if(pace(30,5)!=='6:00') throw Error('Pace incorreto');
if(pace(29.999,5)!=='6:00') throw Error('Arredondamento de pace incorreto');
state=blank();
if(metabolism().bmr!==1699 || metabolism().get!==2633) throw Error('TMB/GET incorretos');
let routine=validateRoutine({name:'Teste',days:[{name:'A',exercises:[{name:'Supino',sets:3,min:8,max:12,rest:90}]}]});
state.routine=routine;
state.history=[{date:today(),name:'A',volume:360,exercises:[{name:'Supino',sets:[{kg:30,reps:12,done:true},{kg:100,reps:8,done:false}]}]}];
if(record('Supino')!==30) throw Error('PR incluiu série incompleta');
if(lastExercise('supino').sets[0].kg!==30) throw Error('Sessão anterior não encontrada');
if(volume(state.history[0])!==360) throw Error('Volume incorreto');
state.meals=validateMeals([{name:'Almoço',description:'Arroz e feijão',kcal:600,protein:40,carbs:70,fat:18}]);
state.days[today()]={checked:[state.meals[0].id],meals:null};
if(nutrition().kcal!==600 || nutrition().protein!==40) throw Error('Macros incorretos');
state.days[today()].checked=[];
if(nutrition().kcal!==0) throw Error('Refeição não marcada entrou nos totais');
let rejected=false;try{validateRoutine({name:'Ruim',days:[{name:'A',exercises:[{name:'X',sets:3,min:12,max:8,rest:90}]}]})}catch{rejected=true}
if(!rejected)throw Error('Plano inválido aceito');
rejected=false;try{validateMeals([{name:'X',description:'X',kcal:-1,protein:0,carbs:0,fat:0}])}catch{rejected=true}
if(!rejected)throw Error('Macros inválidos aceitos');
state=blank();state.profile.name='<img src=x onerror=alert(1)>';
if(home().includes('<img src=x')) throw Error('Texto de perfil não escapado');
validateBackup(blank());
state=blank();state.profile.trainingPreferences.injuries='CUIDADO_PUNHO';state.profile.trainingPreferences.priority='PRIORIDADE_COSTAS';state.profile.dietPreferences.avoid='EVITAR_AMENDOIM';state.profile.dietPreferences.style='VITAMINAS_LIQUIDAS';
if(planPrompt('workout').includes('EVITAR_AMENDOIM')||planPrompt('workout').includes('VITAMINAS_LIQUIDAS'))throw Error('Dieta misturada ao treino');
if(planPrompt('menu').includes('CUIDADO_PUNHO')||planPrompt('menu').includes('PRIORIDADE_COSTAS'))throw Error('Treino misturado à dieta');
if(!planPrompt('workout').includes('CUIDADO_PUNHO')||!planPrompt('menu').includes('EVITAR_AMENDOIM'))throw Error('Preferências não enviadas ao gerador');
let restored=normalize(JSON.parse(JSON.stringify(state)));
if(restored.profile.dietPreferences.avoid!=='EVITAR_AMENDOIM'||restored.profile.trainingPreferences.injuries!=='CUIDADO_PUNHO')throw Error('Preferências não preservadas');
let legacy=normalize({profile:{name:'Teste',days:5},history:[]});
if(legacy.profile.trainingPreferences.days!==5||!legacy.profile.dietPreferences)throw Error('Perfil anterior não migrado');

if(!formatProse('## Título\\n\\n- Um item\\n- Outro item').includes('<ul>')) throw Error('Lista editorial ausente');
if(formatProse('<img src=x onerror=alert(1)>').includes('<img')) throw Error('Resposta sem escape');
if(!authError(new Error('Invalid login credentials')).includes('Diário de trader')) throw Error('Orientação de login ausente');

`);
assert(html.includes('font-variant-numeric:tabular-nums'));
assert(!html.includes('AbortSignal.timeout(30000)'));
assert(html.includes('AbortSignal.timeout(60000)'));
assert(html.includes('maxOutputTokens:4096'));
assert(fs.readFileSync(path.join(root,'supabase/functions/forja-ia/index.ts'),'utf8').includes('maxOutputTokens: 4096'));
assert(fs.readFileSync(path.join(root,'config.js'),'utf8').includes('gemini-3.8-flash'));
assert(!html.includes('gemini-2.5-flash'));
assert(html.includes('overscroll-behavior-x: none'));
assert(html.includes('padding-bottom: calc(88px + env(safe-area-inset-bottom))'));
assert(html.includes('html, body { max-width: 100%; overflow-x: hidden; position: relative;'));
assert(fs.readFileSync(path.join(root,'supabase/functions/forja-ia/index.ts'),'utf8').includes('gemini-3.8-flash'));
const manifest=JSON.parse(fs.readFileSync(path.join(root,'manifest.json'),'utf8'));
for (const icon of manifest.icons) assert(fs.existsSync(path.join(root,icon.src)));
console.log('OK: JavaScript, TMB/GET, macros, volume, PR, sessão anterior, pace, validação de planos/backup, escape de texto e ícones.');

vm.runInContext(`(async()=>{let release;const gate=new Promise(resolve=>release=resolve);let calls=0;const trigger={disabled:false,textContent:'Gerar treino',isConnected:true,setAttribute(){},removeAttribute(){}};const first=withBusy(async()=>{calls++;await gate},trigger,'Gerando...');if(!busy||!trigger.disabled||trigger.textContent!=='Gerando...')throw Error('Estado de geração incorreto');let duplicateBlocked=false;try{await withBusy(async()=>{calls++})}catch{duplicateBlocked=true}if(!duplicateBlocked||calls!==1)throw Error('Chamada duplicada permitida');release();await first;if(busy||trigger.disabled||trigger.textContent!=='Gerar treino')throw Error('Botão não restaurado');})()`,sandbox).then(()=>console.log('OK: preferências separadas/persistidas e bloqueio de chamadas duplicadas.')).catch(e=>{console.error(e);process.exitCode=1});
