export const PAGE_SIZE = 10;

/**
 * Slice a job list into one page.
 * Pages are 1-based and clamped so an out-of-range page still returns data.
 */
export function paginate(items, page, pageSize = PAGE_SIZE) {
  const list = Array.isArray(items) ? items : [];
  const totalPages = Math.max(1, Math.ceil(list.length / pageSize));
  const current = Math.min(Math.max(1, Number(page) || 1), totalPages);
  const start = (current - 1) * pageSize;
  return {
    items: list.slice(start, start + pageSize),
    page: current,
    totalPages,
    total: list.length,
    start: list.length ? start + 1 : 0,
    end: Math.min(start + pageSize, list.length),
  };
}

/**
 * Page numbers to render, with "gap" markers for long lists.
 * Returns numbers and the string 'gap' (keys are derived by the caller).
 */
export function pageWindow(current, totalPages, siblings = 1) {
  const total = Math.max(1, totalPages);
  const active = Math.min(Math.max(1, current), total);
  const pages = new Set([1, total]);
  for (let offset = -siblings; offset <= siblings; offset += 1) {
    const value = active + offset;
    if (value > 1 && value < total) pages.add(value);
  }
  const sorted = [...pages].sort((a, b) => a - b);
  const out = [];
  sorted.forEach((value, index) => {
    if (index > 0 && value - sorted[index - 1] > 1) out.push('gap');
    out.push(value);
  });
  return out;
}
