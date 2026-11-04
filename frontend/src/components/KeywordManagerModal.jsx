import { useEffect, useMemo, useState } from 'react';
import {
  CheckCheck,
  EyeOff,
  Folder,
  Loader2,
  Search,
  Settings2,
  Sparkles,
  X,
  XCircle,
} from 'lucide-react';
import Modal from './Modal';
import { api } from '../lib/api';

const TONE_DOT = {
  cyan: 'bg-cyan-400',
  blue: 'bg-blue-400',
  emerald: 'bg-emerald-400',
  amber: 'bg-amber-400',
  rose: 'bg-rose-400',
  violet: 'bg-violet-400',
  slate: 'bg-slate-500',
};

const TONE_BADGE = {
  cyan: 'border-cyan-400/20 bg-cyan-400/[0.08] text-cyan-200',
  blue: 'border-blue-400/20 bg-blue-500/[0.09] text-blue-200',
  emerald: 'border-emerald-400/20 bg-emerald-500/[0.08] text-emerald-200',
  amber: 'border-amber-400/20 bg-amber-500/[0.08] text-amber-200',
  rose: 'border-rose-400/20 bg-rose-500/[0.08] text-rose-200',
  violet: 'border-violet-400/20 bg-violet-500/[0.08] text-violet-200',
  slate: 'border-white/[0.08] bg-white/[0.03] text-slate-400',
};

function points(value) {
  if (value > 0) return `+${value}`;
  if (value < 0) return `−${Math.abs(value)}`;
  return '0';
}

/**
 * Split managed keywords into custom groups first, then the scoring categories
 * used by the weights form. A custom group wins over the automatic category, so
 * moving a keyword there removes it from its category section.
 */
function buildSections(items, groups, type) {
  const sections = new Map();

  items.forEach((item) => {
    const name = (item.group || '').trim();
    if (!name) return;
    if (!sections.has(name)) {
      sections.set(name, {
        key: `custom:${name}`,
        label: name,
        tone: 'violet',
        weight: null,
        kind: 'custom',
        items: [],
      });
    }
    sections.get(name).items.push(item);
  });

  const ungrouped = items.filter((item) => !(item.group || '').trim());
  const relevant = (groups || []).filter(
    (group) => !group.system && (type === 'exclude'
      ? group.key === 'dealbreaker_weight'
      : group.key !== 'dealbreaker_weight'),
  );

  const lookup = new Map();
  relevant.forEach((group) => {
    (group.keywords || []).forEach((keyword) => {
      if (!lookup.has(keyword)) lookup.set(keyword, group);
    });
  });

  const scoringSections = new Map();
  relevant.forEach((group) => {
    scoringSections.set(group.key, {
      key: group.key,
      label: group.label,
      tone: group.tone || 'slate',
      weight: group.weight,
      kind: 'scoring',
      items: [],
    });
  });

  const other = {
    key: 'other',
    label: relevant.length
      ? type === 'focus'
        ? 'Other signals'
        : 'Other hide keywords'
      : 'All keywords',
    tone: 'slate',
    weight: null,
    kind: 'scoring',
    items: [],
  };

  ungrouped.forEach((item) => {
    const group = lookup.get(item.value);
    const key = group && scoringSections.has(group.key) ? group.key : 'other';
    if (key === 'other') other.items.push(item);
    else scoringSections.get(key).items.push(item);
  });

  const custom = [...sections.values()].sort((a, b) => a.label.localeCompare(b.label));

  return [...custom, ...scoringSections.values(), other].filter(
    (section) => section.items.length,
  );
}

