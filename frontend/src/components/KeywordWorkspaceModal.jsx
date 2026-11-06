import { useEffect, useMemo, useState } from 'react';
import {
  Eye,
  EyeOff,
  Gauge,
  Loader2,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Save,
  Search,
  SlidersHorizontal,
  Sparkles,
  Tag,
  X,
} from 'lucide-react';
import Modal from './Modal';
import { api } from '../lib/api';

const SCOPES = ['global', 'local'];

const TONES = {
  cyan: {
    accent: '#22d3ee',
    dot: 'bg-cyan-400',
    badge: 'border-cyan-400/25 bg-cyan-400/[0.1] text-cyan-100',
    row: 'border-cyan-400/15 bg-cyan-400/[0.04]',
  },
  blue: {
    accent: '#60a5fa',
    dot: 'bg-blue-400',
    badge: 'border-blue-400/25 bg-blue-500/[0.11] text-blue-100',
    row: 'border-blue-400/15 bg-blue-500/[0.05]',
  },
  emerald: {
    accent: '#34d399',
    dot: 'bg-emerald-400',
    badge: 'border-emerald-400/25 bg-emerald-500/[0.1] text-emerald-100',
    row: 'border-emerald-400/15 bg-emerald-500/[0.04]',
  },
  amber: {
    accent: '#fbbf24',
    dot: 'bg-amber-400',
    badge: 'border-amber-400/25 bg-amber-500/[0.1] text-amber-100',
    row: 'border-amber-400/15 bg-amber-500/[0.04]',
  },
  rose: {
    accent: '#fb7185',
    dot: 'bg-rose-400',
    badge: 'border-rose-400/25 bg-rose-500/[0.1] text-rose-100',
    row: 'border-rose-400/15 bg-rose-500/[0.04]',
  },
};

const BEHAVIORS = [
  { value: 'focus', label: 'Highlight', hint: 'Highlight + score' },
  { value: 'exclude', label: 'Hide', hint: 'Hide + score' },
  { value: 'score', label: 'Score only', hint: 'Score only' },
];

function signed(value) {
  if (value > 0) return `+${value}`;
  if (value < 0) return `−${Math.abs(value)}`;
  return '0';
}

function clampWeight(group, value) {
  const parsed = Number(value);
  const safe = Number.isFinite(parsed) ? parsed : 0;
  return Math.max(group.min, Math.min(group.max, Math.round(safe)));
}

function cleanKeyword(value) {
  return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim().slice(0, 60);
}

function behaviorLabel(type) {
  return BEHAVIORS.find((item) => item.value === type)?.label || 'Highlight';
}

function normalizeRow(row) {
  const value = cleanKeyword(row.value);
  if (!value) return null;
  const weightGroup = row.weight_group || '';
  let type = row.type || 'focus';
  if (!BEHAVIORS.some((item) => item.value === type)) type = 'focus';
  if (!weightGroup && type === 'score') type = 'focus';
  return {
    value,
    weight_group: weightGroup,
    type,
    enabled: row.enabled !== false,
  };
}

function rowsForSave(rows) {
  const seen = new Set();
  const out = [];
  rows.forEach((row) => {
    const clean = normalizeRow(row);
    if (!clean || seen.has(clean.value)) return;
    seen.add(clean.value);
    out.push(clean);
  });
  return out;
}

