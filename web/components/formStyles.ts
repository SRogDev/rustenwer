/**
 * Shared form styling for the Rustenwer web UI.
 * Platinum theme; min 44px touch targets; visible focus is global
 * (:focus-visible in globals.css).
 */
export const INPUT_STYLES =
  "w-full min-h-[44px] rounded-lg border border-line bg-paper px-3 py-2 text-sm text-charcoal transition-colors duration-200 focus:border-charcoal disabled:opacity-60";

export const LABEL_STYLES = "mb-1.5 block text-sm font-semibold text-charcoal";

export const HINT_STYLES = "mt-1 text-xs leading-5 text-muted-ink";

export const BUTTON_PRIMARY =
  "inline-flex min-h-[44px] cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-platinum transition-opacity duration-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60";

export const BUTTON_SECONDARY =
  "inline-flex min-h-[44px] cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-line bg-paper px-4 py-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum disabled:cursor-not-allowed disabled:opacity-60";

export const BUTTON_DANGER =
  "inline-flex min-h-[44px] cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-[#DC2626]/30 bg-[#DC2626]/10 px-4 py-2 text-sm font-semibold text-[#8f1d1d] transition-colors duration-200 hover:bg-[#DC2626]/20 disabled:cursor-not-allowed disabled:opacity-60";

export const ERROR_STYLES =
  "rounded-lg border border-[#DC2626]/30 bg-[#DC2626]/10 px-3 py-2 text-sm text-[#8f1d1d]";
