# Rustenwer web (Phase 0)

Next.js 15 + React 19 + TypeScript (strict) + Tailwind CSS v4 + Biome.
Brand: platinum `#E5E4E2` primary, charcoal `#16161A` foreground.

## Develop

```bash
cp .env.example .env.local   # never commit .env.local
npm install
npm run dev                  # http://localhost:3000
```

The API client (`lib/api.ts`) reads `NEXT_PUBLIC_API_URL`
(default `http://localhost:8000`) and sends
`Authorization: Bearer phase0-dev-token`. If the API is unreachable, pages
serve the labeled mock dataset and show an "API offline" banner.

## Verify

```bash
npm run lint     # biome check . — must be 0 errors
npm run format   # biome check --write .
npm run build    # must be 0 errors
```

Domain types come from `../shared/types.ts` via `import type`
(type-only, erased at build). Keep them in sync with `shared/domain.py`
(see `../shared/README.md`).
