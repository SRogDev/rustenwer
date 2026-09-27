-- ============================================================================
-- Rustenwer — Migration 004: Phase 4 intelligence abstraction
-- ============================================================================
-- Deepens the Phase-3 intelligence registry into the full abstraction
-- (plan §2, §31–§34, §43):
--
--   intelligence_architectures — named, editable architecture drafts per
--     intelligence (component composition recipes). Versions pin an
--     immutable SNAPSHOT of the architecture — drafts may evolve, a
--     published version never changes underneath a deployment (§43).
--   intelligence_versions — gains the immutable snapshot columns:
--     architecture, input_schema, output_schema (the §7 contract),
--     version_locked.
--   deployments — gains intelligence_version_id (the Phase 4 deploy path)
--     and provider (plan §34 InferenceProvider). model_version_id stays
--     nullable as the back-compat path (auto-creates a single-model
--     intelligence).
--   inference_endpoints — one serving endpoint per deployment.
--
-- NOTE: the API runs on in-memory repositories (no Supabase credentials yet);
-- this migration is the canonical schema for the later swap.
-- ============================================================================

-- --------------------------------------------------------------------------
-- intelligence_architectures — named composition drafts (plan §2.2)
-- --------------------------------------------------------------------------
create table if not exists public.intelligence_architectures (
  id              uuid        primary key default gen_random_uuid(),
  intelligence_id uuid        not null references public.intelligences (id) on delete cascade,
  name            text        not null,
  kind            text        not null default 'single_model'
                  check (kind in (
                    'single_model', 'deterministic_rule',
                    'classifier_with_deterministic_rule',
                    'embedding_knn_threshold', 'llm_judge_threshold',
                    'heuristic_pipeline', 'model_ensemble', 'custom'
                  )),
  -- {components: [{kind, ref, label, config}], execution_order: [...], notes}
  spec            jsonb       not null default '{"components": []}',
  created_at      timestamptz not null default now(),
  unique (intelligence_id, name)
);

create index if not exists intelligence_architectures_intelligence_id_idx
  on public.intelligence_architectures (intelligence_id);

-- --------------------------------------------------------------------------
-- intelligence_versions — immutable snapshot columns (plan §31, §43)
-- --------------------------------------------------------------------------
alter table public.intelligence_versions
  add column if not exists architecture    jsonb       not null default '{}',
  add column if not exists input_schema    jsonb       not null default '{}',
  add column if not exists output_schema   jsonb       not null default '{}',
  add column if not exists version_locked  boolean     not null default true;

-- --------------------------------------------------------------------------
-- deployments — deploy an Intelligence, not a Model (plan §33)
-- --------------------------------------------------------------------------
alter table public.deployments
  add column if not exists intelligence_version_id uuid
    references public.intelligence_versions (id) on delete set null,
  add column if not exists provider text not null default 'rustenwer_hosted'
    check (provider in ('rustenwer_hosted', 'external_api', 'local_gpu'));

create index if not exists deployments_intelligence_version_id_idx
  on public.deployments (intelligence_version_id);

-- --------------------------------------------------------------------------
-- inference_endpoints — serving endpoints (plan §33, §34)
-- --------------------------------------------------------------------------
create table if not exists public.inference_endpoints (
  id            uuid        primary key default gen_random_uuid(),
  deployment_id uuid        not null references public.deployments (id) on delete cascade,
  path          text        not null,  -- e.g. /api/v1/deployments/{id}/infer
  provider      text        not null default 'rustenwer_hosted'
                  check (provider in ('rustenwer_hosted', 'external_api', 'local_gpu')),
  status        text        not null default 'DRAFT'
                  check (status in ('DRAFT', 'ACTIVE', 'PAUSED', 'ARCHIVED')),
  created_at    timestamptz not null default now(),
  unique (deployment_id)
);

create index if not exists inference_endpoints_deployment_id_idx
  on public.inference_endpoints (deployment_id);

-- --------------------------------------------------------------------------
-- Row Level Security
-- --------------------------------------------------------------------------

alter table public.intelligence_architectures enable row level security;
alter table public.inference_endpoints      enable row level security;

-- intelligence_architectures: scoped through their intelligence.
drop policy if exists "intelligence_architectures_all_own_org"
  on public.intelligence_architectures;
create policy "intelligence_architectures_all_own_org"
  on public.intelligence_architectures for all
  to authenticated
  using (exists (
    select 1 from public.intelligences i
    join public.projects p on p.id = i.project_id
    where i.id = intelligence_architectures.intelligence_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.intelligences i
    join public.projects p on p.id = i.project_id
    where i.id = intelligence_architectures.intelligence_id
      and p.organization_id = public.current_organization_id()
  ));

-- inference_endpoints: scoped through their deployment's project.
drop policy if exists "inference_endpoints_all_own_org"
  on public.inference_endpoints;
create policy "inference_endpoints_all_own_org"
  on public.inference_endpoints for all
  to authenticated
  using (exists (
    select 1 from public.deployments d
    join public.projects p on p.id = d.project_id
    where d.id = inference_endpoints.deployment_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.deployments d
    join public.projects p on p.id = d.project_id
    where d.id = inference_endpoints.deployment_id
      and p.organization_id = public.current_organization_id()
  ));
