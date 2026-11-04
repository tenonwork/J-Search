import { ArrowUpDown, ChevronDown, Filter, Globe2, MapPin } from 'lucide-react';

const STRICTNESS = [
  { value: 'strict', label: 'Strict' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'lenient', label: 'Lenient' },
];

export default function FilterBar({
  tab,
  onTabChange,
  counts,
  strictness,
  onStrictnessChange,
  sortOrder,
  onSortChange,
  visibleCount,
}) {
  return (
    <div className="glass-panel sticky top-3 z-20 flex flex-col gap-4 px-4 py-3 sm:px-5 xl:flex-row xl:items-center xl:justify-between">
      <div className="flex flex-wrap items-center gap-3">
        <div className="segment" role="tablist" aria-label="Job scope">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'global'}
            onClick={() => onTabChange('global')}
            className={`segment-item ${tab === 'global' ? 'segment-item-active' : ''}`}
          >
            <Globe2 className="h-3.5 w-3.5" />
            Global
            <span className={`segment-count ${tab === 'global' ? 'segment-count-active' : ''}`}>
              {counts.global}
            </span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'local'}
            onClick={() => onTabChange('local')}
            className={`segment-item ${tab === 'local' ? 'segment-item-active' : ''}`}
          >
            <MapPin className="h-3.5 w-3.5" />
            Local
            <span className={`segment-count ${tab === 'local' ? 'segment-count-active' : ''}`}>
              {counts.local}
            </span>
          </button>
        </div>

        <span className="hidden h-5 w-px bg-white/[0.07] sm:block" />
        <span className="text-[10px] font-medium uppercase tracking-[0.16em] text-slate-600">
          {visibleCount} visible
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-slate-600" />
          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Strictness</span>
          <div className="segment" role="radiogroup" aria-label="Match strictness">
            {STRICTNESS.map((option) => (
              <button
                type="button"
                role="radio"
                aria-checked={strictness === option.value}
                key={option.value}
                onClick={() => onStrictnessChange(option.value)}
                className={`segment-item px-2.5 text-[11px] ${strictness === option.value ? 'segment-item-active' : ''}`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <ArrowUpDown className="h-3.5 w-3.5 text-slate-600" />
          <div className="relative">
            <select
              value={sortOrder}
              onChange={(event) => onSortChange(event.target.value)}
              className="select-dark min-w-[176px] appearance-none pr-8 text-[11px]"
              aria-label="Sort jobs"
            >
              <option value="recommended">Most recommended first</option>
              <option value="newest">Newest first</option>
              <option value="lowest">Lowest match first</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
          </div>
        </div>
      </div>
    </div>
  );
}
