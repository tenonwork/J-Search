import { Radar, Sparkles } from 'lucide-react';

export default function EmptyState({ title, message }) {
  return (
    <div className="glass-panel relative overflow-hidden px-6 py-16 text-center">
      <div className="pointer-events-none absolute left-1/2 top-0 h-48 w-72 -translate-x-1/2 rounded-full bg-cyan-400/[0.07] blur-3xl" />
      <div className="relative mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.06] shadow-[0_0_40px_-12px_rgba(34,211,238,0.3)]">
        <Radar className="h-6 w-6 text-cyan-300" />
        <Sparkles className="absolute -right-1 -top-1 h-3.5 w-3.5 text-cyan-200/70" />
      </div>
      <h3 className="relative mt-5 text-[15px] font-semibold text-slate-200">{title}</h3>
      <p className="relative mx-auto mt-2 max-w-md text-[12px] leading-relaxed text-slate-500">{message}</p>
    </div>
  );
}
