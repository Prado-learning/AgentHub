import {useEffect,useState} from "react";
export function RuntimeModeBadge(){
  const [mode,setMode]=useState("");
  useEffect(()=>{fetch("/api/runtime-info").then(r=>{if(!r.ok)throw new Error("Unavailable");return r.json();}).then(data=>setMode(data.mode)).catch(()=>setMode("unknown"));},[]);
  return <span className="status-chip">{mode==="demo"?"演示模式 · 样例输出":mode==="configured"?"模型模式": "连接中"}</span>;
}
