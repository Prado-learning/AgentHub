import {useState} from "react";
import {applyArtifactDiff,postJSON} from "../api";
import type {StructuredDiff, StructuredDiffLine} from "../types";
export function DiffViewer({ diff }: { diff: StructuredDiff }) {
  const [reviewedHunks, setReviewedHunks] = useState<Set<string>>(new Set());

  const [applied, setApplied] = useState(diff.status === "applied");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function applySelected() {
    setBusy(true); setError("");
    try {
      await applyArtifactDiff(diff.artifact_id, diff.review_token, [...reviewedHunks]);
      window.dispatchEvent(new Event("agenthub:data-updated"));
      setApplied(true);
      setNotice("已应用。可回滚本次修改。");
      setReviewedHunks(new Set());
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  async function rollback() {
    setBusy(true); setError("");
    try {
      await postJSON(`/artifacts/${diff.artifact_id}/rollback`,{});
      setApplied(false); setNotice("已回滚。重新打开审阅后可再次应用。");
      window.dispatchEvent(new Event("agenthub:data-updated"));
    } catch(err) {setError(err instanceof Error?err.message:String(err));}
    finally {setBusy(false);}
  }
  function toggleHunkReview(hunkKey: string) {
    setReviewedHunks((current) => {
      const next = new Set(current);
      if (next.has(hunkKey)) {
        next.delete(hunkKey);
      } else {
        next.add(hunkKey);
      }
      return next;
    });
  }

  return (
    <div className="diff-viewer split">
      <p>工作区：{diff.workspace_dir}</p>
      <button type="button" disabled={busy || applied || reviewedHunks.size === 0} onClick={applySelected}>应用已选片段 ({reviewedHunks.size})</button>
      {applied && <button type="button" disabled={busy} onClick={rollback}>回滚本次应用</button>}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
      {diff.files.map((file) => (
        <section key={`${file.old_path}-${file.new_path}`}>
          <header>
            <strong>{file.old_path}</strong>
            <strong>{file.new_path}</strong>
          </header>
          {file.hunks.map((hunk) => {
            const hunkKey = hunk.id;
            const reviewed = reviewedHunks.has(hunkKey);
            return (
            <div className={`diff-hunk ${reviewed ? "reviewed" : ""}`} key={hunk.header}>
              <div className="diff-hunk-header">
                <small>{hunk.header}</small>
                <button type="button" aria-pressed={reviewed} onClick={() => toggleHunkReview(hunkKey)}>
                  {reviewed ? "已选择" : "选择片段"}
                </button>
              </div>
              {splitDiffRows(hunk.lines).map((row, index) => (
                <div className="diff-split-row" key={`${hunk.header}-${index}`}>
                  <div className={`diff-split-cell ${row.old?.type ?? "empty"}`}>
                    <span>{row.old?.old_no ?? ""}</span>
                    <code>{row.old ? `${row.old.type === "remove" ? "-" : " "}${row.old.content}` : ""}</code>
                  </div>
                  <div className={`diff-split-cell ${row.next?.type ?? "empty"}`}>
                    <span>{row.next?.new_no ?? ""}</span>
                    <code>{row.next ? `${row.next.type === "add" ? "+" : " "}${row.next.content}` : ""}</code>
                  </div>
                </div>
              ))}
            </div>
          );
          })}
        </section>
      ))}
    </div>
  );
}

function splitDiffRows(lines: StructuredDiffLine[]): Array<{ old?: StructuredDiffLine; next?: StructuredDiffLine }> {
  const rows: Array<{ old?: StructuredDiffLine; next?: StructuredDiffLine }> = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const nextLine = lines[index + 1];
    if (line.type === "remove" && nextLine?.type === "add") {
      rows.push({ old: line, next: nextLine });
      index += 2;
      continue;
    }
    if (line.type === "remove") {
      rows.push({ old: line });
    } else if (line.type === "add") {
      rows.push({ next: line });
    } else {
      rows.push({ old: line, next: line });
    }
    index += 1;
  }
  return rows;
}

