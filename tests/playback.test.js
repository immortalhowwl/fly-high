'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const Playback=require('../web/playback.js');
test('independent visitors, all controls and bounded end of archive',()=>{
 const report={split:10,generations:[{},{}]};
 const a=new Playback(report),b=new Playback(report);
 a.control('run');a.tick(.25);assert.equal(a.cursor,5);assert.equal(b.cursor,0);assert.equal(b.running,false);
 a.control('pause');a.tick(1);assert.equal(a.cursor,5);
 a.control('generation');assert.equal(a.cursor,10);
 a.control('run');a.tick(100);assert.equal(a.cursor,19);assert.equal(a.running,false);
 a.control('replay');assert.equal(a.cursor,0);assert.equal(a.running,true);
 a.control('reset');assert.equal(a.cursor,0);assert.equal(a.running,false);
 assert.throws(()=>a.control('unknown'));
});
