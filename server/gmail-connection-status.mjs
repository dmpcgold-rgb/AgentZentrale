// Connectivity only: never return mailbox identity, message bodies or credentials.
export async function gmailConnectionStatus({env=process.env,fetchImpl=fetch}={}){
 const {GMAIL_CLIENT_ID:clientId,GMAIL_CLIENT_SECRET:secret,GMAIL_REFRESH_TOKEN:refresh}=env;
 if(!clientId||!secret||!refresh) return {configured:false,verified:false,status:'not_configured'};
 try {
  const token=await fetchImpl('https://oauth2.googleapis.com/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:clientId,client_secret:secret,refresh_token:refresh,grant_type:'refresh_token'}),signal:AbortSignal.timeout(10000),redirect:'error'});
  if(!token.ok) return {configured:true,verified:false,status:'oauth_failed'};
  const data=await token.json();
  if(typeof data.access_token!=='string'||!data.access_token) return {configured:true,verified:false,status:'oauth_failed'};
  const profile=await fetchImpl('https://gmail.googleapis.com/gmail/v1/users/me/profile',{headers:{Authorization:'Bearer '+data.access_token},signal:AbortSignal.timeout(10000),redirect:'error'});
  return {configured:true,verified:profile.ok,status:profile.ok?'connected':'profile_failed'};
 } catch {return {configured:true,verified:false,status:'unavailable'};}
}
