import { useEffect, useMemo, useState } from 'react';
import { Gauge, Loader2, RotateCcw, Save, SlidersHorizontal } from 'lucide-react';
import Modal from './Modal';
import ImpactPreview from './ImpactPreview';
import { api } from '../lib/api';

const TONES = {
  cyan: {
    accent: '#22d3ee',
    dot: 'bg-cyan-400',
    chip: 'border-cyan-400/20 bg-cyan-400/[0.08] text-cyan-200',
    badge: 'border-cyan-400/25 bg-cyan-400/[0.1] text-cyan-100',
  },
  blue: {
    accent: '#60a5fa',
    dot: 'bg-blue-400',
    chip: 'border-blue-400/20 bg-blue-500/[0.09] text-blue-200',
    badge: 'border-blue-400/25 bg-blue-500/[0.11] text-blue-100',
  },
  emerald: {
    accent: '#34d399',
    dot: 'bg-emerald-400',
    chip: 'border-emerald-400/20 bg-emerald-500/[0.08] text-emerald-200',
    badge: 'border-emerald-400/25 bg-emerald-500/[0.1] text-emerald-100',
  },
  amber: {
    accent: '#fbbf24',
    dot: 'bg-amber-400',
    chip: 'border-amber-400/20 bg-amber-500/[0.08] text-amber-200',
    badge: 'border-amber-400/25 bg-amber-500/[0.1] text-amber-100',
  },
  rose: {
    accent: '#fb7185',
    dot: 'bg-rose-400',
    chip: 'border-rose-400/20 bg-rose-500/[0.08] text-rose-200',
    badge: 'border-rose-400/25 bg-rose-500/[0.1] text-rose-100',
  },
};

function clampWeight(group, value) {
  const parsed = Number(value);
  const safe = Number.isFinite(parsed) ? parsed : 0;
  return Math.max(group.min, Math.min(group.max, Math.round(safe)));
}

function signed(value) {
  if (value > 0) return `+${value}`;
  if (value < 0) return `−${Math.abs(value)}`;
  return '0';
}

