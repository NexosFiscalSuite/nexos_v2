# Nexos Fiscal Suite V2 — Frontend

React 18 + Vite. **Fiel ao design do V1** (mesmo `styles.css`, sidebar, rail de
Competência/Empresa, fontes Figtree + JetBrains Mono, ícones Tabler), adaptado ao
backend V2 (JWT + refresh + multi-tenant + tarefas assíncronas).

## Rodar em desenvolvimento

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000  (proxy /api -> http://localhost:8000)
```

> Suba o backend antes (API + worker + Postgres + Redis) — ver `../backend/README.md`.
> O Vite faz proxy de `/api/*` para `http://localhost:8000`, então o front fala com
> `/api/v1/...` sem CORS em dev.

## Como a integração funciona

- **`src/api.js`** — cliente único. Guarda `access`/`refresh` no localStorage; em
  `401` tenta **renovar o access** uma vez (rotação) e repete a requisição; se
  falhar, manda para `/login`. Métodos do V1 sem endpoint no V2 lançam um erro
  claro ("…estará disponível numa próxima fase").
- **`AuthContext`** — `login(email, senha, slug?)`. O slug do escritório só é
  pedido quando o mesmo e-mail existe em mais de um tenant.
- **Upload assíncrono** (`pages/Upload.jsx`) — envia os XMLs, recebe um `job_id`
  e faz **polling de `GET /jobs/{id}`** com barra de progresso e KPIs do resumo
  (importadas/duplicadas/canceladas/rejeitadas/erros). É o feedback visual da fila.

## Páginas

| Ligadas ao V2 | Stub "em breve" (sem endpoint ainda) |
|---|---|
| Login, Dashboard, Upload, Notas (listagem+filtros), Conformidade, Relatórios, Empresas, Usuários, Perfil (leitura) | Grupos, Cadastros (clientes/fornecedores), Auditoria, Painel da empresa, edição/cancelamento de nota, editar perfil |

Os stubs usam o componente `components/EmBreve.jsx` e continuam no menu para
preservar a estrutura do V1 — acendem assim que o endpoint correspondente entrar
no backend.

## Build

```bash
npm run build        # -> dist/
```
