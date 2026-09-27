import Link from "next/link";

/** Brand mark: platinum "R" on charcoal. No emojis — pure SVG. */
export function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="Rustenwer logo"
    >
      <rect width="32" height="32" rx="8" fill="#E5E4E2" />
      <path
        d="M10 23V9h6.2c3 0 5.3 1.9 5.3 4.9 0 2.1-1.1 3.6-2.9 4.3L22.4 23h-3.6l-3.2-4.2H13V23H10Zm3-6.6h3.1c1.6 0 2.5-.9 2.5-2.3 0-1.4-.9-2.3-2.5-2.3H13v4.6Z"
        fill="#16161A"
      />
    </svg>
  );
}

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-paper/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Link
          href="/"
          className="flex min-h-[44px] items-center gap-3 rounded-md"
          aria-label="Rustenwer home"
        >
          <BrandMark />
          <span className="font-display text-xl font-bold tracking-tight text-charcoal">
            Rustenwer
          </span>
        </Link>
        <nav aria-label="Primary">
          <ul className="flex items-center gap-1 sm:gap-2">
            <li>
              <Link
                href="/"
                className="flex min-h-[44px] items-center rounded-md px-3 text-sm font-medium text-ink transition-colors duration-200 hover:bg-platinum"
              >
                Home
              </Link>
            </li>
            <li>
              <Link
                href="/methods"
                className="flex min-h-[44px] items-center rounded-md px-3 text-sm font-medium text-ink transition-colors duration-200 hover:bg-platinum"
              >
                Methods
              </Link>
            </li>
            <li>
              <Link
                href="/projects"
                className="flex min-h-[44px] items-center rounded-md bg-charcoal px-4 text-sm font-semibold text-platinum transition-colors duration-200 hover:bg-charcoal-soft"
              >
                Projects
              </Link>
            </li>
          </ul>
        </nav>
      </div>
    </header>
  );
}
