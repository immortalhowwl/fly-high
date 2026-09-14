'use strict';
// A playback instance belongs only to this browser tab. No server sessions.
class Playback {
 constructor(report){this.split=report.split;this.end=report.split*report.generations.length-1;this.cursor=0;this.running=false;}
 tick(seconds){if(this.running){this.cursor=Math.min(this.end,this.cursor+Math.max(0,seconds)*20);if(this.cursor>=this.end)this.running=false;}return this;}
 control(action){
  if(action==='run')this.running=this.cursor<this.end;
  else if(action==='pause')this.running=false;
  else if(action==='reset'){this.cursor=0;this.running=false;}
  else if(action==='replay'){this.cursor=0;this.running=true;}
  else if(action==='generation'){this.cursor=Math.min(this.end,(Math.floor(this.cursor/this.split)+1)*this.split);if(this.cursor===this.end)this.running=false;}
  else throw Error('unknown action');
  return this;
 }
}
if(typeof module!=='undefined')module.exports=Playback;
