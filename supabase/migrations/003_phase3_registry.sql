-- ============================================================================
-- Rustenwer — Migration 003: Phase 3 evaluation & registry
-- ============================================================================
-- Creates: benchmarks, evaluation_runs, intelligences, intelligence_versions
-- Extends: model_versions with lineage columns (dataset_version_id,
--          training_strategy, code_version, template_version, seed,
--          base_model, lineage_locked) — plan §43, §59.
--
-- FULL ENTITY LIST (remaining):
--   Phase 4: intelligence_architectures, inference_endpoints
--   Phase 5: training_strategies, training_methods (+ registry)
--   Phase 6: experiments, experiment_candidates
--   Phase 7: discovery_runs, discovery_events, experiment_memory
--   Phase 8: rsi_runs, rsi_candidates, rsi_mutations
--   Always: infrastructure, billing, audit_events
--
-- NOTE: the API runs on in-memory repositories (no Supabase credentials yet);
-- this migration is the canonical schema for the later swap.
-- ============================================================================

-- --------------------------------------------------------------------------
-- benchmarks — reusable across candidate architectures (plan §57)
-- --------------------------------------------------------------------------
create table if not exists public.benchmarks (
  id                  uuid        primary key default gen_random_uuid(),
  -- NULL project_id = global seeded benchmark (termination, ring).
  project_id          uuid        references public.projects (id) on delete cascade,
  name                text        not null,
  description         text        not null default '',
  input_spec          jsonb       not null default '{}',
  expected_output     jsonb       not null default '{}',
  evaluation_function text        not null default 'classification_on_rows',
  dataset_version_id  uuid,
  metrics             jsonb       not null default '[]',
  cost_rules          jsonb       not null default '{}',
  created_at          timestamptz not null default now(),
  unique (project_id, name)
);

create index if not exists benchmarks_project_id_idx
  on public.benchmarks (project_id);

-- --------------------------------------------------------------------------
-- evaluation_runs — one async evaluation of a subject on a benchmark
-- --------------------------------------------------------------------------
create table if not exists public.evaluation_runs (
  id             uuid        primary key default gen_random_uuid(),
  project_id     uuid        not null references public.projects (id) on delete cascade,
  benchmark_id   uuid        not null references public.benchmarks (id) on delete cascade,
  spec_id        uuid        references public.intelligence_specs (id) on delete set null,
  name           text        not null,
  subject        jsonb       not null default '{}',  -- EvaluationSubject
  status         text        not null default 'PENDING'
                 check (status in (
                   'PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'
                 )),
  quality_vector jsonb,  -- QualityVector (plan §30)
  metrics        jsonb       not null default '{}',
  cost_usd       double precision not null default 0,
  error          text,
  created_at     timestamptz not null default now(),
  completed_at   timestamptz
);

create index if not exists evaluation_runs_project_id_idx
  on public.evaluation_runs (project_id);
create index if not exists evaluation_runs_benchmark_id_idx
  on public.evaluation_runs (benchmark_id);

-- --------------------------------------------------------------------------
-- intelligences — executable cognitive systems (plan §31)
-- --------------------------------------------------------------------------
create table if not exists public.intelligences (
  id          uuid        primary key default gen_random_uuid(),
  project_id  uuid        not null references public.projects (id) on delete cascade,
  name        text        not null,
  description text,
  primitive   text        check (primitive in (
                'decision', 'classification', 'ranking', 'filtering',
                'search', 'retrieval', 'routing', 'verification',
                'critique', 'prediction', 'anomaly_detection',
                'diagnosis', 'planning', 'optimization',
                'compression', 'memory_selection',
                'iteration_control', 'termination',
                'exploration', 'selection'
              )),
  created_at  timestamptz not null default now()
);

create index if not exists intelligences_project_id_idx
  on public.intelligences (project_id);

-- --------------------------------------------------------------------------
-- intelligence_versions — immutable, reference immutable components (§43)
-- --------------------------------------------------------------------------
create table if not exists public.intelligence_versions (
  id                     uuid        primary key default gen_random_uuid(),
  intelligence_id        uuid        not null references public.intelligences (id) on delete cascade,
  version                int         not null,
  -- {model_version_ids: [...], baseline_refs: [...], harness: {...}}
  components             jsonb       not null default '{}',
  notes                  text,
  best_evaluation_run_id uuid,
  status                 text        not null default 'DRAFT'
                         check (status in ('DRAFT', 'PROMOTED')),
  created_at             timestamptz not null default now(),
  unique (intelligence_id, version)
);

