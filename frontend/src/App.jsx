import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUpRight, Layers3, Sparkles } from 'lucide-react';
import Header from './components/Header';
import PreferencesPanel from './components/PreferencesPanel';
import FilterBar from './components/FilterBar';
import JobCard from './components/JobCard';
import JobDrawer from './components/JobDrawer';
import EmptyState from './components/EmptyState';
import KeywordManagerModal from './components/KeywordManagerModal';
import DeleteKeywordModal from './components/DeleteKeywordModal';
import DecisionModal from './components/DecisionModal';
import LocalSourcesModal from './components/LocalSourcesModal';
import ProfileModal from './components/ProfileModal';
import ScoringWeightsModal from './components/ScoringWeightsModal';
import Pagination from './components/Pagination';
import Toast from './components/Toast';
import { api } from './lib/api';
import { isFocused, passesFilters, sortJobs } from './lib/utils';
import { paginate } from './lib/pagination';

export default function App({ bootstrap }) {
  const [jobs, setJobs] = useState(Array.isArray(bootstrap.jobs) ? bootstrap.jobs : []);
  const [filters, setFilters] = useState({ focus: [], exclude: [] });
  const [tab, setTab] = useState('global');
  const [strictness, setStrictness] = useState('balanced');
  const [sortOrder, setSortOrder] = useState('recommended');
  const [appliedCount, setAppliedCount] = useState(Number(bootstrap.appliedCount) || 0);
  const [hiddenCount, setHiddenCount] = useState(Number(bootstrap.dismissedCount) || 0);
  const [keywordType, setKeywordType] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [decisionJob, setDecisionJob] = useState(null);
  const [drawerJob, setDrawerJob] = useState(null);
  const [localOpen, setLocalOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [weightsOpen, setWeightsOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [toast, setToast] = useState(null);
  const feedRef = useRef(null);

  const notify = useCallback((message, action = null) => {
    setToast({ message, action, key: Date.now() });
  }, []);

  const dismissToast = useCallback(() => setToast(null), []);

  const loadKeywords = useCallback(async () => {
    try {
      const data = await api('/api/keywords');
      setFilters({ focus: data.focus || [], exclude: data.exclude || [] });
    } catch {
      notify('Could not load keywords');
    }
  }, [notify]);

  useEffect(() => {
    loadKeywords();
  }, [loadKeywords]);

  const updateCounts = (data) => {
    if (!data) return;
    if (typeof data.applied_count === 'number') setAppliedCount(data.applied_count);
    if (typeof data.dismissed_count === 'number') setHiddenCount(data.dismissed_count);
  };

  const undoDecision = async (job) => {
    try {
      const data = await api('/api/decisions/delete', 'POST', { key: job.key });
      setJobs((current) => (current.some((item) => item.key === job.key) ? current : [...current, job]));
      updateCounts(data);
      notify('Restored to results');
    } catch {
      notify('Could not undo');
    }
  };

  const decide = async (job, status, reason = '', note = '') => {
    try {
      const data = await api('/api/decisions', 'POST', {
        key: job.key,
        status,
        reason,
        note,
        job: {
          title: job.title,
          company: job.company,
          location: job.location,
          url: job.url,
          source: job.source,
          score: job.score,
        },
      });
      setJobs((current) => current.filter((item) => item.key !== job.key));
      setDrawerJob(null);
      updateCounts(data);
      notify(status === 'applied' ? 'Marked as applied' : 'Hidden from results', {
        label: 'Undo',
        handler: () => undoDecision(job),
      });
    } catch {
      notify('Could not save that decision');
    }
  };

  const addKeyword = async (type, value, group = '') => {
    try {
      await api('/api/keywords/add', 'POST', { type, value, group });
      await loadKeywords();
      notify(group ? `Added “${value}” to ${group}` : `Added “${value}”`);
      return true;
    } catch {
      notify('Could not add keyword');
      return false;
    }
  };

  const confirmDeleteKeyword = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setDeleteTarget(null);
    try {
      await api('/api/keywords/delete', 'POST', { type: target.type, values: [target.value] });
      await loadKeywords();
      notify(`Deleted “${target.value}”`);
    } catch {
      notify('Could not delete keyword');
    }
  };

  const saveKeywordStates = async (states, groups) => {
    if (!keywordType) return;
    const type = keywordType;
    try {
      await api('/api/keywords/state', 'POST', { type, states, groups });
      setKeywordType(null);
      await loadKeywords();
      notify('Keyword settings saved');
    } catch {
      notify('Could not save keyword settings');
    }
  };

  const refreshJobs = async () => {
    try {
      const data = await api('/api/jobs');
      if (Array.isArray(data)) setJobs(data);
    } catch {
      /* Keep the current list if the refresh fails. */
    }
  };

  const handleLocalImported = async () => {
    await refreshJobs();
    setTab('local');
  };

  const submitDismissal = async (reason, note) => {
    if (!reason) {
      notify('Pick a reason first');
      return;
    }
    const job = decisionJob;
    setDecisionJob(null);
    if (job) await decide(job, 'dismissed', reason, note);
  };

  const activeFocus = filters.focus.filter((item) => item.enabled).length;
  const activeExclude = filters.exclude.filter((item) => item.enabled).length;
  const pausedCount =
    filters.focus.filter((item) => !item.enabled).length +
    filters.exclude.filter((item) => !item.enabled).length;

  const tabCounts = useMemo(
    () => ({
      global: jobs.filter((job) => job.source === 'global').length,
      local: jobs.filter((job) => job.source === 'local').length,
    }),
    [jobs],
  );

  const visibleJobs = useMemo(() => {
    const filtered = jobs.filter(
      (job) => job.source === tab && passesFilters(job, filters, strictness),
    );
    return sortJobs(filtered, sortOrder);
  }, [jobs, tab, filters, strictness, sortOrder]);

  const pageData = useMemo(() => paginate(visibleJobs, page), [visibleJobs, page]);

  useEffect(() => {
    setPage(1);
  }, [tab, filters, strictness, sortOrder]);

  useEffect(() => {
    if (page > pageData.totalPages) setPage(pageData.totalPages);
  }, [page, pageData.totalPages]);

  const goToPage = (next) => {
    const target = Math.min(Math.max(1, Number(next) || 1), pageData.totalPages);
    if (target === pageData.page) return;
    setPage(target);
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    requestAnimationFrame(() => {
      feedRef.current?.scrollIntoView({
        behavior: reduceMotion ? 'auto' : 'smooth',
        block: 'start',
      });
    });
  };

  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <div className="pointer-events-none fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-ink-900" />
        <div className="ambient-grid absolute inset-0 opacity-60" />
        <div className="absolute -left-40 top-[-180px] h-[520px] w-[520px] rounded-full bg-cyan-500/[0.07] blur-[120px]" />
        <div className="absolute left-[45%] top-[-260px] h-[620px] w-[620px] rounded-full bg-blue-600/[0.09] blur-[140px]" />
        <div className="absolute right-[-160px] top-[160px] h-[380px] w-[380px] rounded-full bg-cyan-400/[0.04] blur-[100px]" />
        <div className="absolute bottom-0 left-1/2 h-[300px] w-[700px] -translate-x-1/2 rounded-full bg-blue-700/[0.04] blur-[120px]" />
      </div>

      <main className="relative mx-auto max-w-[1240px] px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
        <Header appliedCount={appliedCount} hiddenCount={hiddenCount} />

        <div className="mt-4 space-y-4">
          <PreferencesPanel
            filters={filters}
            activeFocus={activeFocus}
            activeExclude={activeExclude}
            pausedCount={pausedCount}
            onAddKeyword={addKeyword}
            onDeleteKeyword={(type, value) => setDeleteTarget({ type, value })}
            onManageKeywords={setKeywordType}
            onOpenLocalSources={() => setLocalOpen(true)}
            onOpenProfile={() => setProfileOpen(true)}
            onOpenWeights={() => setWeightsOpen(true)}
          />

          <FilterBar
            tab={tab}
            onTabChange={setTab}
            counts={tabCounts}
            strictness={strictness}
            onStrictnessChange={setStrictness}
            sortOrder={sortOrder}
            onSortChange={setSortOrder}
            visibleCount={visibleJobs.length}
          />

          <div
            ref={feedRef}
            className="flex scroll-mt-24 flex-wrap items-end justify-between gap-3 px-0.5 pt-1"
          >
            <div>
              <div className="flex items-center gap-2 text-[9px] font-semibold uppercase tracking-[0.24em] text-cyan-300/60">
                <Layers3 className="h-3 w-3" />
                Opportunity feed
              </div>
              <h2 className="mt-1 text-[19px] font-semibold tracking-[-0.025em] text-slate-100">
                {tab === 'global' ? 'Global Results' : 'Local Results'}
              </h2>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-slate-500">
              <Sparkles className="h-3 w-3 text-cyan-300/50" />
              <span className="tabular-nums">{visibleJobs.length}</span>
              result{visibleJobs.length === 1 ? '' : 's'}
              {activeFocus > 0 && (
                <span className="ml-1 hidden rounded-md border border-cyan-400/10 bg-cyan-400/[0.04] px-1.5 py-0.5 text-[9px] text-cyan-300/60 sm:inline">
                  {activeFocus} highlight signals
                </span>
              )}
            </div>
          </div>

          {visibleJobs.length ? (
            <div className="space-y-2.5">
              {pageData.items.map((job) => (
                <JobCard
                  key={job.key || `${job.source}-${job.url}-${job.title}`}
                  job={job}
                  focused={isFocused(job, filters)}
                  onReview={setDrawerJob}
                  onApplied={(target) => decide(target, 'applied')}
                  onDismiss={setDecisionJob}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              title="No roles match this view"
              message="Try a more lenient strictness level, adjust your hide keywords, or run the scrapers to refresh the feed."
            />
          )}

          {visibleJobs.length > 0 && (
            <Pagination
              page={pageData.page}
              totalPages={pageData.totalPages}
              total={pageData.total}
              start={pageData.start}
              end={pageData.end}
              onPageChange={goToPage}
            />
          )}
        </div>

        <footer className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.04] py-4 text-[9px] text-slate-700">
          <span className="uppercase tracking-[0.18em]">J-Search · Your digital navigator</span>
          <span className="inline-flex items-center gap-1.5">
            Review-gated imports
            <ArrowUpRight className="h-2.5 w-2.5" />
            Local-first
          </span>
        </footer>
      </main>

      {keywordType && (
        <KeywordManagerModal
          type={keywordType}
          items={filters[keywordType]}
          onClose={() => setKeywordType(null)}
          onSave={saveKeywordStates}
        />
      )}

      {deleteTarget && (
        <DeleteKeywordModal
          pending={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={confirmDeleteKeyword}
        />
      )}

      {decisionJob && (
        <DecisionModal
          job={decisionJob}
          onClose={() => setDecisionJob(null)}
          onSubmit={submitDismissal}
        />
      )}

      {localOpen && (
        <LocalSourcesModal
          onClose={() => setLocalOpen(false)}
          notify={notify}
          onImported={handleLocalImported}
        />
      )}

      {profileOpen && (
        <ProfileModal strictness={strictness} onClose={() => setProfileOpen(false)} />
      )}

      {weightsOpen && (
        <ScoringWeightsModal
          strictness={strictness}
          onClose={() => setWeightsOpen(false)}
          onSaved={async () => {
            setWeightsOpen(false);
            await refreshJobs();
            notify('Keyword weights saved — scores refreshed');
          }}
        />
      )}

      <JobDrawer
        job={drawerJob}
        onClose={() => setDrawerJob(null)}
        onApplied={(job) => decide(job, 'applied')}
        onDismiss={(job) => {
          setDrawerJob(null);
          setDecisionJob(job);
        }}
      />

      <Toast toast={toast} onDismiss={dismissToast} />
    </div>
  );
}
