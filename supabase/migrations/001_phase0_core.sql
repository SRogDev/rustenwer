-- ============================================================================
-- Rustenwer — Migration 001: Phase 0 core entities
-- ============================================================================
-- Creates: organizations, users, projects (product plan §41, Phase 0 scope).
--
-- FULL ENTITY LIST (for later phases — DO NOT create yet):
--   Phase 1: intelligence_specs, datasets, dataset_versions, training_jobs,
--            training_runs, models, model_versions, evaluations, deployments
--   Phase 3: evaluation_runs, intelligences, intelligence_versions,
--            inference_endpoints, usage
--   Phase 4: intelligence_architectures
--   Phase 5: training_strategies, training_methods (+ registry)
--   Phase 6: experiments, experiment_candidates
--   Phase 7: discovery_runs, discovery_events, experiment_memory
--   Phase 8: rsi_runs, rsi_candidates, rsi_mutations
--   Always: infrastructure, billing, audit_events
-- ============================================================================

-- --------------------------------------------------------------------------
-- organizations
-- --------------------------------------------------------------------------
create table if not exists public.organizations (
  id          uuid        primary key default gen_random_uuid(),
  name        text        not null,
  slug        text        not null unique,
  created_at  timestamptz not null default now()
);

-- --------------------------------------------------------------------------
-- users  (profile rows linked 1:1 to Supabase auth.users)
-- --------------------------------------------------------------------------
create table if not exists public.users (
  id              uuid        primary key references auth.users (id) on delete cascade,
  organization_id uuid        not null references public.organizations (id) on delete restrict,
  email           text        not null,
  display_name    text,
  role            text        not null default 'member'
                  check (role in ('owner', 'admin', 'member')),
  created_at      timestamptz not null default now()
);

-- --------------------------------------------------------------------------
-- projects
-- --------------------------------------------------------------------------
create table if not exists public.projects (
  id              uuid        primary key default gen_random_uuid(),
  organization_id uuid        not null references public.organizations (id) on delete cascade,
  name            text        not null,
  description     text,
  status          text        not null default 'ACTIVE'
                  check (status in ('ACTIVE', 'PAUSED', 'ARCHIVED')),
  created_by      uuid        references public.users (id) on delete set null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists projects_organization_id_idx
  on public.projects (organization_id);

-- keep updated_at fresh
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists projects_touch_updated_at on public.projects;
create trigger projects_touch_updated_at
  before update on public.projects
  for each row execute function public.touch_updated_at();

-- --------------------------------------------------------------------------
-- Row Level Security
-- --------------------------------------------------------------------------
alter table public.organizations enable row level security;
alter table public.users        enable row level security;
alter table public.projects     enable row level security;

-- Helper: organization of the current JWT subject (SECURITY DEFINER so the
-- policy check itself does not recurse into RLS).
create or replace function public.current_organization_id()
returns uuid
language sql
security definer
stable
as $$
  select organization_id
  from public.users
  where id = auth.uid()
$$;

-- Organizations: members can read their own org.
drop policy if exists "org_read_own" on public.organizations;
create policy "org_read_own"
  on public.organizations for select
  to authenticated
  using (id = public.current_organization_id());

-- Users: members can read users of their own org.
drop policy if exists "users_read_own_org" on public.users;
create policy "users_read_own_org"
  on public.users for select
  to authenticated
  using (organization_id = public.current_organization_id());

-- Projects: full CRUD within the caller's organization.
drop policy if exists "projects_all_own_org" on public.projects;
create policy "projects_all_own_org"
  on public.projects for all
  to authenticated
  using (organization_id = public.current_organization_id())
  with check (organization_id = public.current_organization_id());
