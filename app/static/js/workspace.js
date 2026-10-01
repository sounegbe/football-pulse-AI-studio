(() => {
    const $ = selector => document.querySelector(selector);
    const input = $('#intel-input'), result = $('#generated-content'), status = $('#workspace-status');
    const generate = $('#generate-trigger-btn'), regenerate = $('#regenerate-btn');
    const copy = $('#copy-script-btn'), clearResult = $('#clear-result-btn');
    const depth = $('#depth-slider'), cues = $('#audio-cues');
    const names = {1:'Casual Supporter Narrative', 2:'Studio Pundit Tactical View', 3:'Pro Analyst'};
    const formats = {article:'news_article', youtube:'youtube_script', short:'short_video', social_post:'social_post'};
    let pending = false, output = '', lastRequest = null, copying = false;
    const controls = Array.from(document.querySelectorAll('#intel-input, #depth-slider, #audio-cues, input[name=blueprint], .quick-chip, [data-note], #clear-btn, #generate-trigger-btn, #regenerate-btn, #clear-result-btn, #copy-script-btn'));
    function message(text) { status.textContent = text; }
    function counter() { $('#char-counter').textContent = `${Array.from(input.value).length} / 2000 chars`; }
    function refresh() {
        controls.forEach(control => { control.disabled = pending; });
        copy.disabled = pending || copying || !output;
        regenerate.disabled = pending || !lastRequest;
        clearResult.disabled = pending || !output;
        result.setAttribute('aria-busy', String(pending));
        generate.textContent = pending ? 'Generating test response…' : 'Generate test response';
    }
    function appendNote(text) {
        if (pending) return;
        const next = input.value + (input.value ? '\n' : '') + text;
        if (Array.from(next).length > 2000) { message('This note exceeds the 2,000-character limit. Your input is unchanged.'); return; }
        input.value = next; counter(); input.focus();
    }
    input.addEventListener('input', counter);
    depth.addEventListener('input', () => { $('#depth-label').textContent = names[depth.value]; });
    document.querySelectorAll('.quick-chip').forEach(button => button.addEventListener('click', () => {
        if (pending) return;
        input.value = button.dataset.fill; counter(); input.focus(); message('Example context loaded. These claims have not been verified.');
    }));
    document.querySelectorAll('[data-note]').forEach(button => button.addEventListener('click', () => appendNote(`[${button.dataset.note}: add your dated source and measurements here]`)));
    $('#clear-btn').addEventListener('click', () => { if (pending) return; input.value = ''; counter(); input.focus(); message('Input cleared. The previous response remains available.'); });
    async function run(reuse = false) {
        if (pending) return;
        const selection = $('input[name=blueprint]:checked');
        const request = reuse && lastRequest ? {...lastRequest} : {news: input.value.trim(), content_type: formats[selection?.value], depth:Number(depth.value), audio_cues:cues.checked};
        if (!request.news || Array.from(request.news).length > 2000 || !request.content_type || ![1,2,3].includes(request.depth)) {
            message(!request.news ? 'Please enter some football news first.' : 'Check the content format, depth and 2,000-character limit.'); input.focus(); return;
        }
        pending = true; refresh(); message('Sending your request…');
        const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
        try {
            const response = await fetch('/api/generate', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request),signal:controller.signal});
            if (!response.ok) throw Error(response.status === 422 ? 'The request was rejected. Check your input and options.' : response.status === 429 ? 'Too many requests. Please wait before retrying.' : 'The server could not complete the request. Please try again.');
            let data;
            try { data = await response.json(); } catch { throw Error('The server returned an invalid response. Please try again.'); }
            if (typeof data.content !== 'string' || !data.content.trim() || data.content_type !== request.content_type || data.mode !== 'stub' || data.depth !== request.depth || data.audio_cues !== request.audio_cues)
                throw Error('The server returned an unexpected response. Please try again.');
            output = data.content; lastRequest = {...request}; result.textContent = output;
            message(`Test response received • ${request.content_type} • ${names[request.depth]} • Audio cues ${request.audio_cues ? 'on' : 'off'}. AI is not connected. Regenerate repeats these settings.`);
        } catch (error) {
            message(error.name === 'AbortError' ? 'The request timed out. Your input and previous response are preserved.' : error instanceof TypeError ? 'Could not connect to the server. Your input and previous response are preserved.' : error.message);
        } finally { clearTimeout(timeout); pending = false; refresh(); }
    }
    generate.addEventListener('click', () => run());
    regenerate.addEventListener('click', () => run(true));
    copy.addEventListener('click', async () => {
        if (!output || pending || copying) return;
        copying = true; refresh();
        try { if (!navigator.clipboard?.writeText) throw Error(); await navigator.clipboard.writeText(output); message('Response copied to clipboard.'); }
        catch { message('Clipboard access failed. Select and copy the response manually.'); }
        finally { copying = false; refresh(); }
    });
    clearResult.addEventListener('click', () => {
        if (pending) return;
        output = ''; lastRequest = null; result.textContent = 'Your test response will appear here.'; message('Response cleared. Your input and options are preserved.'); refresh();
    });
    $('#push-stage-btn').addEventListener('click', () => message(pending ? 'Wait for the current request to finish.' : !output ? 'Generate a response first.' : 'Test responses cannot advance to Scripts & SEO. Reviewed AI content and the SEO workspace are required in later milestones.'));
    document.querySelectorAll('[data-unavailable]').forEach(control => control.addEventListener('click', event => {event.preventDefault(); message(control.dataset.unavailable);}));
    const prompter = $('#teleprompter');
    $('#teleprompter-btn')?.addEventListener('click', () => {
        if (!output) { message('Generate a response before opening the teleprompter.'); return; }
        $('#prompter-text').textContent = output; prompter.showModal();
    });
    $('#close-prompter')?.addEventListener('click', () => prompter.close());
    counter(); $('#depth-label').textContent = names[depth.value]; refresh();
})();
