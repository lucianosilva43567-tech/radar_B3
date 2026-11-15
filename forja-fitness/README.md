# Forja Fitness

PWA mobile-first, em HTML/CSS/JS vanilla, com quatro abas: Hoje, Treino, Dieta e Progresso. Sem instalação de dependências ou build. Interface e lógica no index.html; integração Supabase por Auth, PostgREST e Edge Function.

## Estado atual

- Tema editorial claro: papel #F9F8F6, areia #F0EEEA, texto carvão #1C1C1E e terracota #C85A32.
- Consultor sem balões, com títulos/listas formatados e compositor arredondado. Anexos TXT, MD e CSV até 24 KB.
- Conectado ao projeto Supabase Diário de trader. Use o mesmo e-mail e senha da conta desse projeto. Dados do Forja permanecem separados na tabela forja_data, com RLS por usuário.
- Tabela criada com as três colunas originais, quatro políticas de propriedade e permissões para usuários autenticados.
- Função forja-ia publicada com verificação JWT. O segredo GEMINI_API_KEY precisa existir no projeto para gerar respostas; o aplicativo mantém a opção de chave local por sessão.
- Retorno de confirmação/recuperação autorizado para https://lucianosilva43567-tech.github.io/radar_B3/forja-fitness/ . A URL principal do Diário foi preservada.
- Login, cadastro, confirmação e recuperação disponíveis em Perfil / Conta. Confirmação de e-mail continua ativa.
- manifest.json e sw.js preservados do pacote original.
- Publicação: repositório radar_B3, pasta forja-fitness, workflow .github/workflows/forja-pages.yml.

## 1. Configurar Supabase

1. No projeto escolhido, execute supabase/forja.sql no SQL Editor. A tabela mantém exatamente user_id, data e updated_at, com RLS por usuário.
2. Preencha supabaseUrl e supabaseKey no config.js usando a URL do projeto e sua chave **anon pública legada**. Nunca coloque service_role ou GEMINI_API_KEY no repositório. A função original verifica o JWT do usuário.
3. Em Edge Functions → Secrets, defina GEMINI_API_KEY e, se GEMINI_MODEL já existir, ajuste para gemini-2.5-flash (uma variável antiga prevalece sobre o valor padrão do código).
4. Faça deploy da função forja-ia usando supabase/functions/forja-ia/index.ts. Mantenha a verificação JWT habilitada; a função também valida o usuário com Auth getUser.
5. Em Authentication → URL Configuration, configure Site URL e Redirect URLs com a URL publicada no GitHub Pages. Ative o provedor Email e confira a configuração de confirmação de e-mail.
6. Se a tabela retornar permission denied, execute supabase/permissoes.sql. Esse arquivo só concede acesso à role authenticated e preserva a estrutura e o RLS originais.

Alternativamente, com Supabase CLI autenticada, consulte primeiro `supabase functions deploy --help`, vincule o projeto e publique a função forja-ia. Configure os segredos pelo painel para não deixá-los em arquivos locais ou no histórico do terminal.

O campo Conexão Supabase no app permite substituir a URL/chave pública somente nesse navegador. Para entregar configuração comum a todos, preencha config.js antes de publicar.

## 2. GitHub Pages

1. Envie o conteúdo desta pasta à raiz do repositório forja-fitness, na branch main. Inclua a pasta .github/workflows.
2. Abra Settings → Pages → Build and deployment → Source → GitHub Actions.
3. Em Actions, execute Publicar Forja Fitness ou faça um novo commit na main. O workflow verifica o app e publica somente HTML, configuração pública, manifesto, service worker e ícones.
4. Aguarde a execução verde. O endereço publicado aparece no environment github-pages e em Settings → Pages.

O workflow preparado não significa que Pages já esteja ativado. Isso exige acesso administrativo ao repositório de destino.

## Uso

