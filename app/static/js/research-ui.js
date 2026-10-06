/* Human review workspace. All text is literal; review decisions are explicit writes. */
(() => {
    'use strict';
    window.PulseResearch={async render({root,request,project,active}) {
        const base='/api/projects/'+project.id+'/research';
        let pending=false,currentClaim=null,currentSource=null;
        const add=(parent,tag,text)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;parent.append(el);return el;};
        const status=add(root,'p','Loading sources and claims…');status.setAttribute('role','status');
        const panel=add(root,'div');panel.className='research-workspace';
        function field(form,label,type='text',max=4000){
            const wrapper=add(form,'label',label),input=add(wrapper,type==='textarea'?'textarea':'input');
            if(type!=='textarea')input.type=type;input.required=true;input.maxLength=max;
            form.append(form.querySelector('button[type="submit"]'));return input;
        }
        function choice(form,label,values){const wrapper=add(form,'label',label),select=add(wrapper,'select');for(const [value,title] of values){const o=add(select,'option',title);o.value=value;}form.append(form.querySelector('button[type="submit"]'));return select;}
        function form(parent,title,submit,handler){
            const box=add(parent,'section');add(box,'h3',title);const f=add(box,'form');
            const button=add(f,'button',submit);button.type='submit';button.className='desktop-action';
            f.addEventListener('submit',event=>{event.preventDefault();if(f.reportValidity())action(()=>handler(f));});return f;
        }
        async function action(fn){
            if(pending||!active())return;pending=true;
            panel.querySelectorAll('button').forEach(b=>b.disabled=true);
            try{await fn();if(active())status.textContent='Saved. Review remains a human decision, not a guarantee of truth.';}
            catch(error){if(active())status.textContent=error.message+' Your form inputs are preserved.';}
            finally{pending=false;if(active())panel.querySelectorAll('button').forEach(b=>b.disabled=Boolean(project.archived));}
        }
        async function all(path){const items=[];for(let offset=0;offset<10000;offset+=100){const data=await request(base+path+'?limit=100&offset='+offset);if(!active())return [];items.push(...data.items);if(data.items.length<100)return items;}throw Error('Too many records to display in this workspace.');}
        const sourceForm=form(panel,'1. Save a dated source','Save source',async()=>{
            await request(base+'/sources','POST',{url:url.value.trim(),title:title.value.trim(),publisher:publisher.value.trim(),text:sourceText.value,published_at:published.value.trim()||null});
            await refresh();sourceForm.reset();
        });
        const url=field(sourceForm,'Source HTTPS URL','url',2048),title=field(sourceForm,'Article title','text',200),publisher=field(sourceForm,'Publisher','text',100);
        const published=field(sourceForm,'Publication date/time with timezone (example: 2026-10-05T12:00:00Z)','text',60);published.required=false;
        const sourceText=field(sourceForm,'Exact source text','textarea',100000);sourceText.rows=5;
        add(sourceForm,'p','Only quote material you may use. A publication date is required before its evidence can support a verified decision.');
        const importForm=form(panel,'Or import an allowed public article','Import article',async()=>{await request(base+'/sources/import','POST',{url:importURL.value.trim()});await refresh();importForm.reset();});
        const importURL=field(importForm,'Public HTTPS article URL','url',2048);add(importForm,'p','Only supported publishers can be imported. If retrieval fails, save the source text manually above.');
        const sourceList=add(panel,'section');add(sourceList,'h3','Saved sources');const sources=add(sourceList,'div');const sourceDetail=add(sourceList,'div');
        const claimForm=form(panel,'2. Record a claim','Save claim',async()=>{const result=await request(base+'/claims','POST',{statement:statement.value.trim(),event_at:eventDate.value.trim()||null});await refresh();await showClaim(result.id);claimForm.reset();});
        const statement=field(claimForm,'Claim statement','textarea'),eventDate=field(claimForm,'Event date/time with timezone (optional)','text',60);eventDate.required=false;
        const claimList=add(panel,'section');add(claimList,'h3','Claims and review history');const claims=add(claimList,'div'),claimDetail=add(claimList,'div');
        async function showSource(id){
            const detail=await request(base+'/sources/'+id);if(!active())return;currentSource=detail;sourceDetail.replaceChildren();
            add(sourceDetail,'h4',detail.title);add(sourceDetail,'p',detail.publisher+' · '+(detail.published_at||'Undated')+' · '+detail.status);add(sourceDetail,'pre',detail.text);
            const edit=form(sourceDetail,'Correct source metadata','Save correction',async()=>{
                await request(base+'/sources/'+detail.id+'/metadata','PATCH',{title:correctTitle.value.trim(),publisher:correctPublisher.value.trim(),published_at:correctDate.value.trim()||null,expected_version:detail.version,reason:correctionReason.value.trim()});await refresh();await showSource(detail.id);
            });
            const correctTitle=field(edit,'Title','text',200),correctPublisher=field(edit,'Publisher','text',100),correctDate=field(edit,'Publication date/time','text',60),correctionReason=field(edit,'Reason for correction','textarea',2000);
            correctTitle.value=detail.title;correctPublisher.value=detail.publisher;correctDate.value=detail.published_at||'';correctDate.required=false;correctionReason.minLength=10;
            const change=form(sourceDetail,detail.status==='active'?'Withdraw source':'Restore source',detail.status==='active'?'Withdraw source':'Restore source',async()=>{
                await request(base+'/sources/'+detail.id+'/status','PATCH',{status:detail.status==='active'?'withdrawn':'active',expected_version:detail.version,reason:sourceReason.value.trim()});await refresh();await showSource(detail.id);
            });
            const sourceReason=field(change,'Reason','textarea',2000);sourceReason.minLength=10;
            add(sourceDetail,'p','Corrections and withdrawal invalidate affected reviews and cancel affected active generation.');
            for(const event of detail.history||[])add(sourceDetail,'p','Source audit: '+JSON.stringify(event));
        }
        async function showClaim(id){
            const detail=await request(base+'/claims/'+id);if(!active())return;currentClaim=detail;claimDetail.replaceChildren();
            add(claimDetail,'h4',detail.statement);add(claimDetail,'p','Status: '+detail.status+' · Version '+detail.version);
            add(claimDetail,'p','Review blockers: '+(detail.verification_blockers.join(', ')||'None'));
            const evidenceForm=form(claimDetail,'3. Attach an exact quotation','Attach evidence',async()=>{
                await request(base+'/claims/'+id+'/evidence','POST',{source_id:sourceSelect.value,quote:quote.value,relation:relation.value,expected_claim_version:detail.version});await refresh();await showClaim(id);
            });
            const sourceSelect=choice(evidenceForm,'Source',sourceRecords.map(s=>[s.id,s.title+' ('+s.status+')']));sourceSelect.required=true;
            const quote=field(evidenceForm,'Exact quotation from the saved source','textarea'),relation=choice(evidenceForm,'Relation',[['supports','Supports'],['contradicts','Contradicts'],['context','Context']]);
            for(const evidence of detail.evidence){
                add(claimDetail,'blockquote',evidence.quote);add(claimDetail,'p',evidence.relation+' · '+evidence.evidence_status+' · source '+evidence.source_status);
                if(evidence.evidence_status==='active'){
                    const withdrawal=form(claimDetail,'Withdraw this evidence','Withdraw evidence',async()=>{await request(base+'/claims/'+id+'/evidence/'+evidence.evidence_id+'/withdraw','POST',{expected_claim_version:detail.version,reason:reason.value.trim()});await refresh();await showClaim(id);});
                    const reason=field(withdrawal,'Reason','textarea',2000);reason.minLength=10;
                }
            }
            const reviewForm=form(claimDetail,'4. Record your review decision','Record review',async()=>{
                await request(base+'/claims/'+id+'/reviews','POST',{decision:decision.value,reason:reviewReason.value.trim(),expected_version:detail.version});await refresh();await showClaim(id);
            });
            const decision=choice(reviewForm,'Decision',[['pending','Pending'],['verified','Verified after human review'],['rejected','Rejected'],['disputed','Disputed']]);
            const reviewReason=field(reviewForm,'Explain your review decision','textarea',2000);reviewReason.minLength=10;
            add(reviewForm,'p','Verified requires active, dated supporting evidence and no active contradictory evidence. The server checks these rules.');
            for(const review of detail.reviews)add(claimDetail,'p','Review: '+review.decision+' · '+review.reason);
            const reload=add(claimDetail,'button','Reload review information');reload.type='button';reload.className='desktop-action';reload.addEventListener('click',()=>action(()=>showClaim(id)));
        }
        let sourceRecords=[];
        async function refresh(){
            const [s,c,r]=await Promise.all([all('/sources'),all('/claims'),request(base+'/readiness')]);if(!active())return;
            sourceRecords=s;sources.replaceChildren();claims.replaceChildren();
            for(const record of s){const b=add(sources,'button',record.title+' · '+record.status);b.type='button';b.className='desktop-action';b.addEventListener('click',()=>action(()=>showSource(record.id)));}
            for(const record of c){const b=add(claims,'button',record.statement+' · '+record.status);b.type='button';b.className='desktop-action';b.addEventListener('click',()=>action(()=>showClaim(record.id)));}
            if(!s.length)add(sources,'p','No sources yet.');if(!c.length)add(claims,'p','No claims yet.');
            status.textContent=r.verified_claim_ids.length+' reviewed claims are ready. Return to Create and refresh reviewed claims to generate.';
            if(project.archived)panel.querySelectorAll('button').forEach(b=>b.disabled=true);
        }
        await refresh();
    }};
})();
