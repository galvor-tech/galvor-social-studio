const SIL='<svg viewBox="0 0 100 100"><circle cx="50" cy="40" r="18" fill="rgba(255,255,255,.88)"/><path d="M12 104c0-24 17-38 38-38s38 14 38 38z" fill="rgba(255,255,255,.88)"/></svg>';
const HUES=[262,320,200,25,170,285,345,220,40,150,300,190,10,250,60,330,210,275,120,350];
function av(parent,x,y,size,i,opts={}){const d=document.createElement('div');
  d.className='av'+(opts.hero?' hero-av':(opts.dim===false?'':' dim'))+(opts.cls?' '+opts.cls:'');
  const h=HUES[i%HUES.length];
  d.style.cssText=`left:${x-size/2}px;top:${y-size/2}px;width:${size}px;height:${size}px;background:linear-gradient(165deg,hsl(${h} 60% 58%),hsl(${(h+40)%360} 60% 34%));`+(opts.css||'');
  d.innerHTML=SIL; parent.appendChild(d); return d;}
function lens(parent,cx,cy,r,ang=-40,len=240,w=58){
  const h=document.createElement('div');h.className='handle';
  const a=(ang+90)*Math.PI/180; // handle leaves the ring at bottom-right
  const hx=cx+Math.cos(Math.PI/4)*(r-4), hy=cy+Math.sin(Math.PI/4)*(r-4);
  h.style.cssText=`left:${hx-w/2}px;top:${hy}px;width:${w}px;height:${len}px;transform:rotate(${ang}deg)`;parent.appendChild(h);
  const l=document.createElement('div');l.className='lens';l.style.cssText=`left:${cx-r}px;top:${cy-r}px;width:${2*r}px;height:${2*r}px`;parent.appendChild(l);}
function chk(parent,x,y,text){const c=document.createElement('div');c.className='chk';c.style.left=x+'px';c.style.top=y+'px';
  c.innerHTML='<span class="t">✓</span>'+text;parent.appendChild(c);return c;}
const COPY=`<div class="kicker"><img src="mark.png" alt="">Decoded by Galvor <span>•</span> Issue #4</div>
<h1>We Shortlisted<br>20 Creators<span class="fs">.</span><br><span class="p">The Brand<br>Picked One<span class="fs">.</span></span></h1>
<div class="how"><span class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/></svg></span>How <b>Galvor Scout</b> finds <i>the one</i></div>`;
