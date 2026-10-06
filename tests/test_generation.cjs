const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
class Element {
 constructor(){this.textContent='';this.children=[];this.handlers={};this.disabled=false;this.hidden=false;this.open=false;this.boxes=[];}
 addEventListener(name,fn){this.handlers[name]=fn;}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 querySelectorAll(){return this.boxes;}
 showModal(){this.open=true;}
 close(){this.open=false;}
 async click(){if(!this.disabled)return this.handlers.click?.();}
}
function harness(request){
 const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
 const ctx={project:{id:'project-a'},busy:false,content_type:'youtube_script',depth:2,audio_cues:false};let receipt=null,n=0;
 const sandbox={window:{},document:{getElementById:get,createElement:()=>new Element(),createTextNode:text=>({textContent:text})},crypto:{getRandomValues:array=>{array.fill(++n);return array;}},setTimeout:()=>1,clearTimeout:()=>{}};
 vm.runInNewContext(fs.readFileSync('app/static/js/generation.js','utf8'),sandbox);
 const ui=sandbox.window.PulseGeneration.install({request,context:()=>ctx,receive:value=>{receipt=value;}});
 return {get,ctx,ui,receipt:()=>receipt};
}
const job=(status='queued')=>({id:'job-a',status,progress:status==='succeeded'?100:0,error_code:null,result_asset_id:'asset-a',payload:{content_type:'youtube_script',review_snapshot:[]},generation:{stage:status,model:'fixture',usage:null,cost_usd:null,billing_status:'unknown'}});
async function refresh(h){await h.get('generation-refresh').click();h.get('generation-claims').boxes=[{value:'claim-a',dataset:{statement:'Fixture'}}];}
function standard(url){if(url==='/api/configuration')return {generation_available:true,generation_model:'fixture'};if(url.endsWith('/readiness'))return {verified_claim_ids:[]};if(url.includes('/claims?'))return {items:[]};if(url.includes('generation?'))return {items:[]};}

test('ambiguous submission replays its key, confirmed jobs block duplicate active submission',async()=>{
 let posts=[],fail=true;
 const h=harness(async(url,method,body)=>{if(method==='POST'){posts.push(body);if(fail){fail=false;throw Error('network lost');}return job();}return standard(url);});
 await refresh(h);await h.get('generation-start').click();assert.match(h.get('generation-status').textContent,/network lost/);
 await h.get('generation-start').click();assert.equal(posts.length,2);assert.equal(posts[0].idempotency_key,posts[1].idempotency_key);
 assert.equal(posts[1].depth,2);assert.equal(posts[1].audio_cues,false);assert.equal(h.get('generation-start').disabled,true);
 await h.get('generation-start').click();assert.equal(posts.length,2);
});

test('result stays outside editor until explicit replacement; project switch clears private output',async()=>{
 let state=job('succeeded');
 const h=harness(async(url)=>url.endsWith('/download')?{text:async()=>'<img> literal fixture'}:url.includes('generation?')?{items:[state]}:standard(url));
 await refresh(h);assert.equal(h.receipt(),null);assert.equal(h.get('generation-preview').textContent,'<img> literal fixture');
 await h.get('generation-use').click();assert.equal(h.get('generation-use-dialog').open,true);assert.equal(h.receipt(),null);
 await h.get('generation-use-confirm').click();assert.equal(h.receipt().content,'<img> literal fixture');
 h.ctx.project={id:'project-b'};h.ui.contextChanged();assert.equal(h.get('generation-preview').textContent,'');assert.equal(h.get('generation-use').disabled,true);
});

test('claim selection validation submits nothing and polling errors never create jobs',async()=>{
 let posts=0;
 const h=harness(async(url,method)=>{if(method==='POST')posts++;return standard(url);});
 await h.get('generation-refresh').click();await h.get('generation-start').click();assert.equal(posts,0);assert.match(h.get('generation-status').textContent,/Select between/);
});

test('a recheck failure preserves the job and cannot submit a billable attempt',async()=>{
 let posts=0;
 const h=harness(async(url,method)=>{if(method==='POST')posts++;if(url.endsWith('/job-a'))throw Error('poll unavailable');return url.includes('generation?')?{items:[job()]}:standard(url);});
 await refresh(h);await h.get('generation-recheck').click();assert.match(h.get('generation-status').textContent,/poll unavailable/);assert.equal(posts,0);assert.equal(h.get('generation-start').disabled,true);
});

test('tone regeneration uses reviewed claims, keeps the editor, and replays an ambiguous submission',async()=>{
 const complete=job('succeeded');complete.payload={claim_ids:['claim-a'],content_type:'youtube_script',depth:2,audio_cues:false};
 const posts=[];let fail=true;
 const h=harness(async(url,method,body)=>{
  if(method==='POST'){posts.push(body);if(fail){fail=false;throw Error('ambiguous timeout');}return job();}
  if(url.endsWith('/download'))return {text:async()=>'<img> complete draft'};
  if(url.includes('generation?'))return {items:[complete]};return standard(url);
 });
 await refresh(h);await h.ui.regenerateTone('conversational');assert.equal(h.receipt(),null);
 await h.ui.regenerateTone('conversational');assert.equal(posts.length,2);
 assert.equal(posts[0].idempotency_key,posts[1].idempotency_key);
 assert.equal(posts[1].tone,'conversational');assert.deepEqual(Array.from(posts[1].claim_ids),['claim-a']);
 assert.equal(posts[1].depth,2);assert.equal(posts[1].audio_cues,false);
 await h.ui.regenerateTone('energetic');assert.equal(posts.length,2);
 h.ctx.project={id:'other-project'};h.ui.contextChanged();await h.ui.regenerateTone('analytical');assert.equal(posts.length,2);
});
