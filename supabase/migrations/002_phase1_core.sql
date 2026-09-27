-- ============================================================================
-- Rustenwer — Migration 002: Phase 1 core entities
-- ============================================================================
-- Creates: intelligence_specs, datasets, dataset_versions, training_jobs,
--          training_runs, models, model_versions, evaluations, deployments,
--          usage_events (product plan §41, Phase 1 scope).
--
-- FULL ENTITY LIST (for later phases — DO NOT create yet):
--   Phase 3: evaluation_runs, intelligences, intelligence_versions,
--            inference_endpoints, usage
--   Phase 4: intelligence_architectures
--   Phase 5: training_strategies, training_methods (+ registry)
--   Phase 6: experiments, experiment_candidates
--   Phase 7: discovery_runs, discovery_events, experiment_memory
--   Phase 8: rsi_runs, rsi_candidates, rsi_mutations
--   Always: infrastructure, billing, audit_events
--
-- NOTE: dataset row data is NOT stored here in Phase 1. The API keeps rows
-- in its in-memory repository (dict version_id -> rows); a future migration
-- moves them to artifact storage.
-- ============================================================================

-- --------------------------------------------------------------------------
-- intelligence_specs
-- --------------------------------------------------------------------------
create table if not exists public.intelligence_specs (
  id                        uuid        primary key default gen_random_uuid(),
  project_id                uuid        not null references public.projects (id) on delete cascade,
  name                      text        not null,
  description               text,
  problem_statement         text        not null,
  input_schema              jsonb       not null default '{}',
  output_schema             jsonb       not null default '{}',
  intelligence_primitive    text        not null
                            check (intelligence_primitive in (
                              'decision', 'classification', 'ranking', 'filtering',
                              'search', 'retrieval', 'routing', 'verification',
                              'critique', 'prediction', 'anomaly_detection',
                              'diagnosis', 'planning', 'optimization',
                              'compression', 'memory_selection',
                              'iteration_control', 'termination',
                              'exploration', 'selection'
                            )),
  quality_requirements      jsonb,
  cost_requirements         jsonb,
  memory_requirements       jsonb,
  reliability_requirements  jsonb,
  latency_requirements      jsonb,
  deployment_requirements   jsonb,
  constraints               text[]      not null default '{}',
  available_data            text,
  evaluation_definition     text,
  human_review_policy       text,
  status                    text        not null default 'DRAFT'
                            check (status in ('DRAFT', 'DIAGNOSED', 'APPROVED', 'ARCHIVED')),
  version                   int         not null default 1,
  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now()
);

create index if not exists intelligence_specs_project_id_idx
  on public.intelligence_specs (project_id);

drop trigger if exists intelligence_specs_touch_updated_at on public.intelligence_specs;
create trigger intelligence_specs_touch_updated_at
  before update on public.intelligence_specs
  for each row execute function public.touch_updated_at();

