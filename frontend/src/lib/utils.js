export function cx(...values) {
  return values.filter(Boolean).join(' ');
}

export function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function skillMatches(text, skill) {
  const needle = String(skill || '').toLowerCase().trim();
  if (!needle) return false;
  if (/^[a-z0-9]+(?:[ /-][a-z0-9]+)*$/.test(needle)) {
    try {
      return new RegExp(`\\b${escapeRegExp(needle)}\\b`).test(text);
    } catch {
      return text.includes(needle);
    }
  }
  return text.includes(needle);
}

export function enabledValues(filters, type) {
  return (filters[type] || []).filter((item) => item.enabled).map((item) => item.value);
}

export function keywordsForScope(keywords, scope) {
  return keywords?.[scope] || { focus: [], exclude: [] };
}

export function isFocused(job, filters) {
  const text = `${job.title || ''} ${job.desc || ''}`.toLowerCase();
  return enabledValues(filters, 'focus').some((keyword) => skillMatches(text, keyword));
}

export function passesFilters(job, filters, strictness) {
  const text = `${job.title || ''} ${job.desc || ''}`.toLowerCase();

  for (const keyword of enabledValues(filters, 'exclude')) {
    if (skillMatches(text, keyword)) return false;
  }

  if (strictness === 'strict') {
    if (job.redFlags && job.redFlags.length) return false;
    if (job.source === 'global' && job.score < 10) return false;
    if (job.source === 'local' && job.score < 3) return false;
  } else if (strictness === 'balanced') {
    if (job.source === 'global' && job.redFlags && job.redFlags.length) return false;
    if (job.source === 'global' && job.score < 5) return false;
    if (job.source === 'local' && job.score < 0) return false;
  }
  return true;
}

export function sortJobs(jobs, sortOrder) {
  const sorted = [...jobs];
  if (sortOrder === 'lowest') {
    return sorted.sort((a, b) => a.score - b.score);
  }
  if (sortOrder === 'newest') {
    return sorted.sort((a, b) => (b.id ?? 0) - (a.id ?? 0));
  }
  return sorted.sort((a, b) => b.score - a.score);
}

export function scoreTone(score) {
  const value = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));
  if (value >= 80) {
    return {
      value,
      color: '#34d399',
      glow: 'rgba(52, 211, 153, 0.35)',
      label: 'Strong',
    };
  }
  if (value >= 50) {
    return {
      value,
      color: '#22d3ee',
      glow: 'rgba(34, 211, 238, 0.35)',
      label: 'Good',
    };
  }
  return {
    value,
    color: '#64748b',
    glow: 'rgba(100, 116, 139, 0.25)',
    label: 'Low',
  };
}

export function pluralize(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}
