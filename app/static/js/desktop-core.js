(function(root) {
    const formats = ['news_article','youtube_script','short_video','social_post'];
    function validateRequest(request) {
        return typeof request.news === 'string' && request.news.trim().length > 0 && Array.from(request.news.trim()).length <= 2000 && formats.includes(request.content_type) && Number.isInteger(request.depth) && request.depth >= 1 && request.depth <= 3 && typeof request.audio_cues === 'boolean';
    }
    function splitChapters(text) {
        if (!text) return [];
        const matches = Array.from(text.matchAll(/^#{1,3}[^\S\r\n]+(.+)$/gm));
        if (!matches.length) return [{title:'Full draft',content:text}];
        const result=[];
        if (matches[0].index>0) result.push({title:'Opening',content:text.slice(0,matches[0].index)});
        matches.forEach((match,index)=>result.push({title:match[1].trim(),content:text.slice(match.index,index+1<matches.length?matches[index+1].index:text.length)}));
        return result;
    }
    function fingerprint(draft) {return JSON.stringify([draft.news,draft.content,draft.content_type,draft.depth,Boolean(draft.audio_cues),draft.content_mode]);}
    function sameSettings(a,b) {return a.news === b.news && a.content_type === b.content_type && a.depth === b.depth && a.audio_cues === b.audio_cues;}
    function editSelection(text,start,end,kind) {
        const selected=text.slice(start,end), wrap={bold:['**','**'],italic:['_','_'],heading:['## ',''],quote:['> ',''],bullet:['- ','']};
        const cues={timecode:'[TIMECODE 00:00]',broll:'[B-ROLL: describe the required visual]',audio:'[AUDIO CUE: describe the required sound]'};
        if(!wrap[kind]&&!cues[kind])return null;
        const insert=wrap[kind]?wrap[kind][0]+selected+wrap[kind][1]:cues[kind];
        const value=text.slice(0,start)+insert+text.slice(end);
        if(Array.from(value).length>200000)return null;
        return {value,start:start+(wrap[kind]?.[0].length||0),end:start+(wrap[kind]?.[0].length||0)+(wrap[kind]?selected.length:insert.length)};
    }
    const api={formats,validateRequest,splitChapters,fingerprint,sameSettings,editSelection};
    if(typeof module!=='undefined'&&module.exports)module.exports=api;
    else root.PulseDesktop=api;
})(typeof window!=='undefined'?window:{});
