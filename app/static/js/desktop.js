(() => {
    'use strict';
    const $=selector=>document.querySelector(selector), core=window.PulseDesktop;
    const input=$('#intelPrompt'), content=$('#scriptContent'), depth=$('#depthSlider'), cue=$('#cueToggle');
    const depthNames={1:'Casual Supporter',2:'Studio Pundit',3:'Pro Analyst'};
    let account=null, previousUser=null, csrf=null, project=null, version=0, selected='youtube_script', audio=true;
    let mediaUrl=null;
    let generationUI=null;
    let editing=false,undo=[],redo=[],selectedRevision=null;
    let output='', mode='unknown', lastRequest=null, savedFingerprint=null, busy=false, chapter=0, view='create', navSequence=0;
    function message(text) {$('#desktop-status').textContent=text;}
    function draft() {return {news:input.value,content:output,content_type:selected,depth:Number(depth.value),audio_cues:audio,content_mode:mode};}
    function dirty() {return savedFingerprint===null ? Boolean(input.value||output) : savedFingerprint!==core.fingerprint(draft());}
    function notice(title,text) {$('#notice-title').textContent=title;$('#notice-body').textContent=text;$('#desktop-notice').showModal();}
    function controls() {
        document.querySelectorAll('#intelPrompt, #depthSlider, #cueToggle, [data-preset], [data-format], #generateBtn, #desktop-regenerate, #desktop-clear, #desktop-copy, #draft-save, #draft-reload, #project-new').forEach(el=>{el.disabled=busy;});
        $('#desktop-broll').disabled=busy||!account||!project;
        $('#desktop-regenerate').disabled=busy||!lastRequest;
        $('#desktop-clear').disabled=busy||!output;
        $('#desktop-copy').disabled=busy||!output;
        if($('#result-download'))$('#result-download').disabled=busy||!output;
        $('#desktop-pdf').disabled=busy||!account||!project||!version||!output||dirty();
        $('#draft-save').disabled=busy||!account||!project||project.archived===1;
        if($('#editor-save')){
            $('#editor-save').disabled=$('#draft-save').disabled;
            $('#editor-history').disabled=busy||!account||!project;
            $('#editor-revert').disabled=busy||!account||!project||!version;
            $('#draft-editor').disabled=busy||project?.archived===1;
            if($('#draft-editor').value!==output)$('#draft-editor').value=output;
            $('#editor-undo').disabled=busy||!undo.length;$('#editor-redo').disabled=busy||!redo.length;
            document.querySelectorAll('[data-editor-command]').forEach(button=>button.disabled=busy||project?.archived===1);
        }
        $('#draft-reload').disabled=busy||!account||!project;
        $('#generateBtn').textContent=busy?'Working…':'Generate test response';
        generationUI?.contextChanged();
        $('#desktop-version').textContent=version?'Saved version '+version:'Not saved';
        $('#draft-state').textContent=dirty()?'Unsaved changes':version?'Saved':'No saved draft';
        $('#desktop-account').textContent=account?account.username:'Guest';
        $('#account-open').textContent=account?'Account':'Sign in';
        $('#current-project').textContent=project?project.title:'No project selected';
        $('#desktop-title').textContent=project?project.title:'Content preview';
        $('#desktop-mode').textContent=output?(mode==='stub'?'Test response - AI not connected':dirty()?'Unsaved draft - not approved':'Saved draft - not approved'):'No draft output';
        $('#desktop-words').textContent=(output.trim()?output.trim().split(/\s+/u).length:0)+' words';
        if($('#result-chapter-count'))$('#result-chapter-count').textContent=core.splitChapters(output).length+' chapters';
        if($('#result-format'))$('#result-format').textContent=selected.replaceAll('_',' ');
        $('#charCount').textContent=Array.from(input.value).length+' / 2000 chars';
        $('#depthLabel').textContent=depthNames[depth.value];
        cue.setAttribute('aria-checked',String(audio));cue.style.justifyContent=audio?'flex-end':'flex-start';cue.style.backgroundColor=audio?'#00ff87':'#31353f';
        document.querySelectorAll('[data-format]').forEach(card=>{
            card.setAttribute('aria-checked',String(card.dataset.format===selected));card.tabIndex=card.dataset.format===selected?0:-1;
            card.classList.toggle('ring-2',card.dataset.format===selected);
            const label=card.querySelector('[data-selected-label]');if(label)label.textContent=card.dataset.format===selected?'Selected':'YouTube';
        });
        $('#account-form').hidden=Boolean(account);$('#account-logout').hidden=!account;
        content.setAttribute('aria-busy',String(busy));
    }
    function chapters() {
        const parts=core.splitChapters(output), tabs=$('#desktop-chapters');tabs.replaceChildren();
        if(chapter>=parts.length)chapter=0;
        parts.forEach((part,index)=>{
            const button=document.createElement('button');button.type='button';button.textContent=part.title;
            button.setAttribute('aria-pressed',String(index===chapter));
            button.addEventListener('click',()=>{chapter=index;chapters();});tabs.append(button);
        });
        content.textContent=parts.length?parts[chapter].content:'Your test response or saved draft will appear here.';
        controls();
    }
    async function request(path,method='GET',body,blob=false) {
        const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),15000);
        try {
            const response=await fetch(path,{method,credentials:'same-origin',signal:controller.signal,headers:{...(body?{'Content-Type':'application/json'}:{}),...(csrf?{'X-CSRF-Token':csrf}:{}),...(path==='/api/auth/login'?{'X-Studio-Request':'1'}:{})},...(body?{body:JSON.stringify(body)}:{})});
            if(!response.ok){
                let detail;try{detail=(await response.json()).detail;}catch{}
                if(response.status===401){account=null;csrf=null;controls();}
                const error=Error(detail?.message||`Request failed (${response.status}). Your editor is preserved.`);error.status=response.status;error.code=detail?.code;throw error;
            }
            if(response.status===204)return null;
            if(blob)return await response.blob();
            try{return await response.json();}catch{throw Error('The server returned invalid JSON. Your editor is preserved.');}
        }catch(error){if(error.name==='AbortError')throw Error('The request timed out. Your editor is preserved.');if(error instanceof TypeError)throw Error('Could not connect. Your editor is preserved.');throw error;}
        finally{clearTimeout(timer);}
    }
    async function operation(action) {
        if(busy)return;busy=true;controls();
        try{await action();}catch(error){const text=error.status===401?'Sign in to continue. '+error.message:error.message;message(text);for(const [dialog,status] of [['new-project-dialog','new-project-status'],['media-dialog','media-status'],['account-dialog','account-status']]){if($('#'+dialog)?.open)$('#'+status).textContent=text;}}
        finally{busy=false;controls();}
    }
    function applyDraft(saved) {
        clearMedia();
        undo=[];redo=[];
        input.value=saved.news;output=saved.content;selected=saved.content_type;depth.value=String(saved.depth??3);audio=Boolean(saved.audio_cues??true);mode=saved.content_mode??'unknown';version=saved.version;
        lastRequest=output&&mode==='stub'?{news:input.value.trim(),content_type:selected,depth:Number(depth.value),audio_cues:audio}:null;
        savedFingerprint=core.fingerprint(draft());chapter=0;chapters();
    }
    async function loadProject(id,discard=false) {
        if(busy)return;
        if(!discard&&project&&dirty()){message('Save or reload the current draft before switching projects.');return;}
        await operation(async()=>{
            const next=await request('/api/projects/'+encodeURIComponent(id));
            let saved;
            try{saved=await request('/api/projects/'+next.id+'/draft');}catch(error){if(error.code!=='draft_not_found')throw error;}
            project=next;
            applyDraft(saved||{news:'',content:'',content_type:'youtube_script',depth:3,audio_cues:true,content_mode:'unknown',version:0});
            navigate('create',true);message(saved?'Saved draft and settings loaded.':'Project opened. No draft has been saved.');
        });
    }
    function navigate(next,replace=false) {
        view=next;const url=new URL(window.location.href);url.searchParams.set('view',view);
        if(project)url.searchParams.set('project',project.id);else url.searchParams.delete('project');
        window.history[replace?'replaceState':'pushState']({},'',url);
        document.querySelectorAll('a[data-path]').forEach(link=>{
            const destination=new URL('/desktop',window.location.origin);destination.searchParams.set('view',link.dataset.path);if(project)destination.searchParams.set('project',project.id);link.href=destination;
            const active=link.dataset.path===view;link.classList.toggle('bg-primary-container',active);link.classList.toggle('text-on-primary-container',active);if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
        });
        $('#desktop-sidebar').classList.remove('sidebar-open');$('#sidebar-toggle').setAttribute('aria-expanded','false');
        $('#create-view').hidden=view!=='create';$('#navigation-view').hidden=view==='create';
        if(view!=='create')renderView().catch(error=>message(error.message));
    }
    function addText(parent,tag,text) {const el=document.createElement(tag);el.textContent=text;parent.append(el);return el;}
    async function renderView() {
        const serial=++navSequence, section=$('#navigation-view');section.replaceChildren();addText(section,'h2',view==='projects'?'Projects':view==='scripts'?'Saved script preview':view==='research'?'Research and review':'Workspace dashboard');
        if(!account){addText(section,'p','Sign in to view saved projects.');return;}
        if(view==='projects'||view==='dashboard'){
            let offset=0;
            const list=document.createElement('div');section.append(list);
            const more=addText(section,'button','Load more projects');more.type='button';more.className='desktop-action';
            async function page(){more.disabled=true;try{
                const data=await request('/api/projects?limit=50&offset='+offset);
                if(serial!==navSequence)return;
                if(!offset&&!data.items.length)addText(list,'p','No projects yet. Use New project to begin.');
                data.items.forEach(item=>{const row=document.createElement('div');addText(row,'span',item.title+' ');const open=addText(row,'button','Open project');open.className='desktop-action';open.addEventListener('click',()=>loadProject(item.id));list.append(row);});
                offset+=data.items.length;more.hidden=data.items.length<50;
            }finally{more.disabled=false;}}
            more.addEventListener('click',()=>page().catch(error=>message(error.message)));await page();
            if(view==='dashboard'&&project)addText(section,'p',`Current project: ${project.title}. Saved draft version: ${version}. ${dirty()?'Editor has unsaved changes.':'Editor matches saved work.'}`);
        }else if(view==='scripts'){
            if(!project){addText(section,'p','Open a project to preview its saved script.');return;}
            let saved;try{saved=await request('/api/projects/'+project.id+'/draft');}catch(error){if(error.code==='draft_not_found'){addText(section,'p','No saved draft output.');return;}throw error;}
            if(serial!==navSequence)return;
            addText(section,'p',`Project: ${project.title}. Saved version ${saved.version}; this read-only preview is not approved for publishing.`);
            addText(section,'pre',saved.content||'No saved draft output.');
        }else if(view==='research'){
            if(!project){addText(section,'p','Select a project first.');return;}
            await window.PulseResearch.render({root:section,request,project,active:()=>serial===navSequence&&view==='research'});
        }
    }
    async function generate(reuse=false) {
        const selectedRequest=reuse&&lastRequest?{...lastRequest}:{news:input.value.trim(),content_type:selected,depth:Number(depth.value),audio_cues:audio};
        if(!core.validateRequest(selectedRequest)){message('Enter football news within 2,000 characters and valid options.');input.focus();return;}
        await operation(async()=>{
            message('Requesting a test response…');const data=await request('/api/generate','POST',selectedRequest);
            if(typeof data.content!=='string'||!data.content.trim()||data.mode!=='stub'||data.content_type!==selectedRequest.content_type||data.depth!==selectedRequest.depth||data.audio_cues!==selectedRequest.audio_cues)throw Error('The response does not match the request. Previous output is preserved.');
            output=data.content;mode='stub';lastRequest={...selectedRequest};chapter=0;chapters();message('Test response received. AI is not connected. Save explicitly to retain this draft.');
            undo=[];redo=[];controls();
        });
    }
    async function save() {
        if(!account||!project){message('Sign in and choose a project before saving.');return;}
        const current=draft();
        if(output&&lastRequest&&!core.sameSettings({...current,news:current.news.trim()},lastRequest)){message('Input or settings changed since this response. Generate again or clear the output before saving.');return;}
        await operation(async()=>{const saved=await request('/api/projects/'+project.id+'/draft','PUT',{...current,expected_version:version});version=saved.version;savedFingerprint=core.fingerprint(current);message('Draft and settings saved as version '+version+'.');});
    }
    async function reload() {
        if(!project)return;
        if(dirty()){$('#reload-dialog').showModal();return;}
        await loadProject(project.id,true);
    }
    function openPrompter(fullscreen=false) {
        if(!output){message('Load or generate a draft first.');return;}
        $('#desktop-prompter-text').textContent=output;$('#prompter-status').textContent='';$('#desktop-prompter').showModal();
        if(fullscreen)enterFullscreen();
    }
    async function enterFullscreen() {
        try{if(!$('#desktop-prompter').requestFullscreen)throw Error();await $('#desktop-prompter').requestFullscreen();$('#prompter-status').textContent='Fullscreen active. Press Escape to exit.';}
        catch{$('#prompter-status').textContent='Fullscreen is unavailable. The teleprompter remains open.';}
    }
    input.addEventListener('input',controls);depth.addEventListener('input',controls);
    cue.addEventListener('click',()=>{if(busy)return;audio=!audio;controls();});
    document.querySelectorAll('[data-format]').forEach(card=>card.addEventListener('click',()=>{if(busy)return;selected=card.dataset.format;controls();}));
    document.querySelector('[role=radiogroup]').addEventListener('keydown',event=>{
        if(busy||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
        event.preventDefault();const direction=['ArrowLeft','ArrowUp'].includes(event.key)?-1:1;
        const index=(core.formats.indexOf(selected)+direction+core.formats.length)%core.formats.length;selected=core.formats[index];controls();document.querySelector(`[data-format="${selected}"]`).focus();
    });
    document.querySelectorAll('[data-pipeline]').forEach(button=>button.addEventListener('click',()=>{navigate(button.dataset.pipeline);if(button.dataset.pipeline==='create')input.focus();}));
    document.querySelectorAll('[data-preset]').forEach(button=>button.addEventListener('click',()=>{
        if(busy)return;const next=input.value+(input.value?'\n':'')+button.dataset.preset;
        if(Array.from(next).length>2000){message('Preset exceeds the input limit. Your input is unchanged.');return;}
        input.value=next;controls();input.focus();message('Unverified context prompt added. Add your dated evidence.');
    }));
    $('#generateBtn').addEventListener('click',()=>generate());$('#desktop-regenerate').addEventListener('click',()=>generate(true));
    $('#draft-save').addEventListener('click',save);$('#draft-reload').addEventListener('click',reload);
    function editorMode(value){
        editing=value;$('#draft-editor').hidden=!editing;$('#draft-editor-label').hidden=!editing;$('#editor-tools').hidden=!editing;content.hidden=editing;
        $('#editor-edit').setAttribute('aria-pressed',String(editing));$('#editor-view').setAttribute('aria-pressed',String(!editing));
        controls();if(editing)$('#draft-editor').focus();
    }
    function edit(value){
        if(busy||project?.archived===1)return;
        if(Array.from(value).length>200000){message('The script exceeds 200,000 characters.');controls();return;}
        undo.push(output);if(undo.length>50)undo.shift();redo=[];output=value;mode='manual';lastRequest=null;chapters();
        message('Manual edits are unsaved. Save Changes to create a revision.');
    }
    $('#editor-edit')?.addEventListener('click',()=>editorMode(true));$('#editor-view')?.addEventListener('click',()=>editorMode(false));
    $('#editor-save')?.addEventListener('click',save);$('#editor-revert')?.addEventListener('click',reload);
    $('#draft-editor')?.addEventListener('input',event=>edit(event.target.value));
    document.querySelectorAll('[data-editor-command]').forEach(button=>button.addEventListener('click',()=>{
        const editor=$('#draft-editor'),change=core.editSelection(output,editor.selectionStart,editor.selectionEnd,button.dataset.editorCommand);
        if(change){edit(change.value);editor.focus();editor.setSelectionRange(change.start,change.end);}
    }));
    $('#editor-undo')?.addEventListener('click',()=>{if(busy||!undo.length)return;redo.push(output);output=undo.pop();mode='manual';lastRequest=null;chapters();});
    $('#editor-redo')?.addEventListener('click',()=>{if(busy||!redo.length)return;undo.push(output);output=redo.pop();mode='manual';lastRequest=null;chapters();});
    $('#editor-history')?.addEventListener('click',()=>operation(async()=>{
        const ownedProject=project.id,list=$('#revision-list');list.replaceChildren();$('#revision-preview').textContent='';$('#revision-status').textContent='Select a saved revision to preview.';selectedRevision=null;$('#revision-restore').disabled=true;
        let offset=0;const more=document.createElement('button');more.type='button';more.textContent='Load more revisions';list.append(more);
        async function page(){more.disabled=true;try{
            const data=await request(`/api/projects/${ownedProject}/revisions?limit=50&offset=${offset}`);
            if(project?.id!==ownedProject)return;
            for(const revision of data.items){const button=document.createElement('button');button.type='button';button.textContent=`Version ${revision.version} · ${revision.created_at}`;list.insertBefore(button,more);
                button.addEventListener('click',()=>operation(async()=>{
                    const saved=await request(`/api/projects/${ownedProject}/revisions/${revision.id}`);
                    if(project?.id!==ownedProject||!$('#revision-dialog').open)return;
                    selectedRevision={...saved,ownerProject:ownedProject};$('#revision-preview').textContent=saved.content;$('#revision-restore').disabled=project.archived===1;
                    $('#revision-status').textContent=`Previewing version ${saved.version}. Restoring replaces the editor and creates a new saved version.`;
                }));
            }
            offset+=data.items.length;more.hidden=data.items.length<50;
        }finally{more.disabled=false;}}
        more.addEventListener('click',()=>operation(page));await page();$('#revision-dialog').showModal();
    }));
    $('#revision-restore')?.addEventListener('click',()=>operation(async()=>{
        if(!selectedRevision||project?.id!==selectedRevision.ownerProject)throw Error('Select a revision from the current project.');
        const restored=await request(`/api/projects/${project.id}/revisions/${selectedRevision.id}/restore`,'POST',{expected_version:version});
        applyDraft(restored);$('#revision-dialog').close();message('Revision restored as new saved version '+restored.version+'.');
    }));
    $('#reload-confirm').addEventListener('click',async()=>{$('#reload-dialog').close();await loadProject(project.id,true);});
    $('#desktop-clear').addEventListener('click',()=>{if(busy)return;output='';mode='unknown';lastRequest=null;chapter=0;chapters();message('Output cleared. Input and settings remain. Save to retain this change.');});
    $('#desktop-copy').addEventListener('click',()=>operation(async()=>{
        if(!output)return;
        try{if(!navigator.clipboard?.writeText)throw Error();await navigator.clipboard.writeText(output);message('Full draft copied, including every chapter.');}
        catch{message('Clipboard access failed. Select and copy the draft manually.');}
    }));
    $('#result-download')?.addEventListener('click',()=>{
        if(busy||!output)return;
        const url=URL.createObjectURL(new Blob([output],{type:'text/plain;charset=utf-8'}));
        const link=document.createElement('a');link.href=url;link.download='football-pulse-complete-script.txt';document.body.append(link);link.click();link.remove();
        setTimeout(()=>URL.revokeObjectURL(url),60000);message('Complete script download requested, including every chapter and unsaved text.');
    });
    $('#result-tone-open')?.addEventListener('click',()=>$('#result-tone-dialog').showModal());
    $('#result-tone-confirm')?.addEventListener('click',async()=>{
        const tone=$('#result-tone').value;$('#result-tone-dialog').close();await generationUI?.regenerateTone(tone);
    });
    $('#desktop-pdf').addEventListener('click',()=>operation(async()=>{
        if(!project||!version||dirty())throw Error('Save or reload this draft before exporting.');
        const blob=await request(`/api/projects/${project.id}/draft/export.pdf?expected_version=${version}`,'GET',undefined,true);
        const url=URL.createObjectURL(blob), link=document.createElement('a');link.href=url;link.download='football-pulse-draft.pdf';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);message('Saved draft PDF ready; download requested.');
    }));
    function clearMedia(){
        const player=$('#media-player');if(!player)return;
        player.pause();player.removeAttribute('src');player.load();player.hidden=true;
        if(mediaUrl){URL.revokeObjectURL(mediaUrl);mediaUrl=null;}
    }
    $('#media-dialog').addEventListener('close',clearMedia);
    $('#media-player').addEventListener('loadedmetadata',()=>{
        const player=$('#media-player');if(!mediaUrl)return;
        if(!Number.isFinite(player.duration)||!player.videoWidth){$('#media-status').textContent='This clip has no readable video track.';return;}
        $('#media-status').textContent=`Source video ready: ${player.videoWidth} × ${player.videoHeight}, ${player.duration.toFixed(1)} seconds.`;
    });
    $('#media-player').addEventListener('error',()=>{if(mediaUrl)$('#media-status').textContent='This file could not be decoded as a playable video. No preview is available.';});
    $('#desktop-broll').addEventListener('click',()=>operation(async()=>{
        if(!account||!project)throw Error('Sign in and select a project before previewing footage.');
        clearMedia();const list=$('#media-assets');list.replaceChildren();$('#media-status').textContent='Choose a saved source clip.';
        let offset=0;const more=document.createElement('button');more.textContent='Load more assets';more.type='button';list.append(more);
        async function page(){more.disabled=true;try{
            const data=await request(`/api/projects/${project.id}/assets?limit=50&offset=${offset}`);
            data.items.filter(asset=>asset.media_type==='video/mp4').forEach(asset=>{
                const button=document.createElement('button');button.type='button';button.textContent=asset.filename;list.insertBefore(button,more);
                const ownerProject=project.id;
                button.addEventListener('click',()=>operation(async()=>{
                    if(project?.id!==ownerProject)throw Error('The project changed. Reopen its media preview.');
                    clearMedia();$('#media-status').textContent='Loading source clip…';
                    const bytes=await request(`/api/projects/${ownerProject}/assets/${asset.id}/download`,'GET',undefined,true);
                    if(!$('#media-dialog').open)return;
                    mediaUrl=URL.createObjectURL(new Blob([bytes],{type:'video/mp4'}));$('#media-player').src=mediaUrl;$('#media-player').hidden=false;
                }));
            });
            offset+=data.items.length;more.hidden=data.items.length<50;
            if(!list.querySelector('button:not(:last-child)')&&more.hidden)$('#media-status').textContent='No saved MP4 clips in this project.';
        }finally{more.disabled=false;}}
        more.addEventListener('click',()=>page().catch(error=>message(error.message)));await page();$('#media-dialog').showModal();
    }));
    $('#desktop-stage').addEventListener('click',()=>message(!output?'Load or generate a draft first.':'Scripts & SEO processing is not connected. This preview cannot be treated as approved content.'));
    $('#teleprompter-open').addEventListener('click',()=>openPrompter());$('#teleprompter-fullscreen-open').addEventListener('click',()=>openPrompter(true));$('#prompter-fullscreen').addEventListener('click',enterFullscreen);
    document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',async()=>{
        if(button.dataset.close==='desktop-prompter'&&document.fullscreenElement)await document.exitFullscreen();$('#'+button.dataset.close).close();
    }));
    $('#sidebar-toggle').addEventListener('click',()=>{const open=$('#desktop-sidebar').classList.toggle('sidebar-open');$('#sidebar-toggle').setAttribute('aria-expanded',String(open));});
    function newProject() {
        if(!account){message('Sign in before creating a saved project.');$('#account-dialog').showModal();return;}
        if(project&&dirty()){message('Save or reload your changes before creating another project.');return;}
        $('#new-project-status').textContent='';$('#new-project-dialog').showModal();
    }
    $('#project-new').addEventListener('click',newProject);$('#project-open').addEventListener('click',()=>navigate('projects'));$('#account-open').addEventListener('click',()=>$('#account-dialog').showModal());
    document.querySelectorAll('[data-unavailable]').forEach(control=>control.addEventListener('click',event=>{event.preventDefault();notice('Not connected yet',control.dataset.unavailable);}));
    document.querySelectorAll('a[data-path]').forEach(link=>link.addEventListener('click',event=>{
        event.preventDefault();if(link.dataset.unavailable)return;if(link.dataset.action==='account'){$('#account-dialog').showModal();return;}navigate(link.dataset.path);
    }));
    document.querySelectorAll('[data-action]').forEach(button=>{if(button.tagName==='A')return;button.addEventListener('click',()=>{
        if(button.dataset.action==='new-project')newProject();
        else if(button.dataset.action==='projects')navigate('projects');
        else if(button.dataset.action==='help')notice('Workspace help','Sign in and choose a project. Use Research to save sources, attach exact evidence and explicitly review claims. Refresh reviewed claims in Create to generate when a provider is configured. Edit Mode supports Markdown text and cue markers. Save explicitly for revisions; PDF uses the saved draft, and TXT downloads include current unsaved text. The provider panel reports availability.');
        else if(button.dataset.action==='jobs')operation(async()=>{if(!account||!project)throw Error('Sign in and select a project first.');const data=await request('/api/projects/'+project.id+'/jobs');notice('Project jobs',data.items.length?data.items.map(job=>`${job.kind}: ${job.status} (${job.progress}%)`).join('\n'):'No jobs in this project. Workers are not connected.');});
    });});
    $('#new-project-form').addEventListener('submit',event=>{event.preventDefault();operation(async()=>{
        const title=$('#new-project-title').value.trim();if(!title)throw Error('Enter a project title.');
        const carryEditor=!project;
        project=await request('/api/projects','POST',{title});version=0;savedFingerprint=null;
        if(!carryEditor)applyDraft({news:'',content:'',content_type:'youtube_script',depth:3,audio_cues:true,content_mode:'unknown',version:0});$('#new-project-dialog').close();navigate('create',true);message('Project created. Save the editor draft explicitly.');
    });});
    $('#account-form').addEventListener('submit',event=>{event.preventDefault();operation(async()=>{
        try{const result=await request('/api/auth/login','POST',{username:$('#account-user').value,password:$('#account-password').value});
            if(previousUser&&previousUser!==result.user.id){project=null;applyDraft({news:'',content:'',content_type:'youtube_script',depth:3,audio_cues:true,content_mode:'unknown',version:0});}
            account=result.user;previousUser=account.id;csrf=result.csrf_token;$('#account-dialog').close();message('Signed in.');navigate('create',true);
        }catch(error){$('#account-status').textContent=error.message;throw error;}finally{$('#account-password').value='';}
    });});
    $('#account-logout').addEventListener('click',()=>{if(dirty()){$('#logout-dialog').showModal();return;}signOut();});
    $('#logout-confirm').addEventListener('click',()=>{$('#logout-dialog').close();signOut();});
    function signOut(){return operation(async()=>{
        await request('/api/auth/logout','POST');account=null;previousUser=null;csrf=null;project=null;savedFingerprint=null;applyDraft({news:'',content:'',content_type:'youtube_script',depth:3,audio_cues:true,content_mode:'unknown',version:0});$('#account-dialog').close();navigate('create',true);message('Signed out. Private editor content cleared.');
    });}
    window.addEventListener('beforeunload',event=>{if(dirty()){event.preventDefault();event.returnValue='';}});
    window.addEventListener('popstate',async()=>{
        const query=new URLSearchParams(window.location.search), id=query.get('project'), next=query.get('view')||'create';
        if(id!==project?.id){
            if(busy||dirty()){navigate(view,true);message('Save or reload changes before changing project history.');return;}
            if(id){await loadProject(id);if(project?.id!==id)return;}
            else{project=null;applyDraft({news:'',content:'',content_type:'youtube_script',depth:3,audio_cues:true,content_mode:'unknown',version:0});}
        }
        navigate(['create','projects','dashboard','research','scripts'].includes(next)?next:'create',true);
    });
    async function start() {
        chapters();
        try{const result=await request('/api/auth/session');account=result.user;previousUser=account.id;csrf=result.csrf_token;}catch(error){if(error.status!==401)message(error.message);}
        controls();const query=new URLSearchParams(window.location.search), id=query.get('project'), initial=query.get('view');
        if(id&&account)await loadProject(id,true);else if(id)message('Sign in to open the requested project.');
        if(['projects','dashboard','research','scripts'].includes(initial))navigate(initial,true);
    }
    generationUI=window.PulseGeneration?.install({request,context:()=>({project:account?project:null,busy,content_type:selected,depth:Number(depth.value),audio_cues:audio}),receive:result=>{
        input.value=result.payload.review_snapshot.map(claim=>claim.statement).join('\n').slice(0,2000);
        selected=result.payload.content_type;depth.value=String(result.payload.depth);audio=result.payload.audio_cues;
        output=result.content;mode='unknown';lastRequest=null;undo=[];redo=[];chapter=0;chapters();
        message('AI draft from job '+result.job_id+' loaded. It requires human review. Save explicitly to retain editor changes.');
    }});
    start().catch(error=>message(error.message));
})();
