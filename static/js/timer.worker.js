// Web Worker - runs in background thread, never throttled
let interval = null;

self.onmessage = function(e) {
  const { type } = e.data;
  if (type === 'start') {
    clearInterval(interval);
    interval = setInterval(() => {
      self.postMessage({ type: 'tick' });
    }, 1000);
  } else if (type === 'stop') {
    clearInterval(interval);
    interval = null;
  }
};
