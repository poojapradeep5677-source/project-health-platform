import React, { useEffect, useState, useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Search,
  Filter,
  FileCode2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Eye,
  X,
  BookOpen,
} from 'lucide-react';
import { usePlatform } from '../context/PlatformContext';
import { platformApi, extractApiError } from '../services/api';
import EmptyProjectState from '../components/EmptyProjectState';
import {
  Card,
  CardHeader,
  DataTable,
  Drawer,
  StatusChip,
  LoadingSkeleton,
  ErrorBanner,
} from '../components/ui';

const METRIC_DEFINITIONS = [
  {
    name: 'Lines of Code (LOC)',
    status: 'Calculated',
    formula: 'Non-blank, non-comment physical source lines',
  },
  {
    name: 'Cyclomatic Complexity (CC)',
    status: 'Calculated (AST)',
    formula: '1 + AST branching nodes (if, for, while, do, case, catch, ?:, &&, ||)',
  },
  {
    name: 'Maintainability Index (MI)',
    status: 'Calculated (AST+Lexical)',
    formula: 'Normalized SEI 0–100 index from Halstead Volume, CC, LOC, and Comment Ratio',
  },
  {
    name: 'Coupling Fan-Out',
    status: 'Calculated (AST)',
    formula: 'Distinct external reference types + non-standard package imports',
  },
  {
    name: 'Dynamic Test Coverage',
    status: 'Unavailable (Static Only)',
    formula: 'Requires JVM runtime test execution (excluded for security)',
  },
];