export default function KeywordManagerModal({ type, items, onClose, onSave }) {
  const [states, setStates] = useState({});
  const [manualGroups, setManualGroups] = useState({});
  const [groups, setGroups] = useState([]);
  const [grouping, setGrouping] = useState(true);
  const [query, setQuery] = useState('');
  const [newGroupFor, setNewGroupFor] = useState(null);
  const [newGroupName, setNewGroupName] = useState('');
  const focus = type === 'focus';

  useEffect(() => {
    const nextStates = {};
    const nextGroups = {};
    items.forEach((item) => {
      nextStates[item.value] = !!item.enabled;
      nextGroups[item.value] = item.group || '';
    });
    setStates(nextStates);
    setManualGroups(nextGroups);
    setNewGroupFor(null);
    setNewGroupName('');
  }, [items, type]);

  useEffect(() => {
    let cancelled = false;
    setGrouping(true);
    api('/api/weights')
      .then((data) => {
        if (cancelled) return;
        setGroups(Array.isArray(data.groups) ? data.groups : []);
        setGrouping(false);
      })
      .catch(() => {
        if (cancelled) return;
        setGroups([]);
        setGrouping(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const enrichedItems = useMemo(
    () => items.map((item) => ({
      ...item,
      group: manualGroups[item.value] ?? (item.group || ''),
    })),
    [items, manualGroups],
  );

  const groupNames = useMemo(
    () => [...new Set(enrichedItems.map((item) => item.group).filter(Boolean))].sort(
      (a, b) => a.localeCompare(b),
    ),
    [enrichedItems],
  );

  const sections = useMemo(
    () => buildSections(enrichedItems, groups, type),
    [enrichedItems, groups, type],
  );

  const needle = query.trim().toLowerCase();
  const visibleSections = useMemo(
    () => sections
      .map((section) => ({
        ...section,
        visible: section.items.filter((item) => item.value.toLowerCase().includes(needle)),
      }))
      .filter((section) => section.visible.length),
    [sections, needle],
  );

  const enabledCount = items.filter((item) => states[item.value]).length;

  const toggle = (value, checked) => {
    setStates((current) => ({ ...current, [value]: checked }));
  };

  const setAll = (checked) => {
    const next = {};
    items.forEach((item) => {
      next[item.value] = checked;
    });
    setStates(next);
  };

  const setGroupFor = (value, name) => {
    const clean = name.trim().slice(0, 40);
    const canonical = clean
      ? groupNames.find((group) => group.toLowerCase() === clean.toLowerCase()) || clean
      : '';
    setManualGroups((current) => ({ ...current, [value]: canonical }));
  };

  const commitNewGroup = (value) => {
    const name = newGroupName.trim();
    if (name) setGroupFor(value, name);
    setNewGroupFor(null);
    setNewGroupName('');
  };

  const setGroup = (values, checked) => {
    setStates((current) => {
      const next = { ...current };
      values.forEach((value) => {
        next[value] = checked;
      });
      return next;
    });
  };

  const save = () => {
    const pendingGroups = { ...manualGroups };
    if (newGroupFor && newGroupName.trim()) {
      pendingGroups[newGroupFor] = newGroupName.trim().slice(0, 40);
    }
    const groupsPayload = {};
    items.forEach((item) => {
      groupsPayload[item.value] = pendingGroups[item.value] ?? (item.group || '');
    });
    onSave(states, groupsPayload);
  };

  return (
    <Modal
      title={`Manage ${focus ? 'highlight' : 'hide'} keywords`}
      eyebrow="Preferences"
      icon={Settings2}
      onClose={onClose}
      size="md"
      footer={
        <>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={save}>
            Save changes
          </button>
        </>
      }
    >
      <p className="modal-copy">
        Keywords are grouped by scoring category or by the custom group you assign. Uncheck one to
        pause it — paused keywords stay saved and can be re-enabled later. Use the × on a chip to
        delete it permanently.
      </p>
      <p className="mt-1 text-[10px] leading-relaxed text-slate-600">
        Custom groups only change how this list is organised; scoring still follows the category
        lists and their weights.
      </p>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-600" />
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={`Filter ${focus ? 'highlight' : 'hide'} keywords...`}
            aria-label={`Filter ${focus ? 'highlight' : 'hide'} keywords`}
            className="input-dark pl-8 pr-8"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              aria-label="Clear keyword filter"
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 transition hover:bg-white/[0.06] hover:text-slate-200"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <span className="text-[9px] tabular-nums text-slate-600">
            {enabledCount}/{items.length} enabled
          </span>
          <button type="button" className="btn btn-secondary btn-xs" onClick={() => setAll(true)}>
            <CheckCheck className="h-3 w-3" />
            Enable all
          </button>
          <button type="button" className="btn btn-secondary btn-xs" onClick={() => setAll(false)}>
            <XCircle className="h-3 w-3" />
            Disable all
          </button>
        </div>
      </div>

      {grouping ? (
        <div className="flex items-center justify-center gap-2 py-14 text-[11px] text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin text-cyan-300" />
          Grouping keywords...
        </div>
      ) : (
        <div className="mt-5 space-y-5">
          {visibleSections.map((section) => {
            const allEnabled = section.visible.every((item) => states[item.value]);
            const shown = section.visible.length;
            const dot = TONE_DOT[section.tone] || TONE_DOT.slate;
            const badge = TONE_BADGE[section.tone] || TONE_BADGE.slate;

            return (
              <section key={section.key} aria-label={`${section.label} keywords`}>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    {section.kind === 'custom' ? (
                      <Folder className="h-3 w-3 shrink-0 text-violet-300/80" />
                    ) : (
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
                    )}
                    <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                      {section.label}
                    </h3>
                    <span className="rounded bg-white/[0.04] px-1.5 py-0.5 text-[8px] tabular-nums text-slate-500">
                      {needle ? `${shown}/${section.items.length}` : section.items.length}
                    </span>
                    {section.weight !== null && section.weight !== undefined && (
                      <span className={`rounded border px-1.5 py-0.5 text-[8px] font-semibold tabular-nums ${badge}`}>
                        {points(section.weight)} pts
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setGroup(section.visible.map((item) => item.value), !allEnabled)}
                    className="rounded px-1.5 py-0.5 text-[9px] font-medium text-slate-500 transition hover:bg-white/[0.05] hover:text-slate-200"
                  >
                    {needle
                      ? allEnabled
                        ? 'Pause shown'
                        : 'Enable shown'
                      : allEnabled
                        ? 'Pause group'
                        : 'Enable group'}
                  </button>
                </div>

                <div className="space-y-1.5">
                  {section.visible.map((item) => {
                    const checked = !!states[item.value];
                    const group = manualGroups[item.value] ?? (item.group || '');

                    return (
                      <div
                        key={item.value}
                        className={`flex items-center gap-2 rounded-lg border transition ${
                          checked
                            ? focus
                              ? 'border-cyan-400/15 bg-cyan-400/[0.05] text-cyan-100'
                              : 'border-rose-400/15 bg-rose-500/[0.05] text-rose-100'
                            : 'border-white/[0.05] bg-white/[0.015] text-slate-500'
                        }`}
                      >
                        <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 px-3 py-2.5 text-[12px]">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(event) => toggle(item.value, event.target.checked)}
                            className="checkbox-dark"
                          />
                          {focus ? (
                            <Sparkles className="h-3 w-3 shrink-0 opacity-50" />
                          ) : (
                            <EyeOff className="h-3 w-3 shrink-0 opacity-50" />
                          )}
                          <span
                            className={`min-w-0 flex-1 truncate ${
                              checked ? '' : 'line-through decoration-slate-700'
                            }`}
                          >
                            {item.value}
                          </span>
                          {!checked && (
                            <span className="shrink-0 text-[8px] font-semibold uppercase tracking-[0.14em] text-slate-600">
                              paused
                            </span>
                          )}
                        </label>

                        {newGroupFor === item.value ? (
                          <input
                            autoFocus
                            type="text"
                            value={newGroupName}
                            maxLength={40}
                            onChange={(event) => setNewGroupName(event.target.value)}
                            onBlur={() => commitNewGroup(item.value)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') {
                                event.preventDefault();
                                commitNewGroup(item.value);
                              } else if (event.key === 'Escape') {
                                setNewGroupFor(null);
                                setNewGroupName('');
                              }
                            }}
                            placeholder="Group name"
                            aria-label={`New group for ${item.value}`}
                            className="mr-2 h-7 w-[104px] shrink-0 rounded-md border border-violet-400/25 bg-violet-500/[0.06] px-1.5 text-[9px] text-violet-100 placeholder:text-violet-300/40 focus:border-violet-300/40 focus:outline-none focus:ring-2 focus:ring-violet-400/10 sm:w-[118px]"
                          />
                        ) : (
                          <select
                            value={group}
                            onChange={(event) => {
                              if (event.target.value === '__new') {
                                setNewGroupFor(item.value);
                                setNewGroupName('');
                              } else {
                                setGroupFor(item.value, event.target.value);
                              }
                            }}
                            aria-label={`Group for ${item.value}`}
                            title="Automatic grouping follows the scoring category; choose a group to organise it manually."
                            className="mr-2 h-7 w-[104px] shrink-0 rounded-md border border-white/[0.07] bg-[#0d1320] px-1.5 text-[9px] text-slate-400 transition hover:border-white/[0.14] hover:text-slate-200 focus:border-violet-400/40 focus:outline-none focus:ring-2 focus:ring-violet-400/10 sm:w-[118px]"
                          >
                            <option value="">Auto category</option>
                            {groupNames.map((name) => (
                              <option value={name} key={name}>
                                {name}
                              </option>
                            ))}
                            <option value="__new">+ New group</option>
                          </select>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}

          {!visibleSections.length && (
            <p className="rounded-lg border border-white/[0.05] bg-white/[0.015] px-3.5 py-6 text-center text-[11px] italic text-slate-600">
              {items.length
                ? `No ${focus ? 'highlight' : 'hide'} keywords match “${query.trim()}”.`
                : 'No keywords to manage.'}
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}
