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
        fingerprint: decision.fingerprint,
        note: confirmNote.trim() || undefined,
      });
      onResolved(updated);
      window.dispatchEvent(new Event("agenthub:data-updated"));
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
        fingerprint: decision.fingerprint,
        reason: declineReason.trim() || undefined,
      });
      onResolved(updated);
      window.dispatchEvent(new Event("agenthub:data-updated"));
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
      <p>工具：{decision.tools?.join(", ") || "CLI Agent"}</p>
      <p>工作区：{decision.workspace_dir}</p>
      {decision.sandbox && (
        <p className="pending-sandbox" title={decision.sandbox.note}>
          沙箱边界：网络 {decision.sandbox.network} ·{" "}
          {decision.sandbox.may_write_files ? "可写文件" : "只读"} ·{" "}
          {decision.sandbox.may_start_processes ? "可起进程" : "不可起进程"}
        </p>
      )}
      <pre>{JSON.stringify(decision.arguments, null, 2)}</pre>
      {isL3 && (
        <p className="pending-warning">
          此步骤尚未执行。确认后 Harness 将执行下列动作并继续运行。
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
            aria-label="拒绝理由（可选）"
            placeholder="(可选) 拒绝理由,有助于 audit trail"
            value={declineReason}
            onChange={(event) => setDeclineReason(event.target.value)}
            disabled={busy !== null}
            rows={2}
          />
          <button
            type="button"
            className="pending-btn decline"
            disabled={busy !== null}
            onClick={handleDecline}
          >
            {busy === "decline" ? "拒绝中…" : "提交拒绝"}
          </button>
        </div>
      )}
      {!showReason && (
        <div className="pending-note-form">
          <input
            aria-label="确认备注（可选）"
            type="text"
            placeholder="(可选) 确认备注"
            value={confirmNote}
            onChange={(event) => setConfirmNote(event.target.value)}
            disabled={busy !== null}
          />
        </div>
      )}
      {error && <p role="alert" className="pending-error">⚠ {error}</p>}
    </div>
  );
}
