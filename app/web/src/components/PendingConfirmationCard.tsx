import { useState } from "react";

import { confirmRunStep, declineRunStep } from "../api";
import type { PendingDecision } from "../types";


const AUTHORITY_LABEL: Record<PendingDecision["authority"], string> = {
  L1: "L1 · 只读",
  L2: "L2 · 可逆",
  L3: "L3 · 不可逆",
};


export type PendingConfirmationCardProps = {
  decision: PendingDecision;
  onResolved: (decision: PendingDecision) => void;
};


function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}


export function PendingConfirmationCard(props: PendingConfirmationCardProps) {
  const { decision, onResolved } = props;
  const [busy, setBusy] = useState<"confirm" | "decline" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [declineReason, setDeclineReason] = useState<string>("");
  const [confirmNote, setConfirmNote] = useState<string>("");
  const [showReason, setShowReason] = useState<boolean>(false);

  const handleConfirm = async () => {
    setBusy("confirm");
    setError(null);
    try {
      const updated = await confirmRunStep(decision.run_id, decision.step_id, {
        actor: "user",
        note: confirmNote.trim() || undefined,
      });
      onResolved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const handleDecline = async () => {
    setBusy("decline");
    setError(null);
    try {
      const updated = await declineRunStep(decision.run_id, decision.step_id, {
        actor: "user",
        reason: declineReason.trim() || undefined,
      });
      onResolved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const authority = AUTHORITY_LABEL[decision.authority] ?? decision.authority;
  const isL3 = decision.authority === "L3";

  return (
    <div className={`pending-confirmation-card pending-${decision.authority.toLowerCase()}`}>
      <header className="pending-confirmation-header">
        <span className={`pending-authority-tag authority-${decision.authority.toLowerCase()}`}>
          {authority}
        </span>
        <span className="pending-agent">agent: {decision.agent_id || "未知"}</span>
      </header>
      <p className="pending-task" title={decision.task}>
        {decision.task || "(该步骤未提供描述)"}
      </p>
      <dl className="pending-meta">
        <div>
          <dt>Run</dt>
          <dd>{decision.run_id}</dd>
        </div>
        <div>
          <dt>Step</dt>
          <dd>{decision.step_id}</dd>
        </div>
        <div>
          <dt>制品</dt>
          <dd>{decision.artifact_count}</dd>
        </div>
        <div>
          <dt>创建时间</dt>
          <dd>{formatTimestamp(decision.created_at)}</dd>
        </div>
      </dl>
      {isL3 && (
        <p className="pending-warning">
          L3 步骤在执行后只产出 SOP,不会被 harness 自动落库 — 需要人工确认才能继续。
        </p>
      )}
      <div className="pending-actions">
        <button
          type="button"
          className="pending-btn confirm"
          disabled={busy !== null}
          onClick={handleConfirm}
        >
          {busy === "confirm" ? "确认中…" : "确认"}
        </button>
        <button
          type="button"
          className="pending-btn decline"
          disabled={busy !== null}
          onClick={() => setShowReason((prev) => !prev)}
        >
          {showReason ? "收起理由" : "拒绝"}
        </button>
      </div>
      {showReason && (
        <div className="pending-decline-form">
          <textarea
            placeholder="(可选) 拒绝理由,有助于 audit trail"
            value={declineReason}
            onChange={(event) => setDeclineReason(event.target.value)}
            disabled={busy !== null}
            rows={2}
          />
          <button
            type="button"
            className="pending-btn decline"
            disabled={busy !== null || declineReason.trim().length === 0}
            onClick={handleDecline}
          >
            {busy === "decline" ? "拒绝中…" : "提交拒绝"}
          </button>
        </div>
      )}
      {!showReason && (
        <div className="pending-note-form">
          <input
            type="text"
            placeholder="(可选) 确认备注"
            value={confirmNote}
            onChange={(event) => setConfirmNote(event.target.value)}
            disabled={busy !== null}
          />
        </div>
      )}
      {error && <p className="pending-error">⚠ {error}</p>}
    </div>
  );
}
