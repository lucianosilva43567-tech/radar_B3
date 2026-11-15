-- Forja Fitness: tabela onde cada usuário guarda os próprios dados.
-- Cole no Supabase em SQL Editor → New query → Run.

create table if not exists public.forja_data (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.forja_data enable row level security;

-- Cada pessoa só vê e altera a própria linha
drop policy if exists "forja: ler o proprio" on public.forja_data;
drop policy if exists "forja: criar o proprio" on public.forja_data;
drop policy if exists "forja: atualizar o proprio" on public.forja_data;
drop policy if exists "forja: apagar o proprio" on public.forja_data;

create policy "forja: ler o proprio"      on public.forja_data for select using (auth.uid() = user_id);
create policy "forja: criar o proprio"    on public.forja_data for insert with check (auth.uid() = user_id);
create policy "forja: atualizar o proprio" on public.forja_data for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "forja: apagar o proprio"   on public.forja_data for delete using (auth.uid() = user_id);
