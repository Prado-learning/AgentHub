import {useEffect, useState} from "react";
import {listConversationRuns,postJSON} from "../api";
export function ActiveRuns({conversationId}:{conversationId:string}) {
  const [runs,setRuns]=useState<Array<{run_id:string;status:string}>>([]);
  const [error,setError]=useState("");
  useEffect(()=>{
    let disposed=false;
    let timer:ReturnType<typeof setTimeout>;
    let previous="";
    const refresh=async()=>{
      try {
        const all=await listConversationRuns(conversationId);
        const next=all.filter(r=>["queued","running","cancelling","waiting_approval"].includes(r.status));
        const signature=JSON.stringify(all);
        if(!disposed){
          setRuns(next); setError("");
          if(previous && previous!==signature) window.dispatchEvent(new Event("agenthub:data-updated"));
          previous=signature;
        }
      }catch(err){if(!disposed)setError(err instanceof Error?err.message:String(err));}
      finally{if(!disposed)timer=setTimeout(refresh,1000);}
    };
    if(conversationId) void refresh();
    return()=>{disposed=true;clearTimeout(timer);};
  },[conversationId]);
  return <div aria-live="polite">{runs.map(run=><div className="active-run" key={run.run_id}>
    <span>{run.run_id} · {run.status==="waiting_approval"?"等待审批":run.status==="cancelling"?"正在停止": "正在执行"}</span>
    <button type="button" disabled={run.status==="cancelling"} onClick={async()=>{try{await postJSON(`/runs/${run.run_id}/cancel`,{});window.dispatchEvent(new Event("agenthub:data-updated"));}catch(err){setError(String(err));}}}>取消运行</button>
  </div>)}{error&&<p role="alert">{error}</p>}</div>;
}
