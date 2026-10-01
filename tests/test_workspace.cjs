const test=require('node:test'), assert=require('node:assert/strict'), vm=require('node:vm'), fs=require('node:fs');
const source=fs.readFileSync('app/static/js/workspace.js','utf8');
function setup(fetch, clipboard=async()=>{}) {
 const element=()=>({textContent:'',disabled:false,value:'',checked:false,dataset:{},attrs:{},listeners:{},setAttribute(k,v){this.attrs[k]=v},addEventListener(k,fn){this.listeners[k]=fn},focus(){this.focused=true}});
 const map={};for(const id of ['intel-input','generated-content','workspace-status','generate-trigger-btn','regenerate-btn','copy-script-btn','clear-result-btn','depth-slider','audio-cues','char-counter','depth-label','clear-btn','push-stage-btn'])map['#'+id]=element();
 const input=map['#intel-input'];input.value='  Football news  ';map['#depth-slider'].value='3';map['#audio-cues'].checked=true;
 const selected=element();selected.value='youtube';const chip=element();chip.dataset.fill='Unverified example — Fixture';const note=element();note.dataset.note='xG Data';const unavailable=element();unavailable.dataset.unavailable='Later milestone';
 let timer;
 vm.runInNewContext(source,{document:{querySelector:s=>s==='input[name=blueprint]:checked'?selected:map[s]||null,querySelectorAll:s=>s==='.quick-chip'?[chip]:s==='[data-note]'?[note]:s==='[data-unavailable]'?[unavailable]:Object.values(map)},fetch,navigator:{clipboard:{writeText:clipboard}},AbortController,TypeError,setTimeout:fn=>{timer=fn;return 1},clearTimeout:()=>{timer=null}});
 return {map,input,selected,chip,note,unavailable,click:id=>map['#'+id].listeners.click(),timeout:()=>timer()};
}
const success=async(_,options)=>{const p=JSON.parse(options.body);return {ok:true,json:async()=>({...p,content:'<img onerror=alert(1)>',mode:'stub'})}};
test('workspace options and all formats reach API and render as text',async()=>{
 let payload;const s=setup(async(url,options)=>{payload=JSON.parse(options.body);return success(url,options)});
 for(const [value,kind] of Object.entries({article:'news_article',youtube:'youtube_script',short:'short_video',social_post:'social_post'})){
 s.selected.value=value;s.map['#depth-slider'].value='2';s.map['#audio-cues'].checked=false;await s.click('generate-trigger-btn');assert.equal(payload.news,'Football news');assert.equal(payload.content_type,kind);assert.equal(payload.depth,2);assert.equal(payload.audio_cues,false);assert.match(s.map['#generated-content'].textContent,/<img/);
 }
});
test('blank, unicode-aware length and invalid depth do not request',async()=>{
 let count=0;const s=setup(()=>{count++});for(const v of [' ', '😀'.repeat(2001)]){s.input.value=v;await s.click('generate-trigger-btn');}s.input.value='text';s.map['#depth-slider'].value='4';await s.click('generate-trigger-btn');assert.equal(count,0);assert.ok(s.input.focused);
});
test('preset, notes and clears retain consistent input and output states',async()=>{
 const s=setup(success);s.chip.listeners.click();assert.match(s.input.value,/Unverified/);s.note.listeners.click();assert.match(s.input.value,/dated source/);await s.click('generate-trigger-btn');await s.click('clear-btn');assert.equal(s.input.value,'');assert.equal(s.map['#copy-script-btn'].disabled,false);await s.click('clear-result-btn');assert.equal(s.map['#copy-script-btn'].disabled,true);assert.equal(s.map['#regenerate-btn'].disabled,true);
});
test('pending disables mutating controls and suppresses duplicate generation',async()=>{
 let resolve,count=0;const s=setup((url,options)=>{count++;return new Promise(r=>resolve=()=>success(url,options).then(r))});const pending=s.click('generate-trigger-btn');assert.ok(s.input.disabled);s.chip.listeners.click();await s.click('generate-trigger-btn');assert.equal(count,1);resolve();await pending;assert.equal(s.input.disabled,false);
});
test('regenerate uses last successful request, failure preserves response',async()=>{
 let payload,fail=false;const s=setup(async(url,options)=>{payload=JSON.parse(options.body);return fail?{ok:false,status:500}:success(url,options)});await s.click('generate-trigger-btn');s.input.value='Edited input';s.selected.value='article';await s.click('regenerate-btn');assert.equal(payload.news,'Football news');assert.equal(payload.content_type,'youtube_script');fail=true;await s.click('generate-trigger-btn');assert.match(s.map['#generated-content'].textContent,/<img/);assert.equal(s.input.value,'Edited input');assert.match(s.map['#workspace-status'].textContent,/could not/);
});
test('clipboard writes exact response and handles rejection without false success',async()=>{
 let copied;const s=setup(success,async value=>{copied=value});await s.click('generate-trigger-btn');await s.click('copy-script-btn');assert.equal(copied,s.map['#generated-content'].textContent);const denied=setup(success,async()=>{throw Error('Denied')});await denied.click('generate-trigger-btn');await denied.click('copy-script-btn');assert.match(denied.map['#workspace-status'].textContent,/failed/);
});
test('malformed, mismatched options, HTTP and network failures restore controls',async()=>{
 for(const fetch of [async()=>({ok:false,status:429}),async()=>({ok:true,json:async()=>{throw Error()}}),async()=>({ok:true,json:async()=>({content:'text',mode:'stub',content_type:'youtube_script',depth:1,audio_cues:true})}),async()=>{throw new TypeError()}]){const s=setup(fetch);await s.click('generate-trigger-btn');assert.equal(s.input.disabled,false);assert.equal(s.input.value,'  Football news  ');assert.ok(s.map['#workspace-status'].textContent);assert.equal(s.map['#copy-script-btn'].disabled,true);}
});
test('timeout aborts; stage and future navigation never claim successful processing',async()=>{
 const s=setup((_,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{const e=Error();e.name='AbortError';reject(e)})));const pending=s.click('generate-trigger-btn');s.timeout();await pending;assert.match(s.map['#workspace-status'].textContent,/timed out/);await s.click('push-stage-btn');assert.match(s.map['#workspace-status'].textContent,/first/);const ready=setup(success);await ready.click('generate-trigger-btn');await ready.click('push-stage-btn');assert.match(ready.map['#workspace-status'].textContent,/cannot advance/);ready.unavailable.listeners.click({preventDefault(){}});assert.equal(ready.map['#workspace-status'].textContent,'Later milestone');
});
