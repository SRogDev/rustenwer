-- ============================================================================
-- Rustenwer — Migration 005: Phase 5 training-method knowledge
-- ============================================================================
-- Canonical schema for the Phase 5 method catalog (plan §10, §11, §52–§54):
--
--   training_methods   — structured, versioned training-method knowledge
--     (slug, name, category, version, status, supported_tasks,
--     data/compute requirements, strengths/weaknesses/failure_modes,
--     compatible architectures/objectives, evaluation requirements,
--     implementation templates, locally_runnable, notes). A new version is
--     a NEW row — (slug, version) is unique, versions are never edited.
--   adapter_registry   — method version -> executor linkage (which
--     TrainingMethodAdapter runs it, plan §54).
--   research_findings  — distilled research knowledge (plan §52): technique,
--     when it helps, what it needs, where it wins and where it breaks.
--
-- NOTE: the API runs on in-memory repositories (no Supabase credentials yet);
-- this migration is the canonical schema for the later swap (same convention
-- as 001–004).
-- ============================================================================

-- --------------------------------------------------------------------------
-- training_methods — the §11 structured representation, versioned
-- --------------------------------------------------------------------------
create table if not exists public.training_methods (
  id                       uuid        primary key default gen_random_uuid(),
  slug                     text        not null,
  name                     text        not null,
  category                 text        not null,   -- MethodCategory (§10)
  version                  integer     not null default 1,
  status                   text        not null default 'KNOWN'
                           check (status in ('VALIDATED', 'KNOWN')),
  supported_tasks          text[]      not null default '{}',
  data_requirements        jsonb       not null default '{}'::jsonb,
  compute_requirements     jsonb       not null default '{}'::jsonb,
  strengths                text[]      not null default '{}',
  weaknesses               text[]      not null default '{}',
  failure_modes            text[]      not null default '{}',
  compatible_architectures text[]      not null default '{}',
  compatible_objectives    text[]      not null default '{}',
  evaluation_requirements  text[]      not null default '{}',
  implementation_templates text[]      not null default '{}',
  locally_runnable         boolean     not null default false,
  notes                    text        not null default '',
  created_at               timestamptz not null default now(),
  unique (slug, version)
);

create index if not exists training_methods_slug_idx
  on public.training_methods (slug);
create index if not exists training_methods_status_idx
  on public.training_methods (status);

-- --------------------------------------------------------------------------
-- adapter_registry — method version -> executor linkage (plan §54)
-- --------------------------------------------------------------------------
create table if not exists public.adapter_registry (
  id               uuid        primary key default gen_random_uuid(),
  method_slug      text        not null,
  method_version   integer     not null default 1,
  adapter_name     text        not null,  -- key in the adapter registry
  template_ref     text        not null default '',
  locally_runnable boolean     not null default false,
  notes            text        not null default '',
  created_at       timestamptz not null default now(),
  unique (method_slug, method_version)
);

-- --------------------------------------------------------------------------
-- research_findings — distilled research knowledge (plan §52)
-- --------------------------------------------------------------------------
create table if not exists public.research_findings (
  id           uuid        primary key default gen_random_uuid(),
  technique    text        not null,
  useful_for   text[]      not null default '{}',
  requires     text[]      not null default '{}',
  advantage    text        not null default '',
  weakness     text        not null default '',
  source       text        not null default '',
  version      integer     not null default 1,
  created_at   timestamptz not null default now(),
  unique (technique, version)
);
