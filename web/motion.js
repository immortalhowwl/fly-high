/* Independent identity clocks. Visual flight never changes execution truth. */
(function(root){
 function hash(id){let n=2166136261;for(const c of id)n=Math.imul(n^c.charCodeAt(0),16777619);return (n>>>0)/4294967296;}
 function position(id,t,w,h){
  const seed=hash(id), phase=seed*Math.PI*30, speed=0.18+seed*0.13;
  return {x:w*(0.5+0.32*Math.sin(t*speed+phase)+0.06*Math.sin(t*.57+phase*2)),
          y:h*(0.50+0.30*Math.cos(t*speed*.83+phase*1.7)+0.07*Math.sin(t*.41+phase)),phase};
 }
 const api={position,hash};if(typeof module!=='undefined')module.exports=api;else root.Flight=api;
})(typeof window==='undefined'?globalThis:window);
