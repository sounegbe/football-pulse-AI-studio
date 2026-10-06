/* M6 controller: owned durable jobs; polling never submits another generation. */
(() => {
    'use strict';
    window.PulseGeneration={install({request,context,receive}) {
        const $=id=>document.getElementById(id);
        let projectId=null,sequence=0,current=null,available=false,pending=false,timer=null,preview=null,selection=null,submission=null;
        let historyOffset=0,historyMore=false,toneSubmission=null;const historyIds=new Set();
        function newKey(){return [...crypto.getRandomValues(new Uint8Array(16))].map(value=>value.toString(16).padStart(2,'0')).join('');}
        function text(id,value){$(id).textContent=value;}
        function status(value){text('generation-status',value);}
        function buttons(){
            $('generation-start').disabled=pending||!available||!projectId||context().busy||['queued','running'].includes(current?.status);
            $('generation-refresh').disabled=pending||!projectId;
            $('generation-more').disabled=pending||!projectId||!historyMore;
            $('generation-cancel').disabled=pending||!current||!['queued','running'].includes(current.status);
            $('generation-retry').disabled=pending||!available||!current||!['failed','cancelled'].includes(current.status);
            $('generation-recheck').disabled=pending||!current;
            $('generation-use').disabled=pending||!preview||context().busy;
            const toneButton=$('result-tone-open');
            if(toneButton)toneButton.disabled=pending||!available||!preview||current?.status!=='succeeded'||context().busy;
        }
        function contextChanged(){
            const next=context().project?.id??null;
            if(next!==projectId){
                projectId=next;historyOffset=0;historyMore=false;historyIds.clear();sequence++;clearTimeout(timer);current=null;preview=null;selection=null;submission=null;toneSubmission=null;available=false;
                $('generation-claims').replaceChildren();$('generation-history').replaceChildren();$('generation-preview').hidden=true;$('generation-preview').textContent='';$('generation-progress').value=0;
                text('generation-timing','Not started');text('generation-usage','');text('generation-provider','Provider not configured');
                if($('generation-use-dialog').open)$('generation-use-dialog').close();
                text('generation-title','Football Pulse generation');
                status(next?'Refresh reviewed claims and jobs to begin.':'Sign in and select a project.');
            }
            buttons();
        }
        async function action(fn){
            if(pending)return;pending=true;buttons();const token=sequence;
            try{await fn(token);}catch(error){if(token===sequence)status(error.message+' No new job is submitted by rechecking.');}
            finally{pending=false;buttons();}
        }
        function base(){return '/api/projects/'+projectId+'/generation';}
        function usage(job){
            const run=job.generation;
            if(run.usage)text('generation-usage',`${run.usage.input_tokens} input / ${run.usage.output_tokens} output tokens. Estimated cost: ${run.cost_usd===null?'unknown':'USD '+run.cost_usd} (${run.cost_basis}).`);
            else text('generation-usage','Usage not reported. Cost: unknown. Billing state: '+run.billing_status+'. Cancellation does not guarantee provider billing stops.');
        }
        async function show(job,token){
            if(token!==sequence)return;
            text('generation-title',({queued:'Generation queued',running:'Creating your Football Pulse content',succeeded:'Generation result ready',failed:'Generation failed',cancelled:'Generation cancelled'})[job.status]);
            current=job;preview=null;$('generation-preview').hidden=true;$('generation-progress').value=job.progress;
            const started=Date.parse(job.generation.started_at),end=Date.parse(job.generation.completed_at||(['failed','cancelled','succeeded'].includes(job.status)?job.updated_at:''));
            text('generation-timing',Number.isFinite(started)?'Elapsed since worker start: '+Math.max(0,((Number.isFinite(end)?end:Date.now())-started)/1000).toFixed(1)+'s':'Worker has not started.');
            status(`${job.status}: ${job.generation.stage}${job.error_code?' — '+job.error_code:''}. Model: ${job.generation.model}.`);usage(job);buttons();clearTimeout(timer);
            if(job.status==='succeeded'){
                const response=await request('/api/projects/'+projectId+'/assets/'+job.result_asset_id+'/download','GET',undefined,'binary');
                const value=await response.text();
                if(token!==sequence||current?.id!==job.id)return;
                preview=value;$('generation-preview').textContent=value;$('generation-preview').hidden=false;buttons();
            }else if(['queued','running'].includes(job.status)){
                timer=setTimeout(()=>action(async t=>show(await request(base()+'/'+job.id),t)),1000);
            }
        }
        $('generation-refresh').addEventListener('click',()=>action(async token=>{
            const id=projectId;
            const configuration=await request('/api/configuration');
            const ready=await request('/api/projects/'+id+'/research/readiness');
            const claims=[];let offset=0;
            while(true){const page=await request('/api/projects/'+id+'/research/claims?limit=100&offset='+offset);claims.push(...page.items);if(page.items.length<100)break;offset+=100;if(offset>=10000)throw Error('Too many claims. Narrow the project before selecting.');}
            const jobs=await request('/api/projects/'+id+'/generation?limit=20');
            if(token!==sequence)return;
            available=configuration.generation_available;
            text('generation-provider',(configuration.generation_test_provider?'QA SIMULATION — ':((configuration.generation_provider==='gemini'?'Gemini':'OpenAI')+' — '))+(configuration.generation_model||'not configured'));
            const choices=$('generation-claims');choices.replaceChildren();
            const verified=new Set(ready.verified_claim_ids);
            for(const claim of claims.filter(c=>verified.has(c.id))){const label=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.value=claim.id;box.dataset.statement=claim.statement;label.append(box,document.createTextNode(' '+claim.statement));choices.append(label);}
            status(!available?'Live generation is disabled or not configured.':verified.size?'Select reviewed claims, then generate.':'No reviewed claims are ready. Complete the research review first.');
            $('generation-history').replaceChildren();historyIds.clear();historyOffset=jobs.items.length;historyMore=jobs.items.length===20;appendHistory(jobs.items);
            if(jobs.items[0])await show(jobs.items[0],token);
        }));
        function appendHistory(items){
            for(const job of items){if(historyIds.has(job.id))continue;historyIds.add(job.id);const button=document.createElement('button');button.type='button';button.className='desktop-action';button.textContent=job.status+' · '+job.id.slice(0,8);button.addEventListener('click',()=>action(async token=>show(await request(base()+'/'+job.id),token)));$('generation-history').append(button);}
        }
        $('generation-more').addEventListener('click',()=>action(async token=>{
            const page=await request(base()+'?limit=20&offset='+historyOffset);if(token!==sequence)return;
            historyOffset+=page.items.length;historyMore=page.items.length===20;appendHistory(page.items);
        }));
        $('generation-start').addEventListener('click',()=>action(async token=>{
            const boxes=[...$('generation-claims').querySelectorAll('input:checked')];
            if(!boxes.length||boxes.length>100)throw Error('Select between one and one hundred reviewed claims.');
            const ctx=context();const payload={claim_ids:boxes.map(box=>box.value),content_type:ctx.content_type,depth:ctx.depth,audio_cues:ctx.audio_cues};
            const fingerprint=JSON.stringify(payload);
            // Keep the key after an ambiguous POST failure; another click safely replays the same submission.
            if(!submission||submission.fingerprint!==fingerprint)submission={fingerprint,key:newKey()};
            selection={...payload,idempotency_key:submission.key};
            const job=await request(base(),'POST',selection);submission=null;await show(job,token);
        }));
        $('generation-cancel').addEventListener('click',()=>action(async token=>{
            const identity=current.id;await request('/api/projects/'+projectId+'/jobs/'+identity+'/cancel','POST');await show(await request(base()+'/'+identity),token);
        }));
        $('generation-recheck').addEventListener('click',()=>action(async token=>show(await request(base()+'/'+current.id),token)));
        let retrySubmission=null;
        $('generation-retry').addEventListener('click',()=>action(async token=>{
            const identity=current.id;if(retrySubmission?.id!==identity)retrySubmission={id:identity,key:newKey()};
            await show(await request(base()+'/'+identity+'/retry','POST',{idempotency_key:retrySubmission.key}),token);
        }));
        $('generation-use').addEventListener('click',()=>{if(preview)$('generation-use-dialog').showModal();});
        $('generation-use-confirm').addEventListener('click',()=>{
            if(!preview||context().project?.id!==projectId||context().busy)return;
            receive({content:preview,payload:current.payload,job_id:current.id,provider:current.generation.provider});$('generation-use-dialog').close();
        });
        async function regenerateTone(tone){
            if(!['neutral','analytical','conversational','energetic'].includes(tone))return;
            if(pending||!available||!preview||current?.status!=='succeeded'||context().busy)return;
            await action(async token=>{
                const identity=current.id;
                const payload={claim_ids:current.payload.claim_ids,content_type:current.payload.content_type,depth:current.payload.depth,audio_cues:current.payload.audio_cues,tone};
                const fingerprint=JSON.stringify([identity,payload]);
                if(toneSubmission?.fingerprint!==fingerprint)toneSubmission={fingerprint,key:newKey()};
                const job=await request(base(),'POST',{...payload,idempotency_key:toneSubmission.key});
                toneSubmission=null;await show(job,token);
            });
        }
        contextChanged();return {contextChanged,regenerateTone};
    }};
})();
