'use strict';

// Override landscape banner with a CSS gradient instead of an image
hexo.extend.injector.register('head_end', () => {
  return `<style>
#banner {
  background: linear-gradient(to bottom, #0a0814 0%, #4a1535 100%) !important;
}
</style>
<script>
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.main-nav-link').forEach(function(a) {
    if (['Home', 'Archives'].includes(a.textContent.trim())) a.remove();
  });
});
</script>`;
});
