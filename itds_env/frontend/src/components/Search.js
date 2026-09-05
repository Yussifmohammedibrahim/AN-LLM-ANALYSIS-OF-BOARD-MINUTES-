
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { aiAPI } from '../api/api';
import { ensureArray } from '../utils/safeMap';
import { Search as SearchIcon, Filter, FileText, Calendar, Tag, X } from 'lucide-react';
import { notifyError, notifyWarning } from '../utils/notify';
import { SelectionProvider, useSelection } from './selection/SelectionContext';
import BulkActionsBar from './BulkActionsBar';
import { useLanguage } from '../context/LanguageContext';

// Helper available to the whole module (used by SearchRow and Search)
const getSentimentClass = (sentiment) => {
  switch ((sentiment || '').toUpperCase()) {
    case 'POSITIVE': return 'tag-success';
    case 'NEGATIVE': return 'tag-danger';
    default: return 'tag-neutral';
  }
};

const Search = () => {
  const { t } = useLanguage();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [filters, setFilters] = useState({
    category: '',
    startDate: '',
    endDate: '',
    sentiment: ''
  });
  const [showFilters, setShowFilters] = useState(false);
  const [themes, setThemes] = useState([]);
  const [selectedResultIndex, setSelectedResultIndex] = useState(-1);
  const [showResultModal, setShowResultModal] = useState(false);
  const modalBodyRef = useRef(null);
  const filterPanelRef = useRef(null);
  const selectedResult = selectedResultIndex >= 0 && selectedResultIndex < results.length
    ? results[selectedResultIndex]
    : null;

  const hasActiveFilters = Boolean(
    filters.sentiment || filters.category || filters.startDate || filters.endDate
  );

  useEffect(() => {
    const loadThemes = async () => {
      try {
        const response = await aiAPI.getDynamicThemes();
        const apiThemes = ensureArray(response?.data?.themes).map((item) => item.name).filter(Boolean);
        setThemes(apiThemes);
      } catch (error) {
        setThemes([]);
      }
    };
    loadThemes();
  }, []);

  const executeSearch = useCallback(async (override = {}) => {
    const nextQuery = (override.query ?? query).trim();
    const nextFilters = {
      ...filters,
      ...(override.filters || {})
    };

    if (!nextQuery && !nextFilters.sentiment && !nextFilters.category && !nextFilters.startDate && !nextFilters.endDate) {
      notifyWarning(t('searchProvideKeywordOrFilter'));
      return;
    }

    setLoading(true);
    setHasSearched(true);

    try {
      const response = await aiAPI.searchRealtimeAnalytics({
        q: nextQuery,
        sentiment: nextFilters.sentiment ? nextFilters.sentiment.toLowerCase() : '',
        start_date: nextFilters.startDate,
        end_date: nextFilters.endDate,
        category: nextFilters.category,
        limit: 100
      });
      setResults(ensureArray(response?.data?.results));
    } catch (error) {
      console.error('Search error:', error);
      setResults([]);
      notifyError(t('searchServiceUnavailable'));
    } finally {
      setLoading(false);
    }
  }, [query, filters, t]);

  const handleSearch = async (e) => {
    e.preventDefault();
    await executeSearch();
  };

  const clearSearch = () => {
    setQuery('');
    setResults([]);
    setHasSearched(false);
    setFilters({ category: '', startDate: '', endDate: '', sentiment: '' });
    setSelectedResultIndex(-1);
    setShowResultModal(false);
  };

  useEffect(() => {
    if (!hasSearched) return undefined;

    const interval = setInterval(() => {
      if (query.trim() || filters.sentiment || filters.category || filters.startDate || filters.endDate) {
        executeSearch();
      }
    }, 15000);

    return () => clearInterval(interval);
  }, [hasSearched, query, filters, executeSearch]);

  useEffect(() => {
    if (!showResultModal) return;
    if (selectedResultIndex < 0 || selectedResultIndex >= results.length) {
      setShowResultModal(false);
      setSelectedResultIndex(-1);
    }
  }, [results, selectedResultIndex, showResultModal]);

  useEffect(() => {
    if (!showResultModal) return undefined;

    const handleModalKeys = (event) => {
      if (event.key === 'Escape') {
        setShowResultModal(false);
        return;
      }
      if (event.key === 'ArrowLeft' && selectedResultIndex > 0) {
        setSelectedResultIndex((prev) => prev - 1);
      }
      if (event.key === 'ArrowRight' && selectedResultIndex < results.length - 1) {
        setSelectedResultIndex((prev) => prev + 1);
      }
    };

    document.addEventListener('keydown', handleModalKeys);
    return () => document.removeEventListener('keydown', handleModalKeys);
  }, [showResultModal, selectedResultIndex, results.length]);

  useEffect(() => {
    if (!showResultModal || !query.trim()) return;

    const timer = setTimeout(() => {
      const container = modalBodyRef.current;
      if (!container) return;

      const firstMatch = container.querySelector('.search-highlight');
      if (firstMatch && typeof firstMatch.scrollIntoView === 'function') {
        firstMatch.scrollIntoView({ behavior: 'smooth', block: 'center' });
        firstMatch.classList.remove('search-highlight-flash');
        void firstMatch.offsetWidth;
        firstMatch.classList.add('search-highlight-flash');

        setTimeout(() => {
          firstMatch.classList.remove('search-highlight-flash');
        }, 700);
      }
    }, 60);

    return () => clearTimeout(timer);
  }, [showResultModal, selectedResultIndex, query]);

  useEffect(() => {
    if (!showFilters) return undefined;

    const handleOutsideClick = (event) => {
      if (filterPanelRef.current && !filterPanelRef.current.contains(event.target)) {
        setShowFilters(false);
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [showFilters]);

  const openResultAt = (index) => {
    setSelectedResultIndex(index);
    setShowResultModal(true);
  };

  const goToPreviousResult = () => {
    setSelectedResultIndex((prev) => Math.max(0, prev - 1));
  };

  const goToNextResult = () => {
    setSelectedResultIndex((prev) => Math.min(results.length - 1, prev + 1));
  };

  const renderHighlightedText = (text) => {
    const safeText = String(text || '');
    const term = query.trim();
    if (!term) return safeText;

    const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escaped})`, 'ig');
    const parts = safeText.split(regex);
    const termLower = term.toLowerCase();

    return parts.map((part, idx) => (
      part.toLowerCase() === termLower
        ? <mark key={`${part}-${idx}`} className="search-highlight">{part}</mark>
        : <React.Fragment key={`${part}-${idx}`}>{part}</React.Fragment>
    ));
  };

  

  return (
    <div className="dashboard">
      <div className="page-header">
        <h1 className="page-title">{t('searchTitle')}</h1>
        <p className="page-subtitle">{t('searchSubtitle')}</p>
      </div>

      {/* Search Form */}
<div className="search-container">
          <form onSubmit={handleSearch}>
            <div className="search-wrapper">
              <SearchIcon size={20} className="search-icon" />
              <input
                type="text"
                className="search-input"
                placeholder={t('searchPlaceholderLong')}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {query && (
                <button
                  type="button"
                  onClick={clearSearch}
                  className="search-clear-btn"
                  aria-label={t('searchClear')}
                >
                  <X size={18} />
                </button>
              )}
            </div>
            <div ref={filterPanelRef} style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', justifyContent: 'flex-start', flexWrap: 'wrap' }}>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? t('searchSearching') : t('searchSearch')}
              </button>
              <button
                type="button"
                className={`btn ${showFilters ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setShowFilters(!showFilters)}
              >
                <Filter size={16} />
                {t('searchFilters')}
              </button>
              {(query || hasActiveFilters) && (
                <button type="button" className="btn btn-ghost" onClick={clearSearch}>
                  {t('searchClear')}
                </button>
              )}
            </div>
          </form>

        {/* Filter Panel */}
        {showFilters && (
          <div className="card mt-4" style={{ animation: 'fadeIn 0.2s ease' }}>
            <div className="card-body">
              <h4 style={{ marginBottom: '1rem', fontWeight: 600 }}>{t('searchFilterResults')}</h4>
              <div className="grid grid-3">
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">{t('searchCategoryTheme')}</label>
                  <select
                    className="form-select"
                    value={filters.category}
                    onChange={(e) => setFilters({ ...filters, category: e.target.value })}
                  >
                    <option value="">{t('searchAllCategories')}</option>
                    {themes.map(theme => (
                      <option key={theme} value={theme}>{theme}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">{t('searchStartDate')}</label>
                  <input
                    type="date"
                    className="form-input"
                    value={filters.startDate}
                    onChange={(e) => setFilters({ ...filters, startDate: e.target.value })}
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">{t('searchEndDate')}</label>
                  <input
                    type="date"
                    className="form-input"
                    value={filters.endDate}
                    onChange={(e) => setFilters({ ...filters, endDate: e.target.value })}
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">{t('searchSentiment')}</label>
                  <select
                    className="form-select"
                    value={filters.sentiment}
                    onChange={(e) => setFilters({ ...filters, sentiment: e.target.value })}
                  >
                    <option value="">{t('searchAllSentiments')}</option>
                    <option value="POSITIVE">{t('searchPositive')}</option>
                    <option value="NEUTRAL">{t('searchNeutral')}</option>
                    <option value="NEGATIVE">{t('searchNegative')}</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Results */}
      {hasSearched && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">
              {t('searchResults')}
              {results.length > 0 && ` (${results.length} ${t('searchFound')})`}
            </h3>
          </div>
          <div className="card-body">
              {loading ? (
              <div className="loading">
                <div className="spinner"></div>
              </div>
            ) : results.length === 0 ? (
              <div className="empty-state">
                <SearchIcon size={48} className="empty-icon" />
                <h3 className="empty-title">{t('searchNoResults')}</h3>
                <p>{t('searchTryDifferent')}</p>
              </div>
              ) : (
              <SelectionProvider>
                <div className="table-container">
                  <BulkActionsBar itemsMap={results.reduce((acc, r) => { acc[r.transcript_id || r.id || JSON.stringify(r)] = r; return acc; }, {})} onDeleteComplete={() => executeSearch()} />
                  <table className="table" role="table" aria-label="Search results table">
                    <thead>
                      <tr>
                        <th>
                          <SelectAllCheckbox results={results} />
                        </th>
                        <th>{t('searchDate')}</th>
                        <th>{t('searchCategory')}</th>
                        <th>{t('searchContent')}</th>
                        <th>{t('searchSentiment')}</th>
                        <th>{t('searchActions')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.map((result, index) => (
                        <SearchRow
                          key={`${result.source || 'entry'}-${result.transcript_id || index}-${index}`}
                          result={result}
                          index={index}
                          openResultAt={openResultAt}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </SelectionProvider>
            )}
          </div>
        </div>
      )}

      {/* Quick Filters */}
      {themes.length > 0 && (
        <div className="card mt-4">
          <div className="card-header">
            <h3 className="card-title">{t('searchQuickFilters')}</h3>
          </div>
          <div className="card-body">
            <div className="flex gap-2 flex-wrap">
              {themes.slice(0, 5).map((filter) => (
                <button
                  key={filter}
                  className="btn btn-outline btn-sm"
                  onClick={() => {
                    const nextFilters = { ...filters, category: filter };
                    setFilters(nextFilters);
                    executeSearch({ filters: nextFilters });
                  }}
                >
                  <Tag size={14} />
                  {filter}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {showResultModal && selectedResult && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setShowResultModal(false); }}>
          <div className="modal report-preview-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">{t('searchResultDetail')}</h3>
              <button className="modal-close" onClick={() => setShowResultModal(false)} aria-label={t('searchCloseResultPreview')}>
                <X size={18} />
              </button>
            </div>
            <div ref={modalBodyRef} className="modal-body report-preview-body">
              <div className="form-group">
                <label className="form-label">{t('searchSource')}</label>
                <div>{selectedResult.source || t('reportsNA')}</div>
              </div>
              <div className="form-group">
                <label className="form-label">{t('searchDate')}</label>
                <div>{selectedResult.created_at ? new Date(selectedResult.created_at).toLocaleString() : t('reportsNA')}</div>
              </div>
              <div className="form-group">
                <label className="form-label">{t('searchSentiment')}</label>
                <div>{(selectedResult.sentiment || 'NEUTRAL').toUpperCase()}</div>
              </div>
              <div className="form-group">
                <label className="form-label">{t('searchCategoryKeywords')}</label>
                <div className="report-preview-value">{renderHighlightedText(selectedResult.keywords || t('searchGeneral'))}</div>
              </div>
              <div className="form-group">
                <label className="form-label">{t('searchContent')}</label>
                <div className="report-preview-value">{renderHighlightedText(selectedResult.transcript_text || t('searchNoContent'))}</div>
              </div>
            </div>
            <div className="modal-footer">
              <div className="search-modal-nav text-sm text-secondary">
                {t('searchResultOf', { index: selectedResultIndex + 1, total: results.length })}
              </div>
              <button
                className="btn btn-outline"
                onClick={goToPreviousResult}
                disabled={selectedResultIndex <= 0}
              >
                {t('searchPrevious')}
              </button>
              <button
                className="btn btn-outline"
                onClick={goToNextResult}
                disabled={selectedResultIndex >= results.length - 1}
              >
                {t('searchNext')}
              </button>
              <button className="btn btn-primary" onClick={() => setShowResultModal(false)}>{t('close')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Search;

// --- Accessible row and select-all helpers ---
const SelectAllCheckbox = ({ results = [] }) => {
  const { selected, selectAll, clear } = useSelection();
  const allIds = results.map(r => r.transcript_id || r.id || JSON.stringify(r));
  const allSelected = allIds.length > 0 && allIds.every(id => selected.has(id));
  const someSelected = allIds.some(id => selected.has(id));

  const onChange = (e) => {
    if (e.target.checked) selectAll(allIds);
    else clear();
  };

  return (
    <input
      type="checkbox"
      aria-label="Select all results"
      checked={allSelected}
      ref={(el) => { if (el) el.indeterminate = !allSelected && someSelected; }}
      onChange={onChange}
    />
  );
};

const SearchRow = ({ result, index, openResultAt }) => {
  const id = result.transcript_id || result.id || JSON.stringify(result);
  const { selected, toggle } = useSelection();
  const isSelected = selected.has(id);

  const handleKey = (e) => {
    if (e.key === ' ') {
      e.preventDefault();
      toggle(id);
    }
    if (e.key === 'Enter') {
      openResultAt(index);
    }
  };

  return (
    <tr tabIndex={0} onKeyDown={handleKey} aria-selected={isSelected} className={isSelected ? 'row-selected' : ''}>
      <td>
        <input
          type="checkbox"
          aria-label={`Select item ${index + 1}`}
          checked={isSelected}
          onChange={() => toggle(id)}
          onClick={(e) => e.stopPropagation()}
        />
      </td>
      <td>
        <div className="flex items-center gap-2">
          <Calendar size={16} className="text-secondary" />
          {result.created_at ? new Date(result.created_at).toLocaleString() : 'N/A'}
        </div>
      </td>
      <td>
        <span className="tag tag-primary search-keyword-tag">{result.keywords || 'General'}</span>
      </td>
      <td style={{ maxWidth: '400px' }}>
        <p className="truncate">{result.transcript_text}</p>
      </td>
      <td>
        <span className={`tag ${getSentimentClass((result.sentiment || '').toUpperCase())}`}>
          {(result.sentiment || 'NEUTRAL').toUpperCase()}
        </span>
      </td>
      <td>
        <button className="btn btn-ghost btn-sm" onClick={() => openResultAt(index)}>
          <FileText size={16} />
          {" "}{'View'}
        </button>
      </td>
    </tr>
  );
};