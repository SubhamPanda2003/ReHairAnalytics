let loadingPromise = null;

/** Loads the Razorpay Checkout script on demand (not in index.html) so
 * visitors who never hit a paywall don't pay for it on every page load.
 * Cached across calls -- repeated buy-button clicks reuse the same script tag. */
export function loadRazorpayScript() {
  if (window.Razorpay) return Promise.resolve(true);
  if (loadingPromise) return loadingPromise;
  loadingPromise = new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve(true);
    script.onerror = () => { loadingPromise = null; resolve(false); };
    document.body.appendChild(script);
  });
  return loadingPromise;
}