-- --------------------------------------------------------------------------
-- datasets
-- --------------------------------------------------------------------------
create table if not exists public.datasets (
  id          uuid        primary key default gen_random_uuid(),
  project_id  uuid        not null references public.projects (id) on delete cascade,
  name        text        not null,
  description text,
  format      text        not null default 'inline'
              check (format in ('jsonl', 'csv', 'inline')),
  row_count   int         not null default 0,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists datasets_project_id_idx
  on public.datasets (project_id);

drop trigger if exists datasets_touch_updated_at on public.datasets;
create trigger datasets_touch_updated_at
  before update on public.datasets
  for each row execute function public.touch_updated_at();

-- --------------------------------------------------------------------------
-- dataset_versions
-- --------------------------------------------------------------------------
create table if not exists public.dataset_versions (
  id            uuid        primary key default gen_random_uuid(),
  dataset_id    uuid        not null references public.datasets (id) on delete cascade,
  version       int         not null,
  column_schema jsonb       not null default '{}',
  split_config  jsonb,
  stats         jsonb,  -- the DatasetReport
  created_at    timestamptz not null default now(),
  unique (dataset_id, version)
);

create index if not exists dataset_versions_dataset_id_idx
  on public.dataset_versions (dataset_id);

-- --------------------------------------------------------------------------
-- training_jobs
-- --------------------------------------------------------------------------
create table if not exists public.training_jobs (
  id                 uuid        primary key default gen_random_uuid(),
  project_id         uuid        not null references public.projects (id) on delete cascade,
  spec_id            uuid        references public.intelligence_specs (id) on delete set null,
  -- plain uuid for now: FK to dataset_versions lands in a later phase.
  dataset_version_id uuid,
  name               text        not null,
  status             text        not null default 'CREATED'
                     check (status in (
                       'CREATED', 'QUEUED', 'RUNNING', 'PAUSED',
                       'FAILED', 'CANCELLED', 'COMPLETED'
                     )),
  strategy           jsonb,
  compute_budget     jsonb,
  error              text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

create index if not exists training_jobs_project_id_idx
  on public.training_jobs (project_id);
create index if not exists training_jobs_spec_id_idx
  on public.training_jobs (spec_id);

drop trigger if exists training_jobs_touch_updated_at on public.training_jobs;
create trigger training_jobs_touch_updated_at
  before update on public.training_jobs
  for each row execute function public.touch_updated_at();

-- --------------------------------------------------------------------------
-- training_runs
-- --------------------------------------------------------------------------
create table if not exists public.training_runs (
  id          uuid        primary key default gen_random_uuid(),
  job_id      uuid        not null references public.training_jobs (id) on delete cascade,
  attempt     int         not null default 1,
  status      text        not null default 'CREATED'
              check (status in (
                'CREATED', 'QUEUED', 'RUNNING', 'PAUSED',
                'FAILED', 'CANCELLED', 'COMPLETED'
              )),
  metrics     jsonb       not null default '{}',
  artifacts   jsonb       not null default '{}',
  logs        text,
  started_at  timestamptz,
  finished_at timestamptz
);

create index if not exists training_runs_job_id_idx
  on public.training_runs (job_id);

-- --------------------------------------------------------------------------
-- models
-- --------------------------------------------------------------------------
create table if not exists public.models (
  id          uuid        primary key default gen_random_uuid(),
  project_id  uuid        not null references public.projects (id) on delete cascade,
  name        text        not null,
  description text,
  created_at  timestamptz not null default now()
);

create index if not exists models_project_id_idx
  on public.models (project_id);

-- --------------------------------------------------------------------------
-- model_versions
-- --------------------------------------------------------------------------
create table if not exists public.model_versions (
  id              uuid        primary key default gen_random_uuid(),
  model_id        uuid        not null references public.models (id) on delete cascade,
  version         int         not null default 1,
  training_run_id uuid,
  architecture    jsonb,
  size_bytes      bigint,
  metrics         jsonb       not null default '{}',
  artifact_uri    text,
  created_at      timestamptz not null default now(),
  unique (model_id, version)
);

create index if not exists model_versions_model_id_idx
  on public.model_versions (model_id);

-- --------------------------------------------------------------------------
-- evaluations
-- --------------------------------------------------------------------------
create table if not exists public.evaluations (
  id                 uuid        primary key default gen_random_uuid(),
  project_id         uuid        not null references public.projects (id) on delete cascade,
  spec_id            uuid        not null references public.intelligence_specs (id) on delete cascade,
  -- plain uuid for now: FK to dataset_versions lands in a later phase.
  dataset_version_id uuid        not null,
  name               text        not null,
  status             text        not null default 'PENDING'
                     check (status in ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
  results            jsonb,
  created_at         timestamptz not null default now(),
  completed_at       timestamptz
);

create index if not exists evaluations_project_id_idx
  on public.evaluations (project_id);
create index if not exists evaluations_spec_id_idx
  on public.evaluations (spec_id);

-- --------------------------------------------------------------------------
-- deployments
-- --------------------------------------------------------------------------
create table if not exists public.deployments (
  id               uuid        primary key default gen_random_uuid(),
  project_id       uuid        not null references public.projects (id) on delete cascade,
  spec_id          uuid        not null references public.intelligence_specs (id) on delete cascade,
  model_version_id uuid,
  name             text        not null,
  status           text        not null default 'DRAFT'
                   check (status in ('DRAFT', 'ACTIVE', 'PAUSED', 'ARCHIVED')),
  endpoint_url     text,
  config           jsonb       not null default '{}',
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index if not exists deployments_project_id_idx
  on public.deployments (project_id);
create index if not exists deployments_spec_id_idx
  on public.deployments (spec_id);

drop trigger if exists deployments_touch_updated_at on public.deployments;
create trigger deployments_touch_updated_at
  before update on public.deployments
  for each row execute function public.touch_updated_at();

-- --------------------------------------------------------------------------
-- usage_events
-- --------------------------------------------------------------------------
create table if not exists public.usage_events (
  id          uuid        primary key default gen_random_uuid(),
  project_id  uuid        not null references public.projects (id) on delete cascade,
  scope       text        not null
              check (scope in (
                'project', 'experiment', 'candidate', 'training_job',
                'model', 'deployment', 'inference'
              )),
  scope_id    uuid,
  kind        text        not null
              check (kind in ('training', 'inference', 'evaluation', 'storage')),
  quantity    double precision not null default 0,
  unit        text        not null default '',
  cost_usd    double precision not null default 0,
  recorded_at timestamptz not null default now()
);

create index if not exists usage_events_project_id_idx
  on public.usage_events (project_id);

-- --------------------------------------------------------------------------
-- Row Level Security (mirror of migration 001: org-scoped via
-- public.current_organization_id(), joined through projects)
-- --------------------------------------------------------------------------

alter table public.intelligence_specs enable row level security;
alter table public.datasets            enable row level security;
alter table public.dataset_versions    enable row level security;
alter table public.training_jobs       enable row level security;
alter table public.training_runs       enable row level security;
alter table public.models              enable row level security;
alter table public.model_versions      enable row level security;
alter table public.evaluations         enable row level security;
alter table public.deployments         enable row level security;
alter table public.usage_events        enable row level security;

-- Tables with a direct project_id: full CRUD within the caller's org.
drop policy if exists "specs_all_own_org" on public.intelligence_specs;
create policy "specs_all_own_org"
  on public.intelligence_specs for all
  to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = intelligence_specs.project_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.projects p
    where p.id = intelligence_specs.project_id
      and p.organization_id = public.current_organization_id()
  ));

drop policy if exists "datasets_all_own_org" on public.datasets;
create policy "datasets_all_own_org"
  on public.datasets for all
  to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = datasets.project_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.projects p
    where p.id = datasets.project_id
      and p.organization_id = public.current_organization_id()
  ));

