() => {
 const cache=new Map(),style=e=>{if(!cache.has(e))cache.set(e,getComputedStyle(e));return cache.get(e)};
 const rect=e=>{const r=e.getBoundingClientRect();return {x:+r.x.toFixed(1),y:+r.y.toFixed(1),width:+r.width.toFixed(1),height:+r.height.toFixed(1)}};
 const visible=e=>{const r=e.getBoundingClientRect();if(r.width<1||r.height<1||r.bottom<0||r.top>=innerHeight||r.right<0||r.left>=innerWidth||style(e).visibility==='hidden'||style(e).display==='none')return false;const hit=document.elementFromPoint(Math.min(innerWidth-1,Math.max(0,r.x+r.width/2)),Math.min(innerHeight-1,Math.max(0,r.y+r.height/2)));return !hit||e.contains(hit)||hit.contains(e)};
 const label=e=>(e.getAttribute('aria-label')||e.getAttribute('placeholder')||e.getAttribute('title')||e.textContent||e.tagName).trim().replace(/\s+/g,' ').slice(0,75);
 const controls=[...document.querySelectorAll('button,a,input:not([type=hidden]):not([type=file]),textarea,select,[role=button]')].filter(visible).map(e=>{
  const effective=e.matches('input[type=checkbox],input[type=radio]')?(e.closest('label')||e):e;
  return {tag:e.tagName,label:label(effective),...rect(effective),font:+parseFloat(style(e).fontSize).toFixed(1),disabled:e.matches(':disabled,[aria-disabled=true]'),nameMissing:!e.getAttribute('aria-label')&&!e.getAttribute('title')&&!e.textContent.trim()&&!e.getAttribute('placeholder')&&!e.labels?.length};
 });
 function rgba(value){const p=value.match(/[\d.]+/g)?.map(Number);return value.startsWith('rgb')&&p?.length>=3?[p[0],p[1],p[2],p[3]??1]:null}
 function blend(a,b){return [0,1,2].map(i=>a[i]*a[3]+b[i]*(1-a[3])).concat(1)}
 function background(e){if(!e)return [255,255,255,1];const c=rgba(style(e).backgroundColor);return !c?background(e.parentElement):c[3]===1?c:blend(c,background(e.parentElement))}
 function lum(c){const n=c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return n[0]*.2126+n[1]*.7152+n[2]*.0722}
 const text=[];
 for(const e of document.querySelectorAll('button,p,label,span,h1,h2,h3,h4,a,input,textarea,select,summary')){
  if(!visible(e)||e.closest('[data-testid=issued-secret]')||(!e.matches('input,textarea,select')&&![...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())))continue;
  const css=style(e),bg=background(e),color=rgba(css.color);if(!color)continue;
  const ratio=(Math.max(lum(blend(color,bg)),lum(bg))+.05)/(Math.min(lum(blend(color,bg)),lum(bg))+.05);
  text.push({label:label(e),font:+parseFloat(css.fontSize).toFixed(1),color:css.color,background:bg.slice(0,3),ratio:+ratio.toFixed(2),disabled:e.matches(':disabled,[aria-disabled=true]')||Boolean(e.closest(':disabled,[aria-disabled=true]'))});
 }
 return {rootFont:getComputedStyle(document.documentElement).fontSize,horizontalOverflow:document.documentElement.scrollWidth>innerWidth,viewport:[innerWidth,innerHeight],controls,text,visibleNativeSelects:[...document.querySelectorAll('select')].filter(visible).length,dialogs:[...document.querySelectorAll('[role=dialog]')].filter(visible).map(e=>({label:e.getAttribute('aria-label')||document.getElementById(e.getAttribute('aria-labelledby'))?.textContent||'',...rect(e)}))};
}