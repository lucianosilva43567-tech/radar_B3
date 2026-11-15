-- Execute somente se o acesso autenticado à tabela retornar permission denied.
-- Não altera a estrutura nem as políticas do forja.sql original.
grant usage on schema public to authenticated;
grant select, insert, update, delete on public.forja_data to authenticated;
