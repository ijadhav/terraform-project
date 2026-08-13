(function () {
  const toggle = document.querySelector('[data-mode-toggle]');
  if (!toggle) return;

  const links = Array.from(toggle.querySelectorAll('a[href]'));

  links.forEach((link) => {
    link.addEventListener('click', (event) => {
      const href = link.getAttribute('href');
      const mode = link.getAttribute('data-mode');

      if (!href || !mode || link.classList.contains('active')) {
        return;
      }

      event.preventDefault();
      toggle.setAttribute('data-active-mode', mode);
      document.body.classList.add('page-transition-out');

      window.setTimeout(() => {
        window.location.assign(href);
      }, 170);
    });
  });
})();
