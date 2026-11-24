import {useEffect,useRef} from "react";
import type {StructuredDiff} from "../types";
import {DiffViewer} from "./DiffViewer";
export function DiffReviewDialog({diff,onClose}:{diff:StructuredDiff;onClose:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{const previous=document.activeElement as HTMLElement|null;dialog.current?.showModal();return()=>{previous?.focus();};},[]);
  return <dialog ref={dialog} className="preview-modal" aria-label="审阅并应用补丁" onCancel={e=>{e.preventDefault();onClose();}} style={{margin:0,border:0,width:"100vw",height:"100vh",maxWidth:"none",maxHeight:"none"}}>
    <div className="editor-card"><button autoFocus type="button" onClick={onClose}>关闭补丁审阅</button><DiffViewer key={diff.review_token} diff={diff}/></div>
  </dialog>;
}
