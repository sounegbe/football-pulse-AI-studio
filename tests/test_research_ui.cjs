const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.attrs={};this.handlers={};this.value='';this._text='';}
 set textContent(value){this._text=value;this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 append(...items){for(const item of items){if(item.parent)item.parent.children=item.parent.children.filter(c=>c!==item);item.parent=this;this.children.push(item);}}
 replaceChildren(...items){this.children=[];this.append(...items);}
 setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,fn){this.handlers[k]=fn;}
 reportValidity(){return true;}reset(){this.querySelectorAll('input,textarea,select').forEach(x=>x.value='');}
 all(){return this.children.flatMap(c=>[c,...c.all()]);}
 querySelectorAll(selector){return this.all().filter(c=>selector.split(',').some(t=>t.trim()==='button'?c.tagName==='button':t.trim()===c.tagName));}
 querySelector(selector){return this.all().find(c=>selector==='button[type="submit"]'&&c.tagName==='button'&&c.type==='submit');}
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function harness(request){
 const root=new Element(),document={createElement:tag=>new Element(tag)},sandbox={window:{},document};let live=true;
 vm.runInNewContext(fs.readFileSync('app/static/js/research-ui.js','utf8'),sandbox);
 return {root,start:()=>sandbox.window.PulseResearch.render({root,request,project:{id:'p'},active:()=>live}),stop:()=>{live=false;},field:label=>root.all().find(x=>x.tagName==='label'&&x._text===label)?.children[0],button:text=>root.all().find(x=>x.tagName==='button'&&x._text===text),submit:async button=>{button.parent.handlers.submit({preventDefault(){}});await flush();await flush();},click:async button=>{button.handlers.click();await flush();await flush();}};
}
function empty(url){if(url.endsWith('/readiness'))return {verified_claim_ids:[]};return {items:[]};}

test('research source failure preserves literal form input and suppresses duplicate submits',async()=>{
 let reject,posts=0;
 const h=harness(async(url,method)=>{if(method==='POST'){posts++;return new Promise((_,r)=>{reject=r;});}return empty(url);});
 await h.start();h.field('Exact source text').value='<img> literal evidence';
 const submit=h.button('Save source');await h.submit(submit);await h.submit(submit);assert.equal(posts,1);
 reject(Error('storage unavailable'));await flush();assert.equal(h.field('Exact source text').value,'<img> literal evidence');
 assert.match(h.root.textContent,/inputs are preserved/);
 h.stop();await h.submit(submit);assert.equal(posts,1);
});

test('claim review sends current versions and evidence withdrawal uses the owned evidence identity',async()=>{
 const posts=[];
 const claim={id:'c',statement:'Synthetic claim <img>',status:'pending',version:7,verification_blockers:[],reviews:[],evidence:[{evidence_id:'e-owned',quote:'Exact quotation',relation:'supports',evidence_status:'active',source_status:'active'}]};
 const h=harness(async(url,method,body)=>{
  if(method==='POST'){posts.push({url,body});claim.version++;return {};}
  if(url.endsWith('/claims/c'))return {...claim};
  if(url.includes('/claims?'))return {items:[claim]};
  if(url.includes('/sources?'))return {items:[{id:'s',title:'Source',status:'active'}]};
  return empty(url);
 });
 await h.start();await h.click(h.button('Synthetic claim <img> · pending'));
 h.field('Source').value='s';h.field('Exact quotation from the saved source').value='Exact quotation';h.field('Relation').value='supports';
 await h.submit(h.button('Attach evidence'));assert.equal(posts[0].body.expected_claim_version,7);assert.equal(posts[0].body.quote,'Exact quotation');
 h.field('Decision').value='verified';h.field('Explain your review decision').value='Human reviewed the dated exact evidence.';
 await h.submit(h.button('Record review'));assert.equal(posts[1].body.expected_version,8);assert.equal(posts[1].body.decision,'verified');
 h.field('Reason').value='Withdrawing this synthetic evidence.';await h.submit(h.button('Withdraw evidence'));
 assert.match(posts[2].url,/claims\/c\/evidence\/e-owned\/withdraw$/);assert.equal(posts[2].body.expected_claim_version,9);
 assert.match(h.root.textContent,/Synthetic claim <img>/);
});
