(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  /* toast */
  function toast(msg, icon) {
    const stack = $('#toastStack');
    const el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = '<i class="fa-solid ' + (icon || 'fa-circle-check') + '"></i> ' + msg;
    stack.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 400); }, 2800);
  }
  window.mxToast = toast;
  $$('#djMessages .toast').forEach((t, i) => setTimeout(() => t.classList.remove('show'), 3600 + i * 300));

  /* announcement rotator */
  const bar = $('#announceBar');
  if (bar) {
    const msgs = JSON.parse(bar.dataset.messages || '[]');
    let i = 0;
    const paint = () => {
      if (!msgs.length) return;
      bar.innerHTML = '<span>' + msgs[i] + '</span>';
      i = (i + 1) % msgs.length;
    };
    paint();
    setInterval(paint, 3400);
  }

  /* sticky header shadow */
  const hdr = $('.site-header');
  addEventListener('scroll', () => hdr.classList.toggle('scrolled', scrollY > 10), { passive: true });

  /* profile popup */
  const profileToggle = $('#profileToggle'), profileOverlay = $('#profileOverlay'), profileClose = $('#profileClose');
  const closeProfile = () => { if (profileOverlay) profileOverlay.hidden = true; profileToggle?.setAttribute('aria-expanded', 'false'); };
  profileToggle?.addEventListener('click', () => {
    if (!profileOverlay) return;
    profileOverlay.hidden = !profileOverlay.hidden;
    profileToggle.setAttribute('aria-expanded', String(!profileOverlay.hidden));
  });
  profileClose?.addEventListener('click', closeProfile);
  profileOverlay?.addEventListener('click', e => { if (e.target === profileOverlay) closeProfile(); });
  addEventListener('keydown', e => { if (e.key === 'Escape') closeProfile(); });
  profileToggle?.addEventListener('click', () => {
    if (!profileOverlay.hidden) profileClose?.focus();
  });

  /* mobile nav */
  $('#hamburgerBtn')?.addEventListener('click', () => $('#mobileNav').classList.add('open'));
  $('#mobileNavClose')?.addEventListener('click', () => $('#mobileNav').classList.remove('open'));
  $$('#mobileNav a').forEach(a => a.addEventListener('click', () => $('#mobileNav').classList.remove('open')));

  /* Cart back button with a shop fallback for direct visits. */
  $('[data-history-back]')?.addEventListener('click', event => {
    if (history.length > 1) {
      event.preventDefault();
      history.back();
    }
  });

  /* Footer actions appear at the footer, keeping WhatsApp clear of its bottom. */
  const footer = $('.site-footer'), wa = $('.wa-float');
  if (footer && wa && 'IntersectionObserver' in window) {
    const footerObserver = new IntersectionObserver(([entry]) => {
      const atFooter = entry.isIntersecting;
      footer.classList.toggle('footer-reached', atFooter);
    }, { threshold: 0.01 });
    footerObserver.observe(footer);
  }

  /* live search */
  const panel = $('#searchPanel'), input = $('#siteSearchInput'), results = $('#searchResults');
  const closeSearch = () => { panel.classList.remove('open'); results.innerHTML = ''; input.value = ''; };
  $('#searchToggle')?.addEventListener('click', () => { panel.classList.contains('open') ? closeSearch() : (panel.classList.add('open'), setTimeout(() => input.focus(), 60)); });
  $('#searchClose')?.addEventListener('click', closeSearch);
  addEventListener('keydown', e => { if (e.key === 'Escape') closeSearch(); });
  let t;
  input?.addEventListener('input', () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      const q = input.value.trim();
      if (!q) { results.innerHTML = ''; return; }
      const r = await fetch(panel.dataset.url + '?q=' + encodeURIComponent(q));
      const d = await r.json();
      results.innerHTML = d.results.length ? d.results.map(p =>
        '<a class="search-hit" href="' + p.url + '"><img src="' + p.image + '" alt=""><div><div style="font-weight:600">' + p.name + '</div><div style="font-size:.78rem;color:#b9b8b0">' + p.category + ' · Rs. ' + p.price.toLocaleString() + '</div></div></a>'
      ).join('') : '<p style="color:#b9b8b0;padding:14px 0">No products found.</p>';
    }, 200);
  });

  /* reveal on scroll */
  const io = 'IntersectionObserver' in window ? new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: 0.1 }) : null;
  $$('.reveal').forEach((el, i) => { el.style.transitionDelay = (i % 4) * 70 + 'ms'; io ? io.observe(el) : el.classList.add('in'); });

  /* ajax add to cart */
  $$('form[data-ajax-add]').forEach(f => f.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = $('button', f), old = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Adding';
    try {
      const r = await fetch(f.action, { method: 'POST', body: new FormData(f), headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      const d = await r.json();
      if (!d.ok) { btn.disabled = false; btn.innerHTML = old; toast(d.message || 'Could not add this item', 'fa-circle-exclamation'); return; }
      const c = $('#cartCount'); c.textContent = d.count; c.style.display = 'flex';
      c.classList.remove('bump'); void c.offsetWidth; c.classList.add('bump');
      btn.innerHTML = '<i class="fa-solid fa-check"></i> Added'; toast('Added to your cart');
    } catch (err) { f.submit(); return; }
    setTimeout(() => { btn.disabled = false; btn.innerHTML = old; }, 1200);
  }));

  /* Guest wishlists stay local; signed-in wishlists sync to the account. */
  const wl = JSON.parse(localStorage.getItem('mxWish') || '[]');
  const accountWishlist = document.body.dataset.authenticated === 'true';
  const csrfToken = () => document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1] || '';
  const paintWish = (button, active) => {
    button.classList.toggle('active', active);
    button.dataset.wishActive = String(active);
    button.setAttribute('aria-pressed', String(active));
    if (button.firstElementChild) button.firstElementChild.className = (active ? 'fa-solid' : 'fa-regular') + ' fa-heart';
  };
  $$('[data-wish]').forEach(b => {
    const id = b.dataset.wish;
    if (accountWishlist) paintWish(b, b.dataset.wishActive === 'true');
    else paintWish(b, wl.includes(id));
    b.addEventListener('click', async e => {
      e.preventDefault();
      if (accountWishlist) {
        try {
          const response = await fetch(b.dataset.wishUrl, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfToken() } });
          const result = await response.json();
          if (!result.ok) throw new Error(result.message || 'Could not update wishlist');
          paintWish(b, result.in_wishlist);
        } catch (error) { toast('Could not update wishlist. Please try again.', 'fa-circle-exclamation'); }
        return;
      }
      const i = wl.indexOf(id);
      if (i > -1) wl.splice(i, 1); else wl.push(id);
      localStorage.setItem('mxWish', JSON.stringify(wl));
      paintWish(b, i === -1);
    });
  });
  if (accountWishlist && wl.length) {
    fetch(document.body.dataset.wishlistMergeUrl, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify({ ids: wl }),
    }).then(response => response.json()).then(result => {
      if (!result.ok) return;
      const mergedIds = new Set(result.ids.map(String));
      $$('[data-wish]').forEach(button => paintWish(button, mergedIds.has(button.dataset.wish)));
      localStorage.removeItem('mxWish');
    }).catch(() => {});
  }

  /* newsletter */
  $$('form[data-newsletter]').forEach(f => f.addEventListener('submit', async e => {
    e.preventDefault();
    const note = f.parentElement.querySelector('.note');
    const r = await fetch(f.action, { method: 'POST', body: new FormData(f), headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    const d = await r.json(); note.textContent = d.message; if (d.ok) f.reset();
  }));

  /* hero carousel */
  const hero = $('#heroCarousel');
  if (hero) {
    const slides = $$('.hero-slide', hero), dots = $('#heroDots');
    let idx = 0, timer;
    slides.forEach((_, i) => { const b = document.createElement('button'); b.setAttribute('aria-label', 'Slide ' + (i + 1)); if (!i) b.className = 'active'; b.onclick = () => go(i); dots.appendChild(b); });
    function go(i) { slides[idx].classList.remove('active'); dots.children[idx].classList.remove('active'); idx = (i + slides.length) % slides.length; slides[idx].classList.add('active'); dots.children[idx].classList.add('active'); }
    const start = () => { timer = setInterval(() => go(idx + 1), 6000); }, stop = () => clearInterval(timer);
    hero.addEventListener('mouseenter', stop); hero.addEventListener('mouseleave', start);
    $('.hero-prev').onclick = () => go(idx - 1); $('.hero-next').onclick = () => go(idx + 1); start();
  }
})();
