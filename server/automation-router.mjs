import { ApiError } from './lib.mjs';

// Fixed, side-effect-free task dispatch. No arbitrary URLs, prompts or shell commands.
export function createAutomationRouter({ now=Date.now, status, readiness, reviewStatus }) {
  const handlers = new Map([
    ['system-status',status],
    ['westbahn-readiness',readiness],
    ['westbahn-review-status',reviewStatus]
  ]);
  const jobs=new Map();
  return {
    types:()=>Array.from(handlers.keys()),
    dispatch(body) {
      if (!body || typeof body !== 'object' || Array.isArray(body) ||
          Object.keys(body).some(k=>!['type','id'].includes(k)) ||
          typeof body.id !== 'string' || !/^[a-zA-Z0-9_-]{8,80}$/.test(body.id) ||
          !handlers.has(body.type)) throw new ApiError(400,'Ungültiger Automatisierungsauftrag.');
      const time=now();
      for(const [id,job] of jobs) if(time-job.time>=600000) jobs.delete(id);
      const old=jobs.get(body.id);
      if(old) {
        if(old.type!==body.type) throw new ApiError(409,'Auftrags-ID bereits für anderen Typ verwendet.');
        return old.result;
      }
      if(jobs.size>=200) throw new ApiError(429,'Zu viele Automatisierungsaufträge.');
      const result={id:body.id,type:body.type,status:'completed',completedAt:new Date(time).toISOString(),readOnly:true,result:handlers.get(body.type)()};
      jobs.set(body.id,{type:body.type,time,result});
      return result;
    }
  };
}
