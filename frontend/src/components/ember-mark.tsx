export function EmberMark({ className = "size-[18px]" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`shrink-0 text-primary ${className}`} aria-hidden="true">
      <circle cx="12" cy="5.5" r="2.4" fill="currentColor" />
      <circle cx="5" cy="18" r="2.4" fill="currentColor" opacity="0.55" />
      <circle cx="19" cy="18" r="2.4" fill="currentColor" opacity="0.85" />
    </svg>
  );
}
