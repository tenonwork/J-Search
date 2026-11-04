import { scoreTone } from '../lib/utils';

export default function ScoreRing({ score, size = 'md' }) {
  const tone = scoreTone(score);
  const radius = 25;
  const circumference = 2 * Math.PI * radius;
  const dash = (tone.value / 100) * circumference;
  const box = size === 'lg' ? 'h-24 w-24' : 'h-[74px] w-[74px]';
  const valueText = size === 'lg' ? 'text-3xl' : 'text-[22px]';
  const labelText = size === 'lg' ? 'text-[9px]' : 'text-[8px]';

  return (
    <div className={`relative shrink-0 ${box}`} title={`Match score ${tone.value} of 100`}>
      <div
        className="absolute inset-2 rounded-full blur-xl opacity-30"
        style={{ backgroundColor: tone.color }}
      />
      <svg viewBox="0 0 64 64" className="relative h-full w-full -rotate-90">
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          stroke="rgba(148,163,184,0.12)"
          strokeWidth="4.5"
        />
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          stroke={tone.color}
          strokeWidth="4.5"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          style={{
            filter: `drop-shadow(0 0 5px ${tone.glow})`,
            transition: 'stroke-dasharray 600ms cubic-bezier(0.22, 1, 0.36, 1)',
          }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className={`${valueText} font-semibold tabular-nums leading-none tracking-tight`}
          style={{ color: tone.color }}
        >
          {tone.value}
        </span>
        <span className={`${labelText} mt-1 font-semibold uppercase tracking-[0.2em] text-slate-500`}>
          Match
        </span>
      </div>
    </div>
  );
}
