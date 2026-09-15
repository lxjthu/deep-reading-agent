document.addEventListener('DOMContentLoaded',()=>{
 document.querySelectorAll('a[data-download64]').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();const bytes=Uint8Array.from(atob(link.dataset.download64),c=>c.charCodeAt(0));const url=URL.createObjectURL(new Blob([bytes],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=link.getAttribute('href');document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}));
 const select=document.querySelector('[data-versions]');
 if(select){ const show=()=>document.querySelectorAll('[data-panel]').forEach(p=>p.hidden=p.id!==select.value);select.addEventListener('change',show);show(); }
 document.querySelectorAll('[data-tex]').forEach(el=>{if(window.katex){try{katex.render(el.dataset.tex,el,{displayMode:el.dataset.display==='true',throwOnError:true,trust:false,strict:'warn'});}catch(e){el.title='公式未识别，保留 LaTeX 原文';el.classList.add('math-fallback');}}});
 document.querySelector('[data-print]')?.addEventListener('click',()=>window.print());
 document.querySelector('[data-font]')?.addEventListener('input',e=>document.body.style.setProperty('--reader-size',e.target.value+'px'));
 document.querySelector('[data-width]')?.addEventListener('input',e=>document.body.style.setProperty('--reader-width',e.target.value+'px'));
 const rows=[...document.querySelectorAll('[data-entry]')], search=document.querySelector('[data-search]'), filter=document.querySelector('[data-filter]');let page=0;
 function update(){const q=(search?.value||'').toLocaleLowerCase(),type=filter?.value||'';const visible=rows.filter(r=>r.textContent.toLocaleLowerCase().includes(q)&&(!type||r.dataset.types.split(' ').includes(type)));const pages=Math.max(1,Math.ceil(visible.length/30));page=Math.min(page,pages-1);rows.forEach(r=>r.hidden=true);visible.slice(page*30,page*30+30).forEach(r=>r.hidden=false);const label=document.querySelector('[data-page]');if(label)label.textContent=`${visible.length} 篇 · 第 ${page+1} / ${pages} 页`;}
 search?.addEventListener('input',()=>{page=0;update()});filter?.addEventListener('change',()=>{page=0;update()});document.querySelector('[data-prev]')?.addEventListener('click',()=>{page=Math.max(0,page-1);update()});document.querySelector('[data-next]')?.addEventListener('click',()=>{page++;update()});if(rows.length)update();
});