function WeightRow({ group, value, rawValue, onChange, expanded, onToggleExpand }) {
  const tone = TONES[group.tone] || TONES.cyan;
  const weight = clampWeight(group, value);
  const percent = ((weight - group.min) / (group.max - group.min)) * 100;
  const keywords = group.keywords || [];
  const visibleKeywords = expanded ? keywords : keywords.slice(0, 8);
  const hiddenCount = keywords.length - visibleKeywords.length;

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] px-3.5 py-3">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
            <h4 className="text-[12px] font-semibold text-slate-200">{group.label}</h4>
            <span
              className={`rounded-md border px-1.5 py-0.5 text-[9px] font-semibold tabular-nums ${tone.badge}`}
            >
              {signed(weight)} pts / match
            </span>
          </div>
          <p className="mt-1 max-w-xl text-[10px] leading-relaxed text-slate-500">{group.description}</p>
        </div>

        <label className="flex shrink-0 items-center gap-2">
          <span className="sr-only">{group.label} weight</span>
          <input
            type="number"
            min={group.min}
            max={group.max}
            step={1}
            value={rawValue}
            onChange={(event) => onChange(event.target.value)}
            onBlur={() => {
              if (rawValue === '' || !Number.isFinite(Number(rawValue))) onChange(String(weight));
            }}
            className="input-dark h-8 w-[74px] text-center text-[12px] tabular-nums"
          />
        </label>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <span className="w-7 shrink-0 text-right text-[9px] tabular-nums text-slate-600">{group.min}</span>
        <input
          type="range"
          min={group.min}
          max={group.max}
          step={1}
          value={weight}
          onChange={(event) => onChange(event.target.value)}
          aria-label={`${group.label} weight`}
          className="weight-range"
          style={{
            '--weight-color': tone.accent,
            background: `linear-gradient(to right, ${tone.accent} 0%, ${tone.accent} ${percent}%, rgba(255,255,255,0.08) ${percent}%, rgba(255,255,255,0.08) 100%)`,
          }}
        />
        <span className="w-7 shrink-0 text-[9px] tabular-nums text-slate-600">{group.max}</span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1">
        {group.system ? (
          <span className="text-[9px] italic text-slate-600">
            Applies to the word “POS” in a title or description.
          </span>
        ) : (
          <>
            <span className="mr-1 text-[8px] font-semibold uppercase tracking-[0.12em] text-slate-600">
              Applies to
            </span>
            {visibleKeywords.map((keyword) => (
              <span
                key={keyword}
                className={`rounded border px-1.5 py-0.5 text-[9px] ${tone.chip}`}
              >
                {keyword}
              </span>
            ))}
            {!keywords.length && (
              <span className="text-[9px] italic text-slate-600">No keywords in this group yet.</span>
            )}
            {hiddenCount > 0 && (
              <button
                type="button"
                onClick={onToggleExpand}
                className="rounded px-1.5 py-0.5 text-[9px] font-medium text-slate-400 transition hover:bg-white/[0.05] hover:text-slate-200"
              >
                +{hiddenCount} more
              </button>
            )}
            {expanded && keywords.length > 8 && (
              <button
                type="button"
                onClick={onToggleExpand}
                className="rounded px-1.5 py-0.5 text-[9px] font-medium text-slate-400 transition hover:bg-white/[0.05] hover:text-slate-200"
              >
                Show less
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function ScoringWeightsModal({ strictness, onClose, onSaved }) {
  const [data, setData] = useState(null);
  const [weights, setWeights] = useState({});
  const [expanded, setExpanded] = useState({});
  const [loadError, setLoadError] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [impact, setImpact] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api('/api/weights')
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        setWeights(
          Object.fromEntries(
            Object.entries(payload.weights || {}).map(([key, value]) => [key, String(value)]),
          ),
        );
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error.message || 'Could not load the score weights.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const cleanWeights = useMemo(() => {
    if (!data) return {};
    const out = {};
    data.groups.forEach((group) => {
      const raw = weights[group.key];
      const parsed = raw === '' || raw === undefined ? data.weights[group.key] : Number(raw);
      out[group.key] = clampWeight(
        group,
        Number.isFinite(parsed) ? parsed : data.weights[group.key],
      );
    });
    return out;
  }, [data, weights]);

  const dirty = useMemo(() => {
    if (!data) return false;
    return data.groups.some((group) => cleanWeights[group.key] !== Number(data.weights[group.key]));
  }, [data, cleanWeights]);

  const isDefault = useMemo(() => {
    if (!data) return true;
    return data.groups.every((group) => cleanWeights[group.key] === Number(data.defaults[group.key]));
  }, [data, cleanWeights]);

  useEffect(() => {
    if (!data) return undefined;
    const timer = setTimeout(() => {
      api('/api/profile/preview', 'POST', {
        profile: { ...data.profile, ...cleanWeights },
        focus: data.focus || [],
        exclude: data.exclude || [],
        strictness,
      })
        .then((result) => setImpact(result.impact))
        .catch(() => {});
    }, 400);
    return () => clearTimeout(timer);
  }, [data, cleanWeights, strictness]);

  const setWeight = (key, value) => {
    setWeights((current) => ({ ...current, [key]: value }));
    setSaveError('');
  };

  const restoreDefaults = () => {
    if (!data) return;
    setWeights(
      Object.fromEntries(
        Object.entries(data.defaults).map(([key, value]) => [key, String(value)]),
      ),
    );
    setSaveError('');
  };

  const save = async () => {
    if (!data || saving) return;
    setSaving(true);
    setSaveError('');
    try {
      const payload = await api('/api/weights', 'POST', { weights: cleanWeights });
      onSaved?.(payload);
    } catch (error) {
      setSaveError(error.message || 'Could not save the score weights.');
      setSaving(false);
    }
  };

  const footer = (
    <>
      <button
        type="button"
        className="btn btn-ghost btn-sm mr-auto"
        onClick={restoreDefaults}
        disabled={!data || saving || isDefault}
      >
        <RotateCcw className="h-3.5 w-3.5" />
        Restore defaults
      </button>
      <button type="button" className="btn btn-secondary btn-sm" onClick={onClose} disabled={saving}>
        Cancel
      </button>
      <button type="button" className="btn btn-primary btn-sm" onClick={save} disabled={!data || saving || !dirty}>
        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
        Save weights
      </button>
    </>
  );

  return (
    <Modal
      title="Keyword weights"
      eyebrow="Scoring engine"
      icon={SlidersHorizontal}
      onClose={onClose}
      size="lg"
      footer={footer}
    >
      {loadError ? (
        <p className="rounded-lg border border-rose-400/15 bg-rose-500/[0.05] px-3.5 py-3 text-[11px] text-rose-200">
          {loadError}
        </p>
      ) : !data ? (
        <div className="flex items-center justify-center gap-2 py-16 text-[11px] text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin text-cyan-300" />
          Reading the current weights...
        </div>
      ) : (
        <>
          <p className="modal-copy">
            These are the points each keyword group adds to a role&apos;s score. Change a weight to
            make that group matter more or less — the keyword lists themselves stay exactly as they
            are.
          </p>

          <div className="mt-3 grid gap-2 rounded-xl border border-white/[0.06] bg-white/[0.015] p-3 sm:grid-cols-3">
            <div>
              <div className="flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                <Gauge className="h-3 w-3 text-cyan-300/70" />
                Per match
              </div>
              <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
                Every matching keyword adds its group&apos;s weight.
              </p>
            </div>
            <div>
              <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                Stacks up
              </div>
              <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
                More matches in a group keep adding points. Dealbreakers subtract.
              </p>
            </div>
            <div>
              <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                Ranking
              </div>
              <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
                Higher totals rise in “Most recommended”. Strictness floors still apply.
              </p>
            </div>
          </div>

          <div className="mt-4 space-y-2.5">
            {data.groups.map((group) => (
              <WeightRow
                key={group.key}
                group={group}
                value={cleanWeights[group.key]}
                rawValue={weights[group.key] ?? ''}
                onChange={(value) => setWeight(group.key, value)}
                expanded={!!expanded[group.key]}
                onToggleExpand={() =>
                  setExpanded((current) => ({ ...current, [group.key]: !current[group.key] }))
                }
              />
            ))}
          </div>

          <div className="mt-4">
            <ImpactPreview impact={impact} strictness={strictness} actionLabel="saving" />
          </div>

          <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[9px] text-slate-600">
            <span className={`h-1.5 w-1.5 rounded-full ${dirty ? 'bg-amber-400' : 'bg-emerald-400'}`} />
            {dirty ? 'Unsaved changes — preview updates as you edit.' : 'These weights are live.'}
            {!dirty && data.saved && <span className="text-slate-700">· Saved to your scoring profile.</span>}
            {data.saved && <span className="text-slate-700">· Restore defaults sets the original scale.</span>}
          </div>

          {saveError && <p className="error-text">{saveError}</p>}
        </>
      )}
    </Modal>
  );
}
