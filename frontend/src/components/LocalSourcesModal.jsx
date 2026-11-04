import { useEffect, useState } from 'react';
import {
  Check,
  ExternalLink,
  Globe2,
  Link2,
  Loader2,
  Plus,
  Radar,
  Radio,
  RefreshCw,
  ScanLine,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';
import Modal from './Modal';
import { api } from '../lib/api';
import { pluralize } from '../lib/utils';

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

export default function LocalSourcesModal({ onClose, notify, onImported }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState({});
  const [watch, setWatch] = useState({});
  const [applying, setApplying] = useState(null);
  const [sites, setSites] = useState([]);
  const [sitesError, setSitesError] = useState('');
  const [removeTarget, setRemoveTarget] = useState(null);
  const [queries, setQueries] = useState([]);
  const [queryDraft, setQueryDraft] = useState('');
  const [queriesError, setQueriesError] = useState('');
  const [savingQuery, setSavingQuery] = useState(false);

  const loadSites = async () => {
    try {
      const data = await api('/api/local-sites');
      setSites(data.sites || []);
      setSitesError('');
    } catch {
      setSitesError('Could not load watched sources.');
    }
  };

  const loadQueries = async () => {
    try {
      const data = await api('/api/discovery-queries');
      setQueries(data.queries || []);
      setQueriesError('');
    } catch {
      setQueriesError('Could not load discovery searches.');
    }
  };

  useEffect(() => {
    loadSites();
    loadQueries();
  }, []);

  const scan = async () => {
    const clean = text.trim();
    if (!clean) {
      setError('Paste a link or message first.');
      return;
    }
    setBusy(true);
    setError('');
    setStatus('Resolving the link and reading role pages. This can take up to a minute.');
    setResults([]);
    try {
      const data = await api('/api/local-sites/scan', 'POST', { text: clean });
      const nextResults = data.results || [];
      const nextSelected = {};
      const nextWatch = {};
      nextResults.forEach((result, index) => {
        nextSelected[index] = (result.jobs || []).map((job) => job.url);
        nextWatch[index] = true;
      });
      setResults(nextResults);
      setSelected(nextSelected);
      setWatch(nextWatch);
      const ok = nextResults.filter((result) => !result.error).length;
      setStatus(`Scanned ${pluralize(ok, 'link')}.`);
    } catch (scanError) {
      setError(scanError.message || 'Could not scan that link.');
      setStatus('');
    } finally {
      setBusy(false);
    }
  };

  const toggleJob = (index, url) => {
    setSelected((current) => {
      const existing = current[index] || [];
      const next = existing.includes(url)
        ? existing.filter((item) => item !== url)
        : [...existing, url];
      return { ...current, [index]: next };
    });
  };

  const apply = async (index) => {
    const result = results[index];
    if (!result?.token || applying !== null) return;
    const selectedJobs = selected[index] || [];
    const shouldWatch = !!watch[index];
    if (!selectedJobs.length && !shouldWatch) {
      notify('Select a role or watch the page');
      return;
    }

    setApplying(index);
    try {
      const data = await api('/api/local-sites/apply', 'POST', {
        token: result.token,
        watch: shouldWatch,
        jobs: selectedJobs,
      });
      notify(
        `Imported ${pluralize(data.imported || 0, 'role')}${data.watched ? ' and watching this page' : ''}`,
      );
      onImported();
      onClose();
    } catch (applyError) {
      notify(applyError.message || 'Could not import those roles');
    } finally {
      setApplying(null);
    }
  };

  const toggleSite = async (site, enabled) => {
    try {
      const data = await api('/api/local-sites/state', 'POST', { url: site.url, enabled });
      setSites(data.sites || []);
      notify(enabled ? 'Source enabled' : 'Source paused');
    } catch (siteError) {
      notify(siteError.message || 'Could not update that source');
      loadSites();
    }
  };

  const removeSite = async (site) => {
    try {
      const data = await api('/api/local-sites/delete', 'POST', { url: site.url });
      setSites(data.sites || []);
      setRemoveTarget(null);
      notify('Source removed');
    } catch (siteError) {
      notify(siteError.message || 'Could not remove that source');
    }
  };

  const saveQueries = async (next) => {
    setSavingQuery(true);
    setQueriesError('');
    try {
      const data = await api('/api/discovery-queries', 'POST', { queries: next });
      setQueries(data.queries || []);
      return true;
    } catch (queryError) {
      setQueriesError(queryError.message || 'Could not save discovery searches.');
      return false;
    } finally {
      setSavingQuery(false);
    }
  };

  const addQuery = async (event) => {
    event.preventDefault();
    const clean = queryDraft.trim();
    if (!clean || savingQuery) return;
    if (queries.some((query) => query.toLowerCase() === clean.toLowerCase())) {
      setQueryDraft('');
      return;
    }
    const ok = await saveQueries([...queries, clean]);
    if (ok) setQueryDraft('');
  };

  const removeQuery = async (query) => {
    if (savingQuery) return;
    await saveQueries(queries.filter((item) => item !== query));
  };

  const activeSites = sites.filter((site) => site.enabled).length;

  return (
    <Modal
      title="Local Sources"
      eyebrow="Local discovery"
      icon={Radio}
      onClose={onClose}
      size="xl"
      footer={
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
          Close
        </button>
      }
    >
      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <div>
          <p className="modal-copy">
            Paste a company careers page or a whole WhatsApp message. Short links are resolved and the real
            destination is shown before anything is imported. Discovery searches on the right add web results.
            Every role type is kept; your keywords shape highlighting and scoring, not what a page contains.
          </p>

          <label className="field-label mt-5" htmlFor="local-link-input">
            Link or WhatsApp message
          </label>
          <textarea
            id="local-link-input"
            rows={4}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="e.g. https://shorturl.at/fRa0o"
            className="textarea-dark"
          />

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button type="button" className="btn btn-primary btn-sm" onClick={scan} disabled={busy}>
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ScanLine className="h-3.5 w-3.5" />}
              {busy ? 'Scanning...' : 'Scan link'}
            </button>
            {status && <span className="text-[11px] text-slate-500">{status}</span>}
          </div>
          {error && <p className="error-text">{error}</p>}

          <div className="mt-5 space-y-3">
            {results.map((result, index) => {
              if (result.error) {
                return (
                  <div key={`error-${index}`} className="rounded-xl border border-rose-400/20 bg-rose-500/[0.05] p-4">
                    <div className="flex items-center gap-2 text-[12px] font-semibold text-rose-200">
                      <Radar className="h-3.5 w-3.5" />
                      Could not scan
                    </div>
                    <p className="mt-1 break-all text-[10px] text-slate-500">{result.input_url}</p>
                    <p className="mt-2 text-[11px] leading-relaxed text-rose-200/80">{result.error}</p>
                  </div>
                );
              }

              const jobs = result.jobs || [];
              const chosen = selected[index] || [];
              const watching = !!watch[index];
              const found = result.total_found || 0;

              return (
                <div key={`result-${index}`} className="overflow-hidden rounded-xl border border-white/[0.08] bg-white/[0.02]">
                  <div className="flex items-start justify-between gap-3 border-b border-white/[0.06] px-4 py-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Globe2 className="h-3.5 w-3.5 text-cyan-300" />
                        <span className="text-[12px] font-semibold text-slate-100">{result.domain}</span>
                      </div>
                      <a
                        href={result.resolved_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-0.5 block break-all text-[10px] text-slate-500 hover:text-cyan-200"
                      >
                        {result.resolved_url}
                      </a>
                    </div>
                    <span className="shrink-0 rounded-md border border-cyan-400/15 bg-cyan-400/[0.06] px-2 py-1 text-[9px] font-semibold text-cyan-200">
                      {result.label}
                    </span>
                  </div>

                  <div className="px-4 py-3">
                    <p className="text-[10px] text-slate-500">
                      <span className="font-semibold text-slate-300">{found}</span> role{found === 1 ? '' : 's'} found
                    </p>

                    <div className="mt-3 space-y-1.5">
                      {jobs.length ? (
                        jobs.map((job) => {
                          const checked = chosen.includes(job.url);
                          return (
                            <label
                              key={job.url}
                              className={`flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2 text-[11px] transition ${
                                checked
                                  ? 'border-cyan-400/15 bg-cyan-400/[0.05] text-slate-200'
                                  : 'border-white/[0.04] bg-white/[0.01] text-slate-500'
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleJob(index, job.url)}
                                className="checkbox-dark mt-0.5"
                              />
                              <span className="min-w-0 flex-1">
                                <span className="block font-medium">{job.title}</span>
                                <span className="mt-0.5 block truncate text-[9px] text-slate-600">{hostOf(job.url)}</span>
                              </span>
                              <a
                                href={job.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-slate-600 transition hover:text-cyan-200"
                                onClick={(event) => event.stopPropagation()}
                                title="Open role"
                              >
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            </label>
                          );
                        })
                      ) : (
                        <p className="rounded-lg border border-white/[0.04] bg-white/[0.01] px-3 py-3 text-[11px] italic text-slate-600">
                          No roles found on this page.
                        </p>
                      )}
                    </div>

                    {(result.warnings || []).length > 0 && (
                      <div className="mt-3 space-y-1">
                        {result.warnings.map((warning) => (
                          <p key={warning} className="text-[10px] leading-relaxed text-amber-200/60">
                            {warning}
                          </p>
                        ))}
                      </div>
                    )}

                    <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                      <label className="inline-flex cursor-pointer items-center gap-2 text-[10px] font-medium text-slate-400">
                        <input
                          type="checkbox"
                          checked={watching}
                          onChange={(event) => setWatch((current) => ({ ...current, [index]: event.target.checked }))}
                          className="checkbox-dark"
                        />
                        Watch on future Local runs
                      </label>
                      <button
                        type="button"
                        className="btn btn-primary btn-xs"
                        onClick={() => apply(index)}
                        disabled={applying !== null}
                      >
                        {applying === index ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : jobs.length ? (
                          <Plus className="h-3.5 w-3.5" />
                        ) : (
                          <Radio className="h-3.5 w-3.5" />
                        )}
                        {jobs.length ? `Add selected (${chosen.length})` : 'Watch this page'}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <aside className="lg:border-l lg:border-white/[0.07] lg:pl-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="flex items-center gap-2 text-[12px] font-semibold text-slate-200">
                <ShieldCheck className="h-3.5 w-3.5 text-cyan-300" />
                Watched sources
              </h3>
              <p className="mt-1 text-[10px] text-slate-500">Read during every Local / All run.</p>
            </div>
            <span className="rounded-md border border-white/[0.06] bg-white/[0.02] px-2 py-1 text-[9px] tabular-nums text-slate-500">
              {activeSites} active / {sites.length}
            </span>
          </div>

          {sitesError && <p className="mt-4 text-[11px] text-rose-300">{sitesError}</p>}

          <div className="mt-4 space-y-2">
            {sites.length ? (
              sites.map((site) => (
                <div
                  key={site.url}
                  className="rounded-lg border border-white/[0.06] bg-white/[0.015] px-3 py-2.5"
                >
                  <div className="flex items-start gap-2.5">
                    <input
                      type="checkbox"
                      checked={!!site.enabled}
                      onChange={(event) => toggleSite(site, event.target.checked)}
                      className="checkbox-dark mt-0.5"
                      title="Enable or pause this source"
                    />
                    <div className="min-w-0 flex-1">
                      <div className={`truncate text-[11px] font-semibold ${site.enabled ? 'text-slate-200' : 'text-slate-500'}`}>
                        {site.label || hostOf(site.url)}
                      </div>
                      <a
                        href={site.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-0.5 block break-all text-[9px] text-slate-600 hover:text-cyan-200"
                      >
                        {site.url}
                      </a>
                    </div>
                    <button
                      type="button"
                      onClick={() => setRemoveTarget(site.url)}
                      className="rounded p-1 text-slate-600 transition hover:bg-rose-500/10 hover:text-rose-300"
                      aria-label={`Remove ${site.label || site.url}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>

                  {removeTarget === site.url && (
                    <div className="mt-2 flex items-center justify-between gap-2 rounded-md border border-rose-400/15 bg-rose-500/[0.05] px-2.5 py-2">
                      <span className="text-[10px] text-rose-200/80">Stop watching this page?</span>
                      <div className="flex gap-1.5">
                        <button type="button" className="btn btn-ghost btn-xs" onClick={() => setRemoveTarget(null)}>
                          Cancel
                        </button>
                        <button type="button" className="btn btn-danger btn-xs" onClick={() => removeSite(site)}>
                          Remove
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="rounded-lg border border-dashed border-white/[0.08] px-4 py-8 text-center">
                <Link2 className="mx-auto h-5 w-5 text-slate-700" />
                <p className="mt-2 text-[11px] text-slate-500">No watched sources yet.</p>
                <p className="mt-1 text-[10px] text-slate-600">Scan a link to add one.</p>
              </div>
            )}
          </div>

          <div className="mt-5 rounded-lg border border-white/[0.06] bg-white/[0.015] p-3.5">
            <div className="flex items-center justify-between gap-2">
              <h4 className="flex items-center gap-2 text-[12px] font-semibold text-slate-200">
                <Search className="h-3.5 w-3.5 text-cyan-300" />
                Discovery searches
              </h4>
              <span className="rounded-md border border-white/[0.06] bg-white/[0.02] px-2 py-1 text-[9px] tabular-nums text-slate-500">
                {queries.length}/10
              </span>
            </div>
            <p className="mt-1.5 text-[10px] leading-relaxed text-slate-500">
              Optional web searches run during Local and All runs. Add any role or industry in your local
              market; leave this empty to rely on boards and watched pages only.
            </p>

            <form onSubmit={addQuery} className="mt-3 flex items-center gap-2">
              <input
                type="text"
                value={queryDraft}
                onChange={(event) => setQueryDraft(event.target.value.slice(0, 120))}
                maxLength={120}
                placeholder="e.g. accounting jobs nairobi"
                aria-label="New discovery search"
                disabled={savingQuery || queries.length >= 10}
                className="input-dark h-8 min-w-0 flex-1 text-[10px]"
              />
              <button
                type="submit"
                className="btn btn-primary btn-xs shrink-0"
                disabled={savingQuery || !queryDraft.trim() || queries.length >= 10}
              >
                {savingQuery ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
                Add
              </button>
            </form>

            {queriesError && <p className="mt-2 text-[10px] text-rose-300">{queriesError}</p>}

            <div className="mt-2 space-y-1.5">
              {queries.length ? (
                queries.map((query) => (
                  <div
                    key={query}
                    className="flex items-center justify-between gap-2 rounded-md border border-white/[0.05] bg-white/[0.02] px-2.5 py-1.5"
                  >
                    <span className="min-w-0 truncate text-[10px] text-slate-300">{query}</span>
                    <button
                      type="button"
                      onClick={() => removeQuery(query)}
                      disabled={savingQuery}
                      aria-label={`Remove search ${query}`}
                      className="rounded p-0.5 text-slate-600 transition hover:bg-rose-500/10 hover:text-rose-300"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))
              ) : (
                <p className="rounded-md border border-dashed border-white/[0.07] px-2.5 py-2 text-[10px] text-slate-600">
                  No web searches yet. Job boards and watched pages still run.
                </p>
              )}
            </div>
          </div>

          <div className="mt-5 space-y-2 rounded-lg border border-white/[0.05] bg-white/[0.015] p-3.5">
            <div className="flex items-start gap-2 text-[10px] leading-relaxed text-slate-500">
              <Check className="mt-0.5 h-3 w-3 shrink-0 text-cyan-300/70" />
              Short links are resolved and shown before import.
            </div>
            <div className="flex items-start gap-2 text-[10px] leading-relaxed text-slate-500">
              <Check className="mt-0.5 h-3 w-3 shrink-0 text-cyan-300/70" />
              Private addresses, credentials and unusual ports are rejected.
            </div>
            <div className="flex items-start gap-2 text-[10px] leading-relaxed text-slate-500">
              <Check className="mt-0.5 h-3 w-3 shrink-0 text-cyan-300/70" />
              Paused pages stay saved and can be re-enabled.
            </div>
          </div>

          <button
            type="button"
            className="btn btn-secondary btn-sm mt-4 w-full"
            onClick={() => {
              loadSites();
              loadQueries();
            }}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh sources
          </button>
        </aside>
      </div>
    </Modal>
  );
}
