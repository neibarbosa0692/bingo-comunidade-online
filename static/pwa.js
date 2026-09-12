(function(){
  if ('serviceWorker' in navigator && window.isSecureContext) {
    window.addEventListener('load', function(){
      navigator.serviceWorker.register('/sw.js', {scope:'/'}).catch(function(err){
        console.warn('PWA: service worker não registrado', err);
      });
    });
  }
  let deferredPrompt = null;
  window.addEventListener('beforeinstallprompt', function(e){
    e.preventDefault();
    deferredPrompt = e;
    document.documentElement.classList.add('pwa-install-available');
  });
  window.addEventListener('appinstalled', function(){
    deferredPrompt = null;
    document.documentElement.classList.remove('pwa-install-available');
  });
  window.BingoPWA = {
    install: async function(){
      if (!deferredPrompt) return false;
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
      document.documentElement.classList.remove('pwa-install-available');
      return true;
    }
  };
})();
