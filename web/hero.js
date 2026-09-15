'use strict';
(()=>{
 const video=document.getElementById('hero-video');if(!video)return;
 const frame=video.closest('.hero-visual'),reduced=matchMedia('(prefers-reduced-motion: reduce)');
 video.controls=false;video.muted=true;video.defaultMuted=true;video.playsInline=true;video.disablePictureInPicture=true;
 const conceal=()=>frame.classList.remove('film-playing');
 const reveal=()=>{if(!video.paused&&!video.ended&&!document.hidden)frame.classList.add('film-playing');};
 video.addEventListener('playing',()=>{if(video.requestVideoFrameCallback)video.requestVideoFrameCallback(reveal);else reveal();});
 ['pause','ended','error','emptied','waiting'].forEach(e=>video.addEventListener(e,conceal));
 const play=()=>{if(document.hidden||reduced.matches)return;video.play().catch(conceal);};
 conceal();if(reduced.matches){video.autoplay=false;video.pause();}else play();
 document.addEventListener('visibilitychange',()=>{if(document.hidden){conceal();video.pause();}else play();});
 reduced.addEventListener('change',e=>{if(e.matches){conceal();video.pause();}else play();});
 // iOS may block autoplay in Low Power Mode. Retry on ordinary interaction;
 // until real playback starts the visible surface remains the clean poster.
 document.addEventListener('pointerdown',play,{passive:true});
 document.addEventListener('touchend',play,{passive:true});
})();
