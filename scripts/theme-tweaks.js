'use strict';

// Override landscape banner with a CSS gradient instead of an image
hexo.extend.injector.register('head_end', () => {
  return `<style>
#banner {
  background: linear-gradient(135deg, #1c1c2e 0%, #4a0e2e 100%) !important;
}
</style>`;
});
