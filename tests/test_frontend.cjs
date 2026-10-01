const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('app/static/js/app.js', 'utf8');
function setup(fetch) {
    const element = () => ({textContent: '', disabled: false, attrs: {}, listeners: {}, dataset: {}, classList: {add(){},remove(){}}, setAttribute(k,v){this.attrs[k]=v}, addEventListener(k,v){this.listeners[k]=v}, focus(){this.focused=true}});
    const button=element(), input=element(), result=element(); input.value=' News ';
    Object.defineProperty(result, 'innerHTML', {set(){throw new Error('Unsafe HTML rendering')}});
    const types=['news_article','youtube_script','short_video','social_post'].map(kind=>{const e=element();e.dataset.contentType=kind;return e});
    let timer;
    const context={document:{querySelector:s=>s==='.generate-button'?button:s==='#football-news'?input:result,querySelectorAll:()=>types},fetch,AbortController,TypeError,setTimeout:fn=>{timer=fn;return 1},clearTimeout:()=>{timer=null}};
    vm.runInNewContext(source,context);
    return {button,input,result,types,click:()=>button.listeners.click(),timeout:()=>timer()};
}
test('empty and oversized input do not request', async()=>{
    let requests=0;const s=setup(()=>{requests++});
    for(const value of ['  ','x'.repeat(2001)]){s.input.value=value;await s.click();assert.equal(requests,0);assert.equal(s.input.focused,true)}
});
test('all formats submit trimmed news and safely render output',async()=>{
    let payload;const s=setup(async(_,options)=>{payload=JSON.parse(options.body);return {ok:true,json:async()=>({content:'<img onerror=alert(1)>\nText',content_type:payload.content_type,mode:'stub'})}});
    for(const type of s.types){type.listeners.click();await s.click();assert.equal(payload.news,'News');assert.equal(payload.content_type,type.dataset.contentType);assert.match(s.result.textContent,/<img/);assert.equal(s.button.disabled,false);assert.equal(s.result.attrs['aria-busy'],'false')}
});
test('pending requests disable controls and prevent duplicate submission',async()=>{
    let resolve,requests=0;const s=setup(()=>{requests++;return new Promise(r=>resolve=r)});
    const pending=s.click();assert.equal(s.button.disabled,true);assert.ok(s.types.every(t=>t.disabled));await s.click();assert.equal(requests,1);
    resolve({ok:true,json:async()=>({content:'test',content_type:'youtube_script',mode:'stub'})});await pending;assert.equal(s.button.disabled,false);
});
test('HTTP, JSON, malformed payload, network, and timeout failures recover',async()=>{
    const cases=[
      [async()=>({ok:false,status:422}),/rejected/],
      [async()=>({ok:false,status:500}),/server could not/],
      [async()=>({ok:true,json:async()=>{throw Error('bad json')}}),/invalid response/],
      [async()=>({ok:true,json:async()=>({content:12})}),/unexpected response/],
      [async()=>{throw new TypeError('network')},/Could not connect/],
      [async()=>{const e=Error('aborted');e.name='AbortError';throw e},/timed out/],
    ];
    for(const [fetch,message] of cases){const s=setup(fetch);await s.click();assert.match(s.result.textContent,message);assert.equal(s.input.value,' News ');assert.equal(s.button.disabled,false);assert.ok(s.types.every(t=>!t.disabled))}
});
test('timeout aborts the active request',async()=>{
    let signal;const s=setup((_,options)=>{signal=options.signal;return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>{const e=Error();e.name='AbortError';reject(e)}))});
    const pending=s.click();s.timeout();await pending;assert.equal(signal.aborted,true);assert.match(s.result.textContent,/timed out/);
});
