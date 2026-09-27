import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="border-t border-line bg-charcoal text-platinum">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-10 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <p className="font-display text-lg font-bold tracking-tight">
            Rustenwer
          </p>
          <p className="mt-1 max-w-md text-sm text-platinum/80">
            Intelligence Fabrication &amp; Discovery Platform. Phase 0 —
            projects and identity; the intelligence lifecycle lands in Phase 1.
          </p>
        </div>
        <nav aria-label="Footer">
          <ul className="flex items-center gap-2">
            <li>
              <Link
                href="/"
                className="flex min-h-[44px] items-center rounded-md px-3 text-sm font-medium text-platinum/90 transition-colors duration-200 hover:bg-white/10 hover:text-platinum"
              >
                Home
              </Link>
            </li>
            <li>
              <Link
                href="/projects"
                className="flex min-h-[44px] items-center rounded-md px-3 text-sm font-medium text-platinum/90 transition-colors duration-200 hover:bg-white/10 hover:text-platinum"
              >
                Projects
              </Link>
            </li>
          </ul>
        </nav>
      </div>
    </footer>
  );
}
