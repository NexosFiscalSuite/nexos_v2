-- ─────────────────────────────────────────────────────────────────────────────
-- Inicialização do Postgres (roda só na 1ª criação do volume).
-- Cria a role do APP (nexos_app): NÃO-owner e SEM bypass de RLS -> fica sujeita
-- às policies. A role de migração/auth (nexos) é o superuser do container e
-- naturalmente faz BYPASSRLS. Em produção, troque a senha e considere uma role
-- dedicada `nexos_auth` apenas com BYPASSRLS (sem superuser).
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
      CREATE ROLE nexos_app LOGIN PASSWORD 'nexos_app';
   END IF;
END
$$;

GRANT CONNECT ON DATABASE nexos TO nexos_app;
GRANT USAGE ON SCHEMA public TO nexos_app;

-- Tabelas/sequences ainda não existem aqui (a migração as cria). Garantimos que
-- objetos FUTUROS criados pelo owner concedam acesso ao app automaticamente.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO nexos_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO nexos_app;
