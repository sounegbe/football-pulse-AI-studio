const test=require('node:test'), assert=require('node:assert/strict');
const core=require('../app/static/js/desktop-core.js');
test('chapters preserve all exact text, heading spans and literal markup',()=>{
 const text='  Opening text\n## Chapter 1 — First\n<img>\n\n## Chapter 2 — Last\nFinal\n';const parts=core.splitChapters(text);
 assert.equal(parts.length,3);assert.equal(parts.map(p=>p.content).join(''),text);assert.equal(parts[2].title,'Chapter 2 — Last');assert.match(parts[1].content,/<img>/);
});
test('single and empty draft chapter behavior has no invented chapter',()=>{assert.deepEqual(core.splitChapters(''),[]);assert.deepEqual(core.splitChapters('Literal draft'),[{title:'Full draft',content:'Literal draft'}]);});
test('request validation enforces Unicode length, enum and strict options',()=>{
 const valid={news:'😀'.repeat(2000),content_type:'youtube_script',depth:2,audio_cues:false};assert.equal(core.validateRequest(valid),true);
 for(const bad of [{news:' '},{news:'😀'.repeat(2001)},{depth:'2'},{depth:true},{depth:4},{audio_cues:0},{content_type:'evil'}])assert.equal(core.validateRequest({...valid,...bad}),false);
});
test('dirty fingerprint tracks exact whitespace and every persisted option',()=>{
 const value={news:' Notes ',content:' Text\n',content_type:'youtube_script',depth:3,audio_cues:true,content_mode:'stub'};
 for(const changed of [{news:'Notes'},{content:'Text'},{content_type:'social_post'},{depth:2},{audio_cues:false},{content_mode:'manual'}])assert.notEqual(core.fingerprint(value),core.fingerprint({...value,...changed}));
 assert.equal(core.fingerprint(value),core.fingerprint({...value,audio_cues:1}));
});
test('response can be saved only with its original request settings',()=>{
 const a={news:'notes',content_type:'youtube_script',depth:2,audio_cues:false};assert.equal(core.sameSettings(a,{...a}),true);
 for(const changed of [{news:'changed'},{content_type:'social_post'},{depth:3},{audio_cues:true}])assert.equal(core.sameSettings(a,{...a,...changed}),false);
});
