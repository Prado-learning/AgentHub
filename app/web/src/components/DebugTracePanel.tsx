import { useEffect, useMemo, useState } from "react";

import { getDebugTrace } from "../api";
import type { DebugStage } from "../types";


export type DebugTracePanelProps = {
  runId: string;
  onClose: () => void;
};


function formatTime(iso: string | null | undefined): string {
  if (!iso) {
    return "";
  }
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}


function summarise(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string") {
    return value.length > 80 ? `${value.slice(0, 77)}…` : value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}


function StageRow({ stage }: { stage: DebugStage }) {
  const [open, setOpen] = useState<boolean>(false);
  const inputs = stage.inputs || {};
  const outputs = stage.outputs || {};
  const raw = stage.raw_api_data || {};
  return (
    <li className={`debug-stage ${stage.error ? "error" : ""} ${stage.final ? "final" : ""}`}>
      <button
        type="button"
        className="debug-stage-summary"
        onClick={() => setOpen((current) => !current)}
      >
        <span className="debug-stage-name">{stage.stage_name || stage.stage_id}</span>
        <span className="debug-stage-cost">{stage.cost_ms} ms</span>
        <span className="debug-stage-time">{formatTime(stage.started_at)}</span>
        {stage.branch_hit ? (
          <span className="debug-stage-branch">branch: {stage.branch_hit}</span>
        ) : null}
        {stage.final ? <span className="debug-stage-flag final">final</span> : null}
        {stage.error ? <span className="debug-stage-flag error">error</span> : null}
        <span className="debug-stage-toggle">{open ? "▾" : "▸"}</span>
      </button>
      {open ? (
        <div className="debug-stage-body">
          {Object.keys(inputs).length > 0 ? (
            <div className="debug-stage-block">
              <strong>输入</strong>
              <pre>{summarise(inputs)}</pre>
            </div>
          ) : null}
          {Object.keys(raw).length > 0 ? (
            <div className="debug-stage-block">
              <strong>原始 API 数据</strong>
              <pre>{summarise(raw)}</pre>
            </div>
          ) : null}
          {Object.keys(outputs).length > 0 ? (
            <div className="debug-stage-block">
              <strong>输出</strong>
              <pre>{summarise(outputs)}</pre>
            </div>
          ) : null}
          {stage.error ? (
            <div className="debug-stage-block error">
              <strong>错误</strong>
              <pre>{stage.error}</pre>
            </div>
          ) : null}
          {!Object.keys(inputs).length && !Object.keys(raw).length
            && !Object.keys(outputs).length && !stage.error ? (
            <div className="debug-stage-block empty">该阶段没有记录额外数据。</div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}


export function DebugTracePanel(props: DebugTracePanelProps) {
  const { runId, onClose } = props;
  const [stages, setStages] = useState<DebugStage[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setStages([]);
    getDebugTrace(runId)
      .then((items) => {
        if (cancelled) {
          return;
        }
        setStages(items);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const totalCost = useMemo(
    () => stages.reduce((sum, stage) => sum + (stage.cost_ms || 0), 0),
    [stages],
  );
  const finalIndex = useMemo(
    () => stages.findIndex((stage) => stage.final),
    [stages],
  );
  const errorCount = useMemo(
    () => stages.filter((stage) => stage.error).length,
    [stages],
  );

  return (
    <div className="debug-trace-overlay" role="dialog" aria-modal="true">
      <div className="debug-trace-panel">
        <header className="debug-trace-header">
          <div>
            <strong>Run Trace</strong>
            <small>{runId}</small>
          </div>
          <button type="button" onClick={onClose}>关闭</button>
        </header>
        {loading ? <p className="debug-trace-loading">加载中…</p> : null}
        {error ? <p className="debug-trace-error">⚠ {error}</p> : null}
        {!loading && !error ? (
          <>
            <section className="debug-trace-summary">
              <span>阶段数 {stages.length}</span>
              <span>累计耗时 {totalCost} ms</span>
              {finalIndex >= 0 ? <span>终态: 阶段 {finalIndex + 1}</span> : null}
              {errorCount > 0 ? <span className="error">错误 {errorCount}</span> : null}
            </section>
            {stages.length === 0 ? (
              <p className="debug-trace-empty">未找到该 run 的 trace。可能 harness 未开启 AGENT_DEBUG,或者 run id 已被清理。</p>
            ) : (
              <ol className="debug-trace-list">
                {stages.map((stage) => (
                  <StageRow key={stage.stage_id} stage={stage} />
                ))}
              </ol>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