function RowControls({ row, groups, onChange, onDelete }) {
  const weighted = !!row.weight_group;
  return (
    <>
      <button
        type="button"
        onClick={() => onChange({ enabled: !row.enabled })}
        title={row.enabled ? 'Pause this keyword' : 'Resume this keyword'}
        aria-label={row.enabled ? `Pause ${row.value}` : `Resume ${row.value}`}
        className={`rounded p-1 transition hover:bg-white/10 ${
          row.enabled ? 'text-slate-500 hover:text-slate-200' : 'text-amber-300'
        }`}
      >
        {row.enabled ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
      </button>
      <span
        className={`min-w-0 flex-1 truncate text-[11px] ${
          row.enabled ? 'text-slate-200' : 'text-slate-500 line-through decoration-slate-700'
        }`}
        title={row.value}
      >
        {row.value}
      </span>
      {!row.enabled && (
        <span className="rounded bg-white/5 px-1 py-0.5 text-[8px] font-semibold uppercase tracking-wider text-amber-300/80">
          paused
        </span>
      )}
      <select
        value={row.type}
        onChange={(event) => onChange({ type: event.target.value })}
        aria-label={`Behavior for ${row.value}`}
        title={BEHAVIORS.find((item) => item.value === row.type)?.hint}
        className="h-6 shrink-0 rounded border border-white/[0.07] bg-[#0d1320] px-1 text-[9px] text-slate-400 focus:border-cyan-400/40 focus:outline-none"
      >
        {BEHAVIORS.filter((item) => weighted || item.value !== 'score').map((item) => (
          <option value={item.value} key={item.value}>
            {item.label}
          </option>
        ))}
      </select>
      {weighted && (
        <select
          value={row.weight_group}
          onChange={(event) => onChange({ weight_group: event.target.value })}
          aria-label={`Weight group for ${row.value}`}
          title="Move to another weight group"
          className="h-6 shrink-0 rounded border border-white/[0.07] bg-[#0d1320] px-1 text-[9px] text-slate-400 focus:border-cyan-400/40 focus:outline-none"
        >
          {groups.map((group) => (
            <option value={group.list_field} key={group.list_field}>
              {group.label}
            </option>
          ))}
          <option value="">Visibility only</option>
        </select>
      )}
      <button
        type="button"
        onClick={onDelete}
        title={`Delete ${row.value}`}
        aria-label={`Delete ${row.value}`}
        className="rounded p-1 text-slate-600 transition hover:bg-rose-500/10 hover:text-rose-300"
      >
        <X className="h-3 w-3" />
      </button>
    </>
  );
}

export default function KeywordWorkspaceModal({ defaultScope = 'global', onClose, onSaved }) {
  const [data, setData] = useState(null);
  const [weights, setWeights] = useState({});
  const [rows, setRows] = useState({ global: [], local: [] });
  const [scope, setScope] = useState(SCOPES.includes(defaultScope) ? defaultScope : 'global');
  const [query, setQuery] = useState('');
  const [value, setValue] = useState('');
  const [newGroup, setNewGroup] = useState('core_skills');
  const [newType, setNewType] = useState('focus');
  const [addError, setAddError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    let cancelled = false;
    api('/api/keyword-workspace')
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        setWeights(
          Object.fromEntries(
            Object.entries(payload.weights || {}).map(([key, weight]) => [key, String(weight)]),
          ),
        );
        setRows({
          global: (payload.scopes?.global || []).map((row) => ({ ...row })),
          local: (payload.scopes?.local || []).map((row) => ({ ...row })),
        });
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error.message || 'Could not load the keyword workspace.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const groups = data?.groups || [];
  const groupsByKey = useMemo(
    () => Object.fromEntries(groups.map((group) => [group.key, group])),
    [groups],
  );

  const cleanWeights = useMemo(() => {
    const out = {};
    groups.forEach((group) => {
      out[group.key] = clampWeight(group, weights[group.key] ?? data?.weights?.[group.key]);
    });
    return out;
  }, [groups, weights, data]);

  const dirty = useMemo(() => {
    if (!data) return false;
    const weightsChanged = groups.some(
      (group) => cleanWeights[group.key] !== Number(data.weights?.[group.key]),
    );
    const rowsChanged = SCOPES.some(
      (name) => JSON.stringify(rowsForSave(rows[name])) !== JSON.stringify(rowsForSave(data.scopes?.[name] || [])),
    );
    return weightsChanged || rowsChanged;
  }, [data, groups, cleanWeights, rows]);

  const activeRows = rows[scope];
  const needle = query.trim().toLowerCase();
  const visibleRows = useMemo(
    () => activeRows.filter((row) => row.value.includes(needle)),
    [activeRows, needle],
  );
  const visibilityRows = visibleRows.filter((row) => !row.weight_group);
  const groupRows = (key) => visibleRows.filter((row) => row.weight_group === key);
  const activeCount = activeRows.filter((row) => row.enabled).length;

  const updateRow = (target, patch) => {
    setRows((current) => ({
      ...current,
      [scope]: current[scope].map((row) => {
        if (row.value !== target.value) return row;
        const next = { ...row, ...patch };
        if (!next.weight_group && next.type === 'score') next.type = 'focus';
        return next;
      }),
    }));
    setSaveError('');
  };

  const deleteRow = (target) => {
    setRows((current) => ({
      ...current,
      [scope]: current[scope].filter((row) => row.value !== target.value),
    }));
    setSaveError('');
  };

  const addRow = (event) => {
    event.preventDefault();
    const clean = cleanKeyword(value);
    setAddError('');
    if (!clean) return;
    if (activeRows.some((row) => row.value === clean)) {
      setAddError(`“${clean}” is already in the ${scope} set.`);
      return;
    }
    let type = newType;
    if (newGroup === 'dealbreakers' && type === 'score') type = 'exclude';
    if (!newGroup && type === 'score') type = 'focus';
    setRows((current) => ({
      ...current,
      [scope]: [
        ...current[scope],
        { value: clean, weight_group: newGroup, type, enabled: true },
      ],
    }));
    setValue('');
    setSaveError('');
  };

  const changeGroup = (key) => {
    setNewGroup(key);
    if (key === 'dealbreakers' && newType !== 'score') setNewType('exclude');
    if (key && key !== 'dealbreakers' && newType === 'exclude') setNewType('focus');
  };

  const setWeight = (key, next) => {
    setWeights((current) => ({ ...current, [key]: next }));
    setSaveError('');
  };

  const restoreDefaults = () => {
    if (!data) return;
    setWeights(
      Object.fromEntries(
        Object.entries(data.defaults || {}).map(([key, weight]) => [key, String(weight)]),
      ),
    );
    setSaveError('');
  };

  const save = async () => {
    if (!data || saving) return;
    setSaving(true);
    setSaveError('');
    try {
      const payload = await api('/api/keyword-workspace', 'POST', {
        weights: cleanWeights,
        scopes: {
          global: rowsForSave(rows.global),
          local: rowsForSave(rows.local),
        },
      });
      onSaved?.(payload);
    } catch (error) {
      setSaveError(error.message || 'Could not save the keyword workspace.');
      setSaving(false);
    }
  };

  const footer = (
    <>
      <button
        type="button"
        className="btn btn-ghost btn-sm mr-auto"
        onClick={restoreDefaults}
        disabled={!data || saving}
      >
        <RotateCcw className="h-3.5 w-3.5" />
        Restore weight defaults
      </button>
      <button type="button" className="btn btn-secondary btn-sm" onClick={onClose} disabled={saving}>
        Cancel
      </button>
      <button
        type="button"
        className="btn btn-primary btn-sm"
        onClick={save}
        disabled={!data || saving || !dirty}
      >
        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
        Save workspace
      </button>
    </>
  );

  return (
    <Modal
      title="Keywords & weights"
      eyebrow="Scoring & visibility"
      icon={SlidersHorizontal}
      onClose={onClose}
      size="xl"
      footer={footer}
    >
      {loadError ? (
        <p className="rounded-lg border border-rose-400/15 bg-rose-500/[0.05] px-3.5 py-3 text-[11px] text-rose-200">
          {loadError}
        </p>
      ) : !data ? (
        <div className="flex items-center justify-center gap-2 py-16 text-[11px] text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin text-cyan-300" />
          Reading the keyword workspace...
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <p className="modal-copy max-w-2xl">
              One keyword set per scope. Weights are shared, so a point change applies to both
              Global and Local. Highlight and hide keywords also shape the feed; score-only
              keywords only change ranking.
            </p>
            <div className="inline-flex shrink-0 rounded-lg border border-white/[0.08] bg-white/[0.02] p-0.5">
              {SCOPES.map((name) => (
                <button
                  type="button"
                  key={name}
                  onClick={() => setScope(name)}
                  className={`rounded-md px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] transition ${
                    scope === name
                      ? 'bg-cyan-400/[0.12] text-cyan-100 shadow-[inset_0_0_0_1px_rgba(34,211,238,0.16)]'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {name}
                  <span className="ml-1.5 tabular-nums opacity-60">{rows[name].length}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-3 flex flex-col gap-2 rounded-xl border border-white/[0.06] bg-white/[0.015] p-3 sm:flex-row sm:items-center">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-600" />
              <input
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={`Filter ${scope} keywords...`}
                aria-label={`Filter ${scope} keywords`}
                className="input-dark pl-8"
              />
            </div>
            <span className="shrink-0 text-[9px] tabular-nums text-slate-600">
              {activeCount}/{activeRows.length} active in {scope}
            </span>
          </div>

          <form onSubmit={addRow} className="mt-3 rounded-xl border border-white/[0.06] bg-white/[0.015] p-3">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
              <div className="relative min-w-0 flex-1">
                <Plus className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-600" />
                <input
                  type="text"
                  value={value}
                  onChange={(event) => setValue(event.target.value)}
                  placeholder={`Add a keyword to the ${scope} set...`}
                  aria-label={`New keyword value for ${scope}`}
                  className="input-dark pl-8"
                />
              </div>
              <select
                value={newGroup}
                onChange={(event) => changeGroup(event.target.value)}
                aria-label="Weight group for the new keyword"
                className="select-dark h-9 shrink-0 py-0 text-[10px] lg:w-[170px]"
              >
                {groups.map((group) => (
                  <option value={group.list_field} key={group.list_field}>
                    {group.label}
                  </option>
                ))}
                <option value="">Visibility only</option>
              </select>
              <select
                value={newType}
                onChange={(event) => setNewType(event.target.value)}
                aria-label="Behavior for the new keyword"
                className="select-dark h-9 shrink-0 py-0 text-[10px] lg:w-[130px]"
              >
                {BEHAVIORS.filter((item) => newGroup || item.value !== 'score').map((item) => (
                  <option value={item.value} key={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
              <button type="submit" className="btn btn-primary btn-sm shrink-0" disabled={!value.trim()}>
                <Plus className="h-3.5 w-3.5" />
                Add
              </button>
            </div>
            <p className="mt-1.5 text-[9px] leading-relaxed text-slate-600">
              Highlight = visible + scored. Hide = removed + scored. Score only = ranked but always
              visible. Visibility-only keywords are not scored.
            </p>
            {addError && <p className="mt-1 text-[10px] font-medium text-amber-300">{addError}</p>}
          </form>

          <div className="mt-4 space-y-2.5">
            {groups.map((group) => {
              const tone = TONES[group.tone] || TONES.cyan;
              const weight = cleanWeights[group.key];
              const percent = ((weight - group.min) / (group.max - group.min)) * 100;
              const items = groupRows(group.list_field);
              const visible = expanded[group.key] ? items : items.slice(0, 8);
              const hidden = items.length - visible.length;
              return (
                <section
                  key={group.key}
                  className="rounded-xl border border-white/[0.06] bg-white/[0.015] px-3.5 py-3"
                >
                  <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
                        <h3 className="text-[12px] font-semibold text-slate-200">{group.label}</h3>
                        <span className={`rounded-md border px-1.5 py-0.5 text-[9px] font-semibold tabular-nums ${tone.badge}`}>
                          {signed(weight)} pts / match
                        </span>
                        <span className="text-[9px] tabular-nums text-slate-600">
                          {items.length} in {scope}
                        </span>
                      </div>
                      <p className="mt-1 max-w-xl text-[10px] leading-relaxed text-slate-500">
                        {group.description}
                      </p>
                    </div>
                    <label className="flex shrink-0 items-center gap-2">
                      <span className="sr-only">{group.label} weight</span>
                      <input
                        type="number"
                        min={group.min}
                        max={group.max}
                        step={1}
                        value={weights[group.key] ?? ''}
                        onChange={(event) => setWeight(group.key, event.target.value)}
                        onBlur={() => {
                          const raw = weights[group.key];
                          if (raw === '' || !Number.isFinite(Number(raw))) {
                            setWeight(group.key, String(weight));
                          }
                        }}
                        className="input-dark h-8 w-[74px] text-center text-[12px] tabular-nums"
                      />
                    </label>
                  </div>

                  <div className="mt-2.5 flex items-center gap-3">
                    <span className="w-7 shrink-0 text-right text-[9px] tabular-nums text-slate-600">{group.min}</span>
                    <input
                      type="range"
                      min={group.min}
                      max={group.max}
                      step={1}
                      value={weight}
                      onChange={(event) => setWeight(group.key, event.target.value)}
                      aria-label={`${group.label} weight`}
                      className="weight-range"
                      style={{
                        '--weight-color': tone.accent,
                        background: `linear-gradient(to right, ${tone.accent} 0%, ${tone.accent} ${percent}%, rgba(255,255,255,0.08) ${percent}%, rgba(255,255,255,0.08) 100%)`,
                      }}
                    />
                    <span className="w-7 shrink-0 text-[9px] tabular-nums text-slate-600">{group.max}</span>
                  </div>

                  <div className="mt-2 space-y-1">
                    {visible.map((row) => (
                      <div
                        key={row.value}
                        className={`flex min-h-[30px] flex-wrap items-center gap-1.5 rounded-md border px-1.5 py-0.5 ${
                          row.enabled ? tone.row : 'border-white/[0.04] bg-white/[0.01]'
                        }`}
                      >
                        <RowControls
                          row={row}
                          groups={groups}
                          onChange={(patch) => updateRow(row, patch)}
                          onDelete={() => deleteRow(row)}
                        />
                      </div>
                    ))}
                    {!items.length && (
                      <p className="py-1 text-[9px] italic text-slate-600">
                        {needle ? `No ${group.label.toLowerCase()} matches.` : 'No keywords in this group yet.'}
                      </p>
                    )}
                    {(hidden > 0 || (expanded[group.key] && items.length > 8)) && (
                      <button
                        type="button"
                        onClick={() =>
                          setExpanded((current) => ({ ...current, [group.key]: !current[group.key] }))
                        }
                        className="rounded px-1.5 py-0.5 text-[9px] font-medium text-slate-500 transition hover:bg-white/[0.05] hover:text-slate-200"
                      >
                        {hidden > 0 ? `+${hidden} more` : 'Show less'}
                      </button>
                    )}
                  </div>
                </section>
              );
            })}

            <section className="rounded-xl border border-white/[0.06] bg-white/[0.015] px-3.5 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <Tag className="h-3 w-3 text-slate-400" />
                <h3 className="text-[12px] font-semibold text-slate-200">Visibility only</h3>
                <span className="text-[9px] tabular-nums text-slate-600">
                  {visibilityRows.length} in {scope}
                </span>
              </div>
              <p className="mt-1 max-w-xl text-[10px] leading-relaxed text-slate-500">
                Highlight or hide matches without adding any score. Pick this by setting a keyword&apos;s
                weight group to “Visibility only”.
              </p>
              <div className="mt-2 space-y-1">
                {visibilityRows.map((row) => (
                  <div
                    key={row.value}
                    className={`flex min-h-[30px] flex-wrap items-center gap-1.5 rounded-md border px-1.5 py-0.5 ${
                      row.enabled
                        ? row.type === 'exclude'
                          ? 'border-rose-400/15 bg-rose-500/[0.04]'
                          : 'border-slate-400/10 bg-white/[0.02]'
                        : 'border-white/[0.04] bg-white/[0.01]'
                    }`}
                  >
                    <span className="rounded p-1 text-slate-500">
                      {row.type === 'exclude' ? (
                        <EyeOff className="h-3 w-3" />
                      ) : (
                        <Sparkles className="h-3 w-3" />
                      )}
                    </span>
                    <span
                      className={`min-w-0 flex-1 truncate text-[11px] ${
                        row.enabled ? 'text-slate-200' : 'text-slate-500 line-through decoration-slate-700'
                      }`}
                    >
                      {row.value}
                    </span>
                    {!row.enabled && (
                      <span className="rounded bg-white/5 px-1 py-0.5 text-[8px] font-semibold uppercase tracking-wider text-amber-300/80">
                        paused
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => updateRow(row, { enabled: !row.enabled })}
                      title={row.enabled ? 'Pause this keyword' : 'Resume this keyword'}
                      aria-label={row.enabled ? `Pause ${row.value}` : `Resume ${row.value}`}
                      className={`rounded p-1 transition hover:bg-white/10 ${
                        row.enabled ? 'text-slate-500 hover:text-slate-200' : 'text-amber-300'
                      }`}
                    >
                      {row.enabled ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                    </button>
                    <select
                      value={row.type}
                      onChange={(event) => updateRow(row, { type: event.target.value })}
                      aria-label={`Behavior for ${row.value}`}
                      className="h-6 shrink-0 rounded border border-white/[0.07] bg-[#0d1320] px-1 text-[9px] text-slate-400 focus:border-cyan-400/40 focus:outline-none"
                    >
                      <option value="focus">Highlight</option>
                      <option value="exclude">Hide</option>
                    </select>
                    <select
                      value=""
                      onChange={(event) => updateRow(row, { weight_group: event.target.value })}
                      aria-label={`Weight group for ${row.value}`}
                      title="Place this keyword under a scoring weight"
                      className="h-6 shrink-0 rounded border border-white/[0.07] bg-[#0d1320] px-1 text-[9px] text-slate-400 focus:border-cyan-400/40 focus:outline-none"
                    >
                      <option value="">Visibility only</option>
                      {groups.map((group) => (
                        <option value={group.list_field} key={group.list_field}>
                          {group.label}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => deleteRow(row)}
                      title={`Delete ${row.value}`}
                      aria-label={`Delete ${row.value}`}
                      className="rounded p-1 text-slate-600 transition hover:bg-rose-500/10 hover:text-rose-300"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
                {!visibilityRows.length && (
                  <p className="py-1 text-[9px] italic text-slate-600">
                    No visibility-only keywords in this scope.
                  </p>
                )}
              </div>
            </section>
          </div>

          <div className="mt-3 grid gap-2 rounded-xl border border-white/[0.06] bg-white/[0.015] p-3 sm:grid-cols-3">
            <div>
              <div className="flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                <Gauge className="h-3 w-3 text-cyan-300/70" />
                Per match
              </div>
              <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
                Every enabled keyword in a group adds that group&apos;s weight. Dealbreakers subtract.
              </p>
            </div>
            <div>
              <div className="flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                <Eye className="h-3 w-3 text-cyan-300/70" />
                Visibility
              </div>
              <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
                Highlight and hide lists are per scope. Pausing a keyword stops both its score and
                its visibility effect.
              </p>
            </div>
            <div>
              <div className="flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                <SlidersHorizontal className="h-3 w-3 text-cyan-300/70" />
                One weight
              </div>
              <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
                A keyword can only sit in one weight group. Moving it updates its score weight.
              </p>
            </div>
          </div>

          <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[9px] text-slate-600">
            <span className={`h-1.5 w-1.5 rounded-full ${dirty ? 'bg-amber-400' : 'bg-emerald-400'}`} />
            {dirty ? 'Unsaved changes — both scopes save together.' : 'Everything is saved.'}
            {!dirty && data.saved && <span className="text-slate-700">· Saved scoring profile.</span>}
          </div>

          {saveError && <p className="error-text">{saveError}</p>}
        </>
      )}
    </Modal>
  );
}