create index if not exists intelligence_versions_intelligence_id_idx
  on public.intelligence_versions (intelligence_id);

-- --------------------------------------------------------------------------
-- model_versions — lineage extension (plan §43, §59)
-- --------------------------------------------------------------------------
alter table public.model_versions
  add column if not exists dataset_version_id  uuid,
  add column if not exists training_strategy   jsonb,
  add column if not exists code_version        text,
  add column if not exists template_version   text,
  add column if not exists seed                bigint,
  add column if not exists base_model          text,
  add column if not exists lineage_locked      boolean not null default true;

-- --------------------------------------------------------------------------
-- Row Level Security
-- --------------------------------------------------------------------------

alter table public.benchmarks            enable row level security;
alter table public.evaluation_runs       enable row level security;
alter table public.intelligences         enable row level security;
alter table public.intelligence_versions enable row level security;

-- benchmarks: global (project_id NULL) readable by all; project-scoped
-- benchmarks writable only inside the caller's org.
drop policy if exists "benchmarks_read_global_or_own_org" on public.benchmarks;
create policy "benchmarks_read_global_or_own_org"
  on public.benchmarks for select
  to authenticated
  using (
    project_id is null
    or exists (
      select 1 from public.projects p
      where p.id = benchmarks.project_id
        and p.organization_id = public.current_organization_id()
    )
  );

drop policy if exists "benchmarks_write_own_org" on public.benchmarks;
create policy "benchmarks_write_own_org"
  on public.benchmarks for insert
  to authenticated
  with check (
    project_id is not null
    and exists (
      select 1 from public.projects p
      where p.id = benchmarks.project_id
        and p.organization_id = public.current_organization_id()
    )
  );

drop policy if exists "benchmarks_update_delete_own_org" on public.benchmarks;
create policy "benchmarks_update_delete_own_org"
  on public.benchmarks for update
  to authenticated
  using (
    project_id is not null
    and exists (
      select 1 from public.projects p
      where p.id = benchmarks.project_id
        and p.organization_id = public.current_organization_id()
    )
  )
  with check (
    project_id is not null
    and exists (
      select 1 from public.projects p
      where p.id = benchmarks.project_id
        and p.organization_id = public.current_organization_id()
    )
  );

-- Tables with a direct project_id: full CRUD within the caller's org.
drop policy if exists "evaluation_runs_all_own_org" on public.evaluation_runs;
create policy "evaluation_runs_all_own_org"
  on public.evaluation_runs for all
  to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = evaluation_runs.project_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.projects p
    where p.id = evaluation_runs.project_id
      and p.organization_id = public.current_organization_id()
  ));

drop policy if exists "intelligences_all_own_org" on public.intelligences;
create policy "intelligences_all_own_org"
  on public.intelligences for all
  to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = intelligences.project_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.projects p
    where p.id = intelligences.project_id
      and p.organization_id = public.current_organization_id()
  ));

-- intelligence_versions: scoped through their intelligence.
drop policy if exists "intelligence_versions_all_own_org"
  on public.intelligence_versions;
create policy "intelligence_versions_all_own_org"
  on public.intelligence_versions for all
  to authenticated
  using (exists (
    select 1 from public.intelligences i
    join public.projects p on p.id = i.project_id
    where i.id = intelligence_versions.intelligence_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.intelligences i
    join public.projects p on p.id = i.project_id
    where i.id = intelligence_versions.intelligence_id
      and p.organization_id = public.current_organization_id()
  ));

-- Phase 3 cost accounting (§45): per-evaluation scope for usage events.
-- Migration 002's inline check did not include 'evaluation'.
alter table public.usage_events
  drop constraint if exists usage_events_scope_check;
alter table public.usage_events
  add constraint usage_events_scope_check
  check (scope in (
    'project', 'experiment', 'candidate', 'training_job',
    'model', 'deployment', 'evaluation', 'inference'
  ));
