import { ChevronLeft, ChevronRight, MoreHorizontal } from 'lucide-react';
import { pageWindow } from '../lib/pagination';

export default function Pagination({ page, totalPages, total, start, end, onPageChange }) {
  if (!total) return null;

  const pages = pageWindow(page, totalPages, 2);
  const atStart = page <= 1;
  const atEnd = page >= totalPages;

  return (
    <nav
      aria-label="Job results pages"
      className="glass-panel flex flex-col items-center gap-3 px-4 py-3 sm:flex-row sm:justify-between sm:px-5"
    >
      <p className="text-[10px] text-slate-500">
        Showing <span className="font-semibold tabular-nums text-slate-300">{start}–{end}</span> of{' '}
        <span className="font-semibold tabular-nums text-slate-300">{total}</span> roles
        <span className="mx-1.5 text-slate-700">·</span>
        <span className="tabular-nums">
          Page {page} of {totalPages}
        </span>
      </p>

      <div className="flex flex-wrap items-center justify-center gap-1">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={atStart}
          className="page-btn gap-1 pr-2.5"
          aria-label="Previous page"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Prev</span>
        </button>

        {pages.map((value, index) =>
          value === 'gap' ? (
            <span
              key={`gap-${index}`}
              aria-hidden="true"
              className="inline-flex h-8 w-6 items-center justify-center text-slate-600"
            >
              <MoreHorizontal className="h-3.5 w-3.5" />
            </span>
          ) : (
            <button
              key={value}
              type="button"
              onClick={() => onPageChange(value)}
              aria-label={`Page ${value}`}
              aria-current={value === page ? 'page' : undefined}
              className={`page-btn ${value === page ? 'page-btn-active' : ''}`}
            >
              {value}
            </button>
          ),
        )}

        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={atEnd}
          className="page-btn gap-1 pl-2.5"
          aria-label="Next page"
        >
          <span className="hidden sm:inline">Next</span>
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </nav>
  );
}