drop policy if exists "training_jobs_all_own_org" on public.training_jobs;
create policy "training_jobs_all_own_org"
  on public.training_jobs for all
  to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = training_jobs.project_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.projects p
    where p.id = training_jobs.project_id
      and p.organization_id = public.current_organization_id()
  ));

drop policy if exists "models_all_own_org" on public.models;
create policy "models_all_own_org"
  on public.models for all
  to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = models.project_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.projects p
    where p.id = models.project_id
      and p.organization_id = public.current_organization_id()
  ));

drop policy if exists "evaluations_all_own_org" on public.evaluations;
create policy "evaluations_all_own_org"
  on public.evaluations for all
  to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = evaluations.project_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.projects p
    where p.id = evaluations.project_id
      and p.organization_id = public.current_organization_id()
  ));

drop policy if exists "deployments_all_own_org" on public.deployments;
create policy "deployments_all_own_org"
  on public.deployments for all
  to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = deployments.project_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.projects p
    where p.id = deployments.project_id
      and p.organization_id = public.current_organization_id()
  ));

drop policy if exists "usage_events_all_own_org" on public.usage_events;
create policy "usage_events_all_own_org"
  on public.usage_events for all
  to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = usage_events.project_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.projects p
    where p.id = usage_events.project_id
      and p.organization_id = public.current_organization_id()
  ));

-- Child tables: scoped through their parent (datasets / training_jobs / models).
drop policy if exists "dataset_versions_all_own_org" on public.dataset_versions;
create policy "dataset_versions_all_own_org"
  on public.dataset_versions for all
  to authenticated
  using (exists (
    select 1 from public.datasets d
    join public.projects p on p.id = d.project_id
    where d.id = dataset_versions.dataset_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.datasets d
    join public.projects p on p.id = d.project_id
    where d.id = dataset_versions.dataset_id
      and p.organization_id = public.current_organization_id()
  ));

drop policy if exists "training_runs_all_own_org" on public.training_runs;
create policy "training_runs_all_own_org"
  on public.training_runs for all
  to authenticated
  using (exists (
    select 1 from public.training_jobs j
    join public.projects p on p.id = j.project_id
    where j.id = training_runs.job_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.training_jobs j
    join public.projects p on p.id = j.project_id
    where j.id = training_runs.job_id
      and p.organization_id = public.current_organization_id()
  ));

drop policy if exists "model_versions_all_own_org" on public.model_versions;
create policy "model_versions_all_own_org"
  on public.model_versions for all
  to authenticated
  using (exists (
    select 1 from public.models m
    join public.projects p on p.id = m.project_id
    where m.id = model_versions.model_id
      and p.organization_id = public.current_organization_id()
  ))
  with check (exists (
    select 1 from public.models m
    join public.projects p on p.id = m.project_id
    where m.id = model_versions.model_id
      and p.organization_id = public.current_organization_id()
  ));
