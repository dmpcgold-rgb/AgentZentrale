import { createAutomationHistory } from './automation-history.mjs';
import { ApiError } from './lib.mjs';
export function createAutomationRouter({ now=Date.now, status, readiness, reviewStatus, buildStatus, qualityStatus, gmailStatus, historyFile }) {
  const handlers=new Map(Object.entries({'system-status':status,'westbahn-readiness':readiness,'westbahn-review-status':reviewStatus,'github-build-status':buildStatus,'quality-status':qualityStatus,'gmail-connection-status':gmailStatus}).filter(([,fn])=>typeof fn==='function'));
  const jobs=new Map();
  const history=createAutomationHistory(historyFile);
  function record(job,id,status){history.record({id,type:job.type,status,at:new Date(now()).toISOString()});}
  return {
    history:()=>history.list(),
    persistent:()=>history.persistent(),
    types:()=>Array.from(handlers.keys()),
    async dispatch(body) {
      if(!body || typeof body!=='object' || Array.isArray(body) || Object.keys(body).some(k=>!['type','id'].includes(k)) || typeof body.id!=='string' || !/^[a-zA-Z0-9_-]{8,80}$/.test(body.id) || !handlers.has(body.type)) throw new ApiError(400,'Ungültiger Automatisierungsauftrag.');
      const time=now();
      for(const [id,job] of jobs) if(job.finished && time-job.time>=600000) jobs.delete(id);
      const old=jobs.get(body.id);
      if(old){if(old.type!==body.type) throw new ApiError(409,'Auftrags-ID bereits für anderen Typ verwendet.');return old.promise;}
      if(jobs.size>=200 || [...jobs.values()].filter(j=>!j.finished).length>=4) throw new ApiError(429,'Zu viele Automatisierungsaufträge.');
      const job={type:body.type,time,finished:false};
      job.promise=Promise.resolve().then(()=>handlers.get(body.type)()).then(result=>({id:body.id,type:body.type,status:'completed',completedAt:new Date(now()).toISOString(),readOnly:true,result})).then(result=>{record(job,body.id,'completed');return result;},error=>{record(job,body.id,'failed');throw error;}).finally(()=>{job.finished=true;job.time=now();});
      jobs.set(body.id,job);
      return job.promise;
    }
  };
}
