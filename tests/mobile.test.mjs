import test from 'node:test';
import assert from 'node:assert/strict';
import {apiBase,initialConnection,createConnection} from '../mobile/connection.mjs';
test('query cannot redirect remembered token',()=>{
 const x=initialConnection({origin:'https://panel.example',requested:'https://other.example',savedBase:'https://desktop.example',savedToken:'fixture'});
 assert.equal(x.token,'');assert.equal(x.automatic,false);
 assert.equal(initialConnection({origin:'http://localhost:8765',fragment:'fixture'}).automatic,true);
 for(const v of ['file:///tmp','javascript:void(0)','https://user:pass@example.com'])assert.throws(()=>apiBase(v));
});
test('poll fixed pair and disconnect stops requests',async()=>{
 const calls=[];const c=createConnection(async(u,o)=>{calls.push([u.origin,o.headers.Authorization,o.redirect]);return{ok:true,json:async()=>[]};});
 await c.connect('https://desktop.example','fixture');await c.refresh();c.disconnect();await c.refresh();
 assert.deepEqual(calls,[['https://desktop.example','Bearer fixture','error'],['https://desktop.example','Bearer fixture','error']]);
});
test('stale response cannot save credentials',async()=>{
 let finish;const saved=[];const c=createConnection(()=>new Promise(r=>finish=r),(...p)=>saved.push(p));
 const pending=c.connect('https://old.example','fixture');c.disconnect();finish({ok:true,json:async()=>[]});
 assert.equal(await pending,null);assert.deepEqual(saved,[]);
});
