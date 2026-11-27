import test from 'node:test';
import assert from 'node:assert/strict';
import { gmailConnectionStatus } from '../gmail-connection-status.mjs';
test('Gmail status avoids network when not configured',async()=>{
 assert.deepEqual(await gmailConnectionStatus({env:{},fetchImpl:()=>{throw Error('unexpected');}}),{configured:false,verified:false,status:'not_configured'});
});
test('Gmail profile check never discloses identity',async()=>{
 const urls=[];
 const result=await gmailConnectionStatus({env:{GMAIL_CLIENT_ID:'test',GMAIL_CLIENT_SECRET:'test',GMAIL_REFRESH_TOKEN:'test'},fetchImpl:async(url)=>{urls.push(url);return {ok:true,json:async()=>({access_token:'test',emailAddress:'private@example.com'})};}});
 assert.deepEqual(result,{configured:true,verified:true,status:'connected'});
 assert.deepEqual(urls,['https://oauth2.googleapis.com/token','https://gmail.googleapis.com/gmail/v1/users/me/profile']);
});