- **Perfil / Conta:** ajuste dados físicos, dias disponíveis, objetivos, equipamentos, alergias e restrições antes de gerar planos. O perfil inicial contém valores de referência editáveis, não seus dados reais.
- **Hoje:** treino seguinte na sequência da rotina, resumo de alimentação consumida e peso registrado.
- **Treino:** rotina inicial editável ou geração estruturada via forja-ia (`json: true`); revise antes de aplicar. Durante uma sessão, informe kg/reps e marque a série. A sessão anterior aparece por série; ao completar todas as séries no teto, o app sugere +2,5% na sessão seguinte. A sugestão não altera automaticamente a carga.
- **Descanso:** inicia ao marcar uma série, com −15s, +15s e Pular; usa horário absoluto, para resistir à suspensão do navegador. Uma nova série reinicia o descanso. A sessão em andamento sobrevive a recarregamentos.
- **Volume:** soma de kg × repetições das séries concluídas. **PR:** maior carga já concluída para o mesmo nome de exercício. Não é recorde de 1RM. Exercícios com peso corporal podem usar 0 kg; o peso do corpo não entra no volume.
- **Dieta:** TMB Mifflin–St Jeor × fator de atividade = GET; objetivo ajusta a meta em −300/0/+250 kcal. Proteína 1,6g/kg, gordura 0,8g/kg e carboidratos pelo restante da meta. São estimativas; não uma avaliação nutricional. Cardápios sugeridos precisam de revisão de porções/restrições.
- **Refeições:** contadas nos totais apenas após o check. Trocas procuram calorias em ±10% e proteína próxima; afetam o dia atual. Refeições manuais também pertencem ao dia atual. O cardápio gerado vira o padrão dos dias seguintes.
- **Progresso:** peso, maior carga concluída por exercício em cada sessão, cardio (pace = duração/distância), medidas e Consultor com contexto recente. Cargas sem séries concluídas não entram no gráfico.
- **Chave Gemini local:** opcional, em sessionStorage, apenas para a sessão do navegador; usa o Gemini diretamente e dispensa login para esse caminho. Não faz parte do backup nem da nuvem. Sem chave local, o app chama forja-ia com o token do usuário conectado.
- **Backup:** exportação JSON versão 3, importação validada com confirmação e opção de exportar o estado anterior. A importação substitui os registros. Não inclui senha, chave Gemini ou configuração Supabase.

## Dados locais e sincronização

Dados de visitante e de cada conta ficam separados por usuário no dispositivo. O app não envia automaticamente os dados de visitante ao entrar em outra conta: há uma ação explícita para importá-los. Mudanças autenticadas ficam salvas localmente e são enviadas à linha do usuário na forja_data. Sem conexão ou após conflito, o app mantém os dados locais e mostra o estado pendente. Use Sincronizar para retomar; quando há versões divergentes, escolha qual manter após exportar backup. Atualizações condicionais por updated_at evitam sobrescrever silenciosamente uma alteração concorrente feita por este aplicativo.

Não há merge automático entre versões divergentes. No mesmo aparelho, outra aba é atualizada por eventos de armazenamento.

## PWA e offline

O app funciona offline após a primeira visita online com cache instalado. O sw.js original foi preservado: sua estratégia é rede primeiro e cache como fallback. Login, sincronização e Gemini exigem conexão. O cronômetro não depende de execução de JavaScript em segundo plano, mas não há garantia de alerta sonoro/notificação com o app fechado. No iPhone, instale pelo Safari → Compartilhar → Adicionar à Tela de Início.

## Validação

Execute `node tests/verify.cjs` na raiz. Verifica sintaxe e cálculos, validações e escape de texto. Também foram conferidos no navegador: rotina inicial, edição visual, início/retomada/finalização da sessão, 30kg × 12 = 360kg de volume, PR, descanso automático, sessão anterior, refeição manual/checklist, peso e cardio (5km em 30min = 6:00 min/km), além dos gráficos.

Login real, isolamento por RLS, sincronização entre contas/dispositivos e respostas reais Gemini ainda precisam de teste no projeto Supabase de destino, depois da configuração e publicação. Não há dados de teste embutidos no pacote.