export default function ProjectAnalysisPage() {
  const location = useLocation();
  const { activeProject, activeRun, loadingInitial } = usePlatform();
  const [analysisData, setAnalysisData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showDefinitions, setShowDefinitions] = useState(false);

  // Table search, filter, sort, pagination state
  const [searchQuery, setSearchQuery] = useState('');
  const [riskFilter, setRiskFilter] = useState('ALL');
  const [parseFilter, setParseFilter] = useState('ALL');
  const [minComplexityFilter, setMinComplexityFilter] = useState(0);
  const [sortField, setSortField] = useState('cyclomatic_complexity');
  const [sortOrder, setSortOrder] = useState('desc');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  // Selected file for dark detail side drawer
  const [selectedFile, setSelectedFile] = useState(null);

  useEffect(() => {
    if (!activeRun?.id) {
      setAnalysisData(null);
      return;
    }
    let cancelled = false;
    async function loadAnalysis() {
      try {
        setLoading(true);
        setError(null);
        const data = await platformApi.getAnalysisRun(activeRun.id);
        if (!cancelled) {
          setAnalysisData(data);
          const params = new URLSearchParams(location.search);
          const targetFilePath = params.get('file');
          if (targetFilePath && data.files) {
            const match = data.files.find(
              (f) => f.file_path === targetFilePath || f.file_name === targetFilePath
            );
            setSelectedFile(match || null);
          } else {
            setSelectedFile(null);
          }
        }
      } catch (err) {
        if (!cancelled) setError(extractApiError(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadAnalysis();
    return () => {
      cancelled = true;
    };
  }, [activeRun?.id, location.search]);

  const files = analysisData?.files || [];

  const filteredAndSortedFiles = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = files.filter((f) => {
      const matchesQuery =
        !q ||
        f.file_name.toLowerCase().includes(q) ||
        f.file_path.toLowerCase().includes(q) ||
        (f.package_name || '').toLowerCase().includes(q);
      const matchesRisk = riskFilter === 'ALL' || f.risk_category === riskFilter;
      const matchesParse = parseFilter === 'ALL' || f.parse_status === parseFilter;
      const matchesCc = (f.cyclomatic_complexity || 0) >= Number(minComplexityFilter || 0);
      return matchesQuery && matchesRisk && matchesParse && matchesCc;
    });

    filtered.sort((a, b) => {
      const valA = a[sortField] ?? -1;
      const valB = b[sortField] ?? -1;
      if (typeof valA === 'string') {
        return sortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      return sortOrder === 'asc' ? valA - valB : valB - valA;
    });

    return filtered;
  }, [files, searchQuery, riskFilter, parseFilter, minComplexityFilter, sortField, sortOrder]);

  const handleSortChange = (field, order) => {
    setSortField(field);
    setSortOrder(order);
    setCurrentPage(1);
  };

  if (loadingInitial || loading) {
    return <LoadingSkeleton rows={3} />;
  }

  if (!activeProject || !activeRun) {
    return <EmptyProjectState title="No Project Selected for File Analysis" />;
  }

  const summary = analysisData || activeRun;

  const columns = [
    {
      key: 'file_name',
      label: 'File & Package',
      sortable: true,
      defaultSortOrder: 'asc',
      render: (f) => (
        <div className="flex items-start gap-2">
          <FileCode2
            className={`w-4 h-4 mt-0.5 shrink-0 ${
              f.parse_status === 'SUCCESS' ? 'text-[#7C5CFF]' : 'text-[#EF4444]'
            }`}
          />
          <div className="min-w-0">
            <div className="font-mono font-medium text-[#F4F4F5] flex items-center gap-1.5">
              <span className="truncate">{f.file_name}</span>
              {f.parse_status !== 'SUCCESS' && (
                <StatusChip status="PARSE_ERROR" variant="danger" size="xs" />
              )}
            </div>
            <div className="text-[11px] font-mono text-[#6B6B76] truncate max-w-xs">
              {f.file_path}
            </div>
          </div>
        </div>
      ),
    },
    {
      key: 'loc',
      label: 'LOC',
      sortable: true,
      align: 'right',
      mono: true,
      render: (f) => <span className="text-[#F4F4F5]">{f.loc}</span>,
    },
    {
      key: 'method_count',
      label: 'Methods',
      sortable: true,
      align: 'right',
      mono: true,
      render: (f) =>
        f.parse_status === 'SUCCESS' ? (
          <span className="text-[#A1A1AA]">{f.method_count}</span>
        ) : (
          <span className="text-[#6B6B76]">N/A</span>
        ),
    },
    {
      key: 'cyclomatic_complexity',
      label: 'Complexity (CC)',
      sortable: true,
      align: 'right',
      mono: true,
      render: (f) =>
        f.parse_status === 'SUCCESS' ? (
          <span
            className={`font-semibold ${
              f.cyclomatic_complexity >= 20
                ? 'text-[#EF4444]'
                : f.cyclomatic_complexity >= 12
                ? 'text-[#F97316]'
                : 'text-[#F4F4F5]'
            }`}
          >
            {f.cyclomatic_complexity}
          </span>
        ) : (
          <span className="text-[#6B6B76]">N/A</span>
        ),
    },
    {
      key: 'maintainability_index',
      label: 'Maintainability',
      sortable: true,
      align: 'right',
      mono: true,
      render: (f) =>
        f.maintainability_index !== null && f.maintainability_index !== undefined ? (
          <span
            className={`font-semibold ${
              f.maintainability_index < 55
                ? 'text-[#EF4444]'
                : f.maintainability_index < 70
                ? 'text-[#EAB308]'
                : 'text-[#22C55E]'
            }`}
          >
            {f.maintainability_index.toFixed(1)}
          </span>
        ) : (
          <span className="text-[#6B6B76]">N/A</span>
        ),
    },
    {
      key: 'fan_out',
      label: 'Coupling',
      sortable: true,
      align: 'right',
      mono: true,
      render: (f) =>
        f.parse_status === 'SUCCESS' ? (
          <span className="text-[#A1A1AA]">{f.fan_out}</span>
        ) : (
          <span className="text-[#6B6B76]">N/A</span>
        ),
    },
    {
      key: 'comment_ratio',
      label: 'Comment %',
      sortable: true,
      align: 'right',
      mono: true,
      render: (f) => <span className="text-[#A1A1AA]">{f.comment_ratio}%</span>,
    },
    {
      key: 'code_smell_count',
      label: 'Smells',
      sortable: true,
      align: 'right',
      mono: true,
      render: (f) =>
        f.parse_status === 'SUCCESS' ? (
          <span
            className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${
              f.code_smell_count > 0
                ? 'bg-[#EAB308]/12 text-[#EAB308] border-[#EAB308]/30'
                : 'bg-[#22C55E]/12 text-[#22C55E] border-[#22C55E]/30'
            }`}
          >
            {f.code_smell_count}
          </span>
        ) : (
          <span className="text-[#6B6B76]">—</span>
        ),
    },
    {
      key: 'risk_score',
      label: 'Risk',
      sortable: true,
      align: 'right',
      render: (f) => (
        <div className="inline-flex items-center gap-1.5 justify-end">
          <span className="font-mono text-[11px] text-[#A1A1AA] tabular-nums">
            {f.risk_score?.toFixed(1)}
          </span>
          <StatusChip status={f.risk_category || 'LOW'} size="xs" />
        </div>
      ),
    },
    {
      key: 'actions',
      label: 'Inspect',
      align: 'center',
      render: (f) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setSelectedFile(f);
          }}
          className="ui-btn-secondary px-2 py-1 text-[11px] inline-flex items-center gap-1 cursor-pointer"
        >
          <Eye className="w-3 h-3 text-[#7C5CFF]" />
          <span>Details</span>
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {/* Project-Level Summary Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          {
            label: 'Total Files',
            value: summary.total_files,
            sub: `${summary.parsed_files} parsed, ${summary.failed_files} failed`,
          },
          {
            label: 'Lines of Code',
            value: summary.total_loc?.toLocaleString(),
            sub: `${summary.total_lines?.toLocaleString()} physical lines`,
          },
          {
            label: 'Classes & Interfaces',
            value: summary.total_classes,
            sub: `${summary.total_methods} total methods`,
          },
          {
            label: 'Avg Complexity',
            value: summary.avg_complexity,
            sub: `Max file CC: ${summary.max_complexity}`,
          },
          {
            label: 'Avg Maintainability',
            value: summary.avg_maintainability !== null ? `${summary.avg_maintainability}/100` : 'N/A',
            sub: 'SEI Normalized Index',
          },
          {
            label: 'Avg Comment Ratio',
            value: `${summary.avg_comment_ratio}%`,
            sub: `${summary.total_comment_lines} comment lines`,
          },
        ].map((item) => (
          <Card key={item.label} padding="p-3.5">
            <div className="text-[10px] font-semibold uppercase tracking-[0.07em] text-[#A1A1AA]">
              {item.label}
            </div>
            <div className="text-lg font-semibold font-mono text-[#F4F4F5] mt-1 tabular-nums">
              {item.value}
            </div>
            <div className="text-[11px] text-[#6B6B76] mt-0.5 truncate">{item.sub}</div>
          </Card>
        ))}
      </div>

      {/* Calculated vs Unsupported Metric Transparency Toggle */}
      <Card padding="p-3.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs text-[#A1A1AA]">
            <BookOpen className="w-4 h-4 text-[#7C5CFF] shrink-0" />
            <span>
              <strong className="text-[#F4F4F5]">Metric Support Transparency:</strong> Static AST &
              lexical metrics are calculated directly from source files; runtime metrics are
              explicitly marked unavailable.
            </span>
          </div>
          <button
            type="button"
            onClick={() => setShowDefinitions((prev) => !prev)}
            className="text-xs font-semibold text-[#7C5CFF] hover:underline cursor-pointer"
          >
            {showDefinitions ? 'Hide Metric Definitions' : 'View Metric Definitions & Scope'}
          </button>
        </div>

        {showDefinitions && (
          <div className="mt-3 pt-3 border-t border-[#1F1F25] grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2.5">
            {METRIC_DEFINITIONS.map((m) => (
              <div
                key={m.name}
                className="p-2.5 rounded-lg bg-[#0E0E11] border border-[#1F1F25] text-xs"
              >
                <div className="font-semibold text-[#F4F4F5]">{m.name}</div>
                <div className="mt-1">
                  <StatusChip
                    status={m.status}
                    variant={m.status.includes('Calculated') ? 'success' : 'muted'}
                    size="xs"
                  />
                </div>
                <p className="text-[11px] text-[#A1A1AA] mt-1.5 leading-relaxed">{m.formula}</p>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Search & Filter Controls */}
      <Card padding="p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <div className="lg:col-span-2 relative">
            <Search className="w-4 h-4 text-[#6B6B76] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              placeholder="Search by file name, path, or Java package..."
              className="w-full pl-9 pr-3 py-2 ui-input"
              aria-label="Search files"
            />
          </div>

          <div>
            <select
              value={riskFilter}
              onChange={(e) => {
                setRiskFilter(e.target.value);
                setCurrentPage(1);
              }}
              aria-label="Filter by Risk Category"
              className="w-full px-3 py-2 ui-input"
            >
              <option value="ALL">All Risk Categories</option>
              <option value="HIGH">High Risk Only</option>
              <option value="MEDIUM">Medium Risk Only</option>
              <option value="LOW">Low Risk Only</option>
            </select>
          </div>

          <div>
            <select
              value={parseFilter}
              onChange={(e) => {
                setParseFilter(e.target.value);
                setCurrentPage(1);
              }}
              aria-label="Filter by Parse Status"
              className="w-full px-3 py-2 ui-input"
            >
              <option value="ALL">All Parse Statuses</option>
              <option value="SUCCESS">Parsed Successfully</option>
              <option value="PARSE_ERROR">Syntax Parse Errors</option>
            </select>
          </div>

          <div className="flex items-center gap-2 bg-[#0E0E11] border border-[#1F1F25] rounded-lg px-3 py-1.5">
            <Filter className="w-3.5 h-3.5 text-[#6B6B76] shrink-0" />
            <span className="text-[11px] text-[#A1A1AA] whitespace-nowrap">Min CC:</span>
            <input
              type="number"
              min="0"
              max="200"
              value={minComplexityFilter}
              onChange={(e) => {
                setMinComplexityFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full bg-transparent text-xs font-mono text-[#F4F4F5] focus:outline-none"
              aria-label="Minimum Cyclomatic Complexity"
            />
          </div>
        </div>
      </Card>

      {/* Searchable, Sortable, Paginated Dark File DataTable */}
      <Card padding="p-0" className="overflow-hidden">
        <DataTable
          columns={columns}
          data={filteredAndSortedFiles}
          rowKey="id"
          sortField={sortField}
          sortOrder={sortOrder}
          onSortChange={handleSortChange}
          onRowClick={(row) => setSelectedFile(row)}
          selectedRowKey={selectedFile?.id}
          currentPage={currentPage}
          pageSize={pageSize}
          onPageChange={setCurrentPage}
          emptyMessage="No Java files match the current search and filter criteria."
        />
      </Card>

      {/* File Analysis Detail Drawer (Section 2.6 & 3D) */}
      <Drawer
        open={Boolean(selectedFile)}
        onClose={() => setSelectedFile(null)}
        title={selectedFile?.file_name}
        subtitle={
          selectedFile
            ? `${selectedFile.file_path} · Package: ${selectedFile.package_name || '(default)'}`
            : ''
        }
        headerBadge={
          selectedFile ? (
            <StatusChip status={selectedFile.risk_category || 'LOW'} size="xs" />
          ) : null
        }
      >
        {selectedFile && (
          <>
            {selectedFile.parse_status !== 'SUCCESS' ? (
              <div className="p-4 rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/35 text-xs text-[#EF4444] space-y-1.5">
                <div className="font-semibold flex items-center gap-1.5 text-[#F4F4F5]">
                  <XCircle className="w-4 h-4 text-[#EF4444]" />
                  <span>AST Syntax Parse Failure</span>
                </div>
                <p className="font-mono">{selectedFile.parse_error}</p>
                <p className="text-[#A1A1AA]">
                  Physical line counts were extracted, but AST-dependent metrics (Cyclomatic
                  Complexity, Methods, Maintainability Index) are marked unavailable for this file.
                </p>
              </div>
            ) : (
              <>
                {/* Calculated File Metrics */}
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.07em] text-[#A1A1AA] mb-2.5">
                    Calculated File Metrics (AST & Lexical)
                  </h4>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                    {[
                      { label: 'Source LOC', value: selectedFile.loc },
                      { label: 'Total Physical Lines', value: selectedFile.total_lines },
                      { label: 'Comment Ratio', value: `${selectedFile.comment_ratio}%` },
                      { label: 'Methods Count', value: selectedFile.method_count },
                      { label: 'Cyclomatic Complexity', value: selectedFile.cyclomatic_complexity },
                      { label: 'Max Method CC', value: selectedFile.max_method_complexity },
                      { label: 'Max Nesting Depth', value: selectedFile.max_nesting_depth },
                      {
                        label: 'Maintainability Index',
                        value:
                          selectedFile.maintainability_index !== null
                            ? `${selectedFile.maintainability_index}/100`
                            : 'N/A',
                      },
                      {
                        label: 'Halstead Volume',
                        value: selectedFile.halstead_volume ?? 'N/A',
                      },
                      { label: 'Coupling Fan-Out', value: selectedFile.fan_out },
                      { label: 'Imports Count', value: selectedFile.import_count },
                      { label: 'Max Method Params', value: selectedFile.max_parameters },
                    ].map((m) => (
                      <div
                        key={m.label}
                        className="p-2.5 rounded-lg bg-[#0E0E11] border border-[#1F1F25]"
                      >
                        <div className="text-[10px] text-[#6B6B76]">{m.label}</div>
                        <div className="text-sm font-semibold font-mono text-[#F4F4F5] mt-0.5 tabular-nums">
                          {m.value}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Class-level defect predictions for the Ant 1.7 model */}
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.07em] text-[#A1A1AA] mb-2.5">
                    Java Class-Level Metrics &amp; ML Risk ({selectedFile.class_metrics?.length || 0} classes)
                  </h4>
                  {selectedFile.class_metrics?.length > 0 ? (
                    <>
                      <div className="border border-[#1F1F25] rounded-xl overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead className="bg-[#0E0E11] text-[#A1A1AA] text-[10px] uppercase">
                            <tr>
                              <th className="px-3 py-2">Class</th>
                              <th className="px-3 py-2 text-right">LOC</th>
                              <th className="px-3 py-2 text-right">WMC proxy</th>
                              <th className="px-3 py-2 text-right">ML risk score</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-[#1F1F25]">
                            {selectedFile.class_metrics.map((cls, idx) => {
                              const pred = selectedFile.class_predictions?.find(
                                (item) => item.class_name === cls.class_name
                              );
                              return (
                                <tr key={idx}>
                                  <td className="px-3 py-2 font-medium text-[#F4F4F5]">{cls.class_name}</td>
                                  <td className="px-3 py-2 text-right font-mono">{cls.loc}</td>
                                  <td className="px-3 py-2 text-right font-mono">{cls.wmc}</td>
                                  <td className="px-3 py-2 text-right font-mono">
                                    {pred?.defect_probability != null
                                      ? `${(pred.defect_probability * 100).toFixed(1)}%`
                                      : 'Not available'}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      <p className="text-[10px] leading-relaxed mt-2 text-[#A1A1AA]">
                        Class scores use Java class LOC and a WMC approximation. File risk is
                        based on the highest class score, not a calibrated probability.
                        Cross-project validation is still required.
                      </p>
                    </>
                  ) : (
                    <p className="text-xs text-[#6B6B76]">
                      No named Java classes extracted. ML defect prediction may fall back to heuristic mode.
                    </p>
                  )}
                </div>

                {/* Unavailable Metrics (Clearly Separated) */}
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.07em] text-[#6B6B76] mb-2">
                    Unavailable Metrics (Not Extracted from Static ZIP Snapshot)
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {[
                      {
                        label: 'Dynamic Test Coverage',
                        reason: 'Requires JVM runtime test execution (disabled for security)',
                      },
                      {
                        label: 'Git Code Churn / Ownership',
                        reason: 'Requires .git commit log history',
                      },
                      {
                        label: 'Ground-Truth Bug Count',
                        reason: 'Requires external issue-tracker linkage',
                      },
                    ].map((u) => (
                      <div
                        key={u.label}
                        className="p-2.5 rounded-lg bg-[#0E0E11]/70 border border-[#1F1F25] text-xs"
                      >
                        <div className="flex items-center justify-between gap-1">
                          <span className="font-medium text-[#A1A1AA]">{u.label}</span>
                          <span className="font-mono text-[10px] text-[#6B6B76]">Not available</span>
                        </div>
                        <p className="text-[10px] text-[#6B6B76] mt-1 leading-relaxed">{u.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Detected Code Smells */}
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.07em] text-[#A1A1AA] mb-2.5">
                    Why Flagged — Identified Code Quality Concerns & Smells (
                    {selectedFile.code_smells?.length || 0})
                  </h4>
                  {selectedFile.code_smells?.length > 0 ? (
                    <div className="space-y-2">
                      {selectedFile.code_smells.map((smell, i) => (
                        <div
                          key={i}
                          className="p-3 rounded-lg bg-[#0E0E11] border border-[#1F1F25] flex items-start justify-between gap-3"
                        >
                          <div className="flex items-start gap-2">
                            <AlertTriangle
                              className={`w-4 h-4 shrink-0 mt-0.5 ${
                                smell.severity === 'HIGH' ? 'text-[#EF4444]' : 'text-[#EAB308]'
                              }`}
                            />
                            <div>
                              <div className="text-xs font-semibold text-[#F4F4F5]">
                                {smell.label}
                              </div>
                              <div className="text-xs text-[#A1A1AA] mt-0.5">{smell.message}</div>
                            </div>
                          </div>
                          <StatusChip status={smell.severity} size="xs" />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-3 rounded-lg bg-[#22C55E]/10 border border-[#22C55E]/30 text-xs text-[#22C55E] flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 shrink-0" />
                      <span>
                        No static code smells exceeded configured thresholds in this file.
                      </span>
                    </div>
                  )}
                </div>

                {/* Per-Method AST Breakdown */}
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.07em] text-[#A1A1AA] mb-2.5">
                    Per-Method AST Breakdown ({selectedFile.methods_detail?.length || 0} methods)
                  </h4>
                  {selectedFile.methods_detail?.length > 0 ? (
                    <div className="border border-[#1F1F25] rounded-xl overflow-hidden">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead className="bg-[#0E0E11] text-[10px] font-semibold uppercase text-[#A1A1AA] border-b border-[#1F1F25]">
                          <tr>
                            <th className="py-2 px-3">Method</th>
                            <th className="py-2 px-2 text-right">Line</th>
                            <th className="py-2 px-2 text-right">LOC</th>
                            <th className="py-2 px-2 text-right">Params</th>
                            <th className="py-2 px-2 text-right">Nesting</th>
                            <th className="py-2 px-3 text-right">CC</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#1F1F25] font-mono text-[11px]">
                          {selectedFile.methods_detail.map((m, idx) => (
                            <tr key={idx} className="hover:bg-[#16161A]">
                              <td className="py-2 px-3 text-[#F4F4F5] font-medium">{m.name}()</td>
                              <td className="py-2 px-2 text-right text-[#6B6B76]">L{m.line}</td>
                              <td className="py-2 px-2 text-right text-[#A1A1AA]">
                                {m.estimated_loc ?? m.loc}
                              </td>
                              <td className="py-2 px-2 text-right text-[#A1A1AA]">
                                {m.parameters}
                              </td>
                              <td className="py-2 px-2 text-right text-[#A1A1AA]">
                                {m.max_nesting_depth ?? m.max_nesting}
                              </td>
                              <td
                                className={`py-2 px-3 text-right font-semibold ${
                                  (m.cyclomatic_complexity ?? m.complexity) >= 10
                                    ? 'text-[#EF4444]'
                                    : (m.cyclomatic_complexity ?? m.complexity) >= 6
                                    ? 'text-[#F97316]'
                                    : 'text-[#22C55E]'
                                }`}
                              >
                                {m.cyclomatic_complexity ?? m.complexity}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="text-xs text-[#6B6B76] italic">
                      No executable methods declared (e.g., interface or constant declaration).
                    </div>
                  )}
                </div>
              </>
            )}
          </>
        )}
      </Drawer>
    </div>
  );
}
