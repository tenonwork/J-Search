export default function Logo({ className = 'h-12 w-12' }) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={className}
      role="img"
      aria-label="J-Search logo"
    >
      <defs>
        <linearGradient id="js-mark" x1="10" y1="55" x2="56" y2="9" gradientUnits="userSpaceOnUse">
          <stop stopColor="#1d4ed8" />
          <stop offset="0.48" stopColor="#2563eb" />
          <stop offset="1" stopColor="#22d3ee" />
        </linearGradient>
        <linearGradient id="js-tail" x1="37" y1="43" x2="55" y2="57" gradientUnits="userSpaceOnUse">
          <stop stopColor="#2563eb" />
          <stop offset="1" stopColor="#22d3ee" />
        </linearGradient>
        <filter id="js-glow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="2.2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <rect x="0.75" y="0.75" width="62.5" height="62.5" rx="17" fill="#0e1421" stroke="rgba(255,255,255,0.09)" />
      <rect x="0.75" y="0.75" width="62.5" height="62.5" rx="17" fill="url(#js-mark)" opacity="0.06" />

      <g filter="url(#js-glow)" fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path
          d="M14.5 37.5c-5.4 12.8 13.4 18.3 20.3 6.2l7.2-13.6c4.6-9.3 15.5-5.7 15.5 3.3 0 9.3-11.2 14.4-18 8.2-6.5-5.8-2.7-17.1 7.5-19.4"
          stroke="url(#js-mark)"
          strokeWidth="7.4"
        />
        <path d="M35.2 43.6 48.6 56" stroke="url(#js-tail)" strokeWidth="7.4" />
      </g>

      <path
        d="M17 36.2c-3.2 8.2 6.8 12.3 12.8 6.2"
        fill="none"
        stroke="rgba(255,255,255,0.24)"
        strokeWidth="1.15"
        strokeLinecap="round"
      />
    </svg>
  );
}
