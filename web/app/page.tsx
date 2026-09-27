import { ArrowRight, FlaskConical, ListChecks, Rocket } from "lucide-react";
import Link from "next/link";
import { PipelineFlow } from "../components/PipelineFlow";
import { PrimitiveCards } from "../components/PrimitiveCards";

const ROADMAP = [
  {
    icon: ListChecks,
    phase: "Phase 0 — now",
    title: "Projects & identity",
    text: "Create projects, the containers that will hold every spec, dataset, and job. In-memory storage behind the Supabase-shaped model; honest stub auth.",
    current: true,
  },
  {
    icon: FlaskConical,
    phase: "Phase 1 — next",
    title: "Describe & diagnose",
    text: "Intelligence Specs, datasets, training jobs, and evaluations — the fabrication loop's first real machinery.",
    current: false,
  },
  {
    icon: Rocket,
    phase: "Later",
    title: "Deploy & improve",
    text: "Production artifacts, discovery of better candidates from production data, and the compound loop.",
    current: false,
  },
] as const;

export default function Home() {
  return (
    <div>
      {/* Hero — platinum surface, charcoal foreground (brand primary). */}
      <section
        aria-labelledby="hero-heading"
        className="bg-platinum text-charcoal"
      >
        <div className="mx-auto max-w-6xl px-4 pt-16 pb-14 sm:px-6 sm:pt-24 sm:pb-20">
          <p className="text-sm font-semibold tracking-[0.2em] uppercase">
            Intelligence Fabrication &amp; Discovery Platform
          </p>
          <h1
            id="hero-heading"
            className="mt-4 max-w-3xl font-display text-4xl font-bold tracking-tight text-balance sm:text-6xl"
          >
            Fabricate the smallest, cheapest, fastest,{" "}
            <span className="underline decoration-charcoal/40 decoration-4 underline-offset-8">
              sufficiently capable
            </span>{" "}
            intelligence.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-ink">
            Rustenwer is the platform for fabricating intelligence. Describe a
            problem that needs intelligent behavior, and Rustenwer determines
            how to construct, train, evaluate, and deploy the cheapest
            intelligence that solves it — not a bigger model, the{" "}
            <em>right-sized</em> one.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Link
              href="/projects"
              className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-charcoal px-6 py-3 text-base font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft"
            >
              Open projects
              <ArrowRight className="h-5 w-5" aria-hidden="true" />
            </Link>
            <Link
              href="#how-it-works"
              className="inline-flex min-h-[44px] items-center justify-center rounded-lg border-2 border-charcoal px-6 py-3 text-base font-semibold text-charcoal transition-colors duration-200 hover:bg-charcoal/5"
            >
              How it works
            </Link>
          </div>
        </div>
      </section>

      {/* Flow visualization */}
      <section
        id="how-it-works"
        aria-labelledby="flow-heading"
        className="mx-auto max-w-6xl scroll-mt-20 px-4 py-14 sm:px-6 sm:py-20"
      >
        <h2
          id="flow-heading"
          className="font-display text-3xl font-bold tracking-tight text-charcoal"
        >
          The fabrication flow
        </h2>
        <p className="mt-3 max-w-2xl text-base leading-7 text-muted-ink">
          Every intelligence Rustenwer produces travels the same pipeline. Each
          step is explicit, reviewable, and measured — no magic, no black boxes.
        </p>
        <div className="mt-8">
          <PipelineFlow />
        </div>
      </section>

      {/* Intelligence Primitives */}
      <section
        aria-labelledby="primitives-heading"
        className="border-y border-line bg-platinum/40"
      >
        <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
          <h2
            id="primitives-heading"
            className="font-display text-3xl font-bold tracking-tight text-charcoal"
          >
            Intelligence Primitives
          </h2>
          <p className="mt-3 max-w-2xl text-base leading-7 text-muted-ink">
            Rustenwer doesn't hand-build one-off models. It composes{" "}
            <strong className="font-semibold text-charcoal">
              Intelligence Primitives
            </strong>{" "}
            — reusable cognitive operations, each with measured cost, latency,
            and quality — into exactly the intelligence your problem needs.
          </p>
          <div className="mt-8">
            <PrimitiveCards />
          </div>
          <p className="mt-6 text-sm text-muted-ink">
            …and fourteen more: filtering, search, retrieval, routing, critique,
            diagnosis, planning, optimization, compression, memory selection,
            iteration control, termination, exploration, and selection.
          </p>
        </div>
      </section>

      {/* Phase 0 note + roadmap */}
      <section
        aria-labelledby="roadmap-heading"
        className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20"
      >
        <h2
          id="roadmap-heading"
          className="font-display text-3xl font-bold tracking-tight text-charcoal"
        >
          Where we are
        </h2>
        <div className="mt-4 rounded-xl border border-line bg-card p-6">
          <p className="text-base leading-7 text-ink">
            <strong className="font-semibold text-charcoal">
              Honest Phase 0 note:
            </strong>{" "}
            this site currently manages <em>projects</em> — the containers that
            will hold specs, datasets, and jobs. Auth is a clearly marked stub,
            storage is in-memory, and there are no agents yet. The fabrication
            pipeline above is the plan, not the product. What you see is what
            exists.
          </p>
        </div>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {ROADMAP.map((r) => {
            const Icon = r.icon;
            return (
              <article
                key={r.phase}
                className={`rounded-xl border p-6 ${
                  r.current
                    ? "border-charcoal bg-platinum"
                    : "border-line bg-card"
                }`}
                aria-current={r.current ? "step" : undefined}
              >
                <span
                  className={`flex h-11 w-11 items-center justify-center rounded-lg ${
                    r.current
                      ? "bg-charcoal text-platinum"
                      : "bg-platinum text-charcoal"
                  }`}
                  aria-hidden="true"
                >
                  <Icon className="h-5 w-5" />
                </span>
                <p className="mt-4 text-xs font-semibold tracking-[0.15em] text-muted-ink uppercase">
                  {r.phase}
                </p>
                <h3 className="mt-1 font-display text-lg font-bold text-charcoal">
                  {r.title}
                </h3>
                <p className="mt-2 text-sm leading-6 text-muted-ink">
                  {r.text}
                </p>
              </article>
            );
          })}
        </div>
        <div className="mt-10 text-center">
          <Link
            href="/projects"
            className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-charcoal px-6 py-3 text-base font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft"
          >
            Start with a project
            <ArrowRight className="h-5 w-5" aria-hidden="true" />
          </Link>
        </div>
      </section>
    </div>
  );
}
