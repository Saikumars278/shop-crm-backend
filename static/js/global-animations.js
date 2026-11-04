/**
 * Universal YouTube-Style Animation & Progress System
 * Global integration for Django & CRM interfaces
 */
(function () {
  "use strict";

  let progress = 0;
  let activeRequests = 0;
  let trickleInterval = null;
  let finishTimer = null;
  let resetTimer = null;
  let safetyTimer = null;

  // DOM Elements
  let container = null;
  let bar = null;

  // Ensure DOM container and progress bar exist
  function ensureBarElements() {
    if (container && bar) return;

    container = document.getElementById("yt-progress-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "yt-progress-container";
      container.setAttribute("role", "progressbar");
      container.setAttribute("aria-valuemin", "0");
      container.setAttribute("aria-valuemax", "100");
      container.setAttribute("aria-valuenow", "0");

      bar = document.createElement("div");
      bar.id = "yt-progress-bar";
      container.appendChild(bar);

      if (document.body) {
        document.body.prepend(container);
      } else {
        document.addEventListener("DOMContentLoaded", () => {
          document.body.prepend(container);
        });
      }
    } else {
      bar = document.getElementById("yt-progress-bar");
    }
  }

  function setProgress(val) {
    ensureBarElements();
    progress = Math.max(0, Math.min(100, val));
    if (bar) {
      bar.style.width = progress + "%";
    }
    if (container) {
      container.setAttribute("aria-valuenow", String(progress));
    }
  }

  function stopTrickle() {
    if (trickleInterval) {
      clearInterval(trickleInterval);
      trickleInterval = null;
    }
  }

  function clearSafetyTimeout() {
    if (safetyTimer) {
      clearTimeout(safetyTimer);
      safetyTimer = null;
    }
  }

  function start() {
    ensureBarElements();
    if (!container) return;

    if (finishTimer) clearTimeout(finishTimer);
    if (resetTimer) clearTimeout(resetTimer);

    container.classList.add("is-active");

    if (progress === 0 || progress === 100) {
      setProgress(24);
    }

    if (!trickleInterval) {
      trickleInterval = setInterval(() => {
        if (progress < 40) {
          setProgress(progress + 6);
        } else if (progress < 70) {
          setProgress(progress + 3);
        } else if (progress < 88) {
          setProgress(progress + 1);
        }
      }, 250);
    }

    clearSafetyTimeout();
    safetyTimer = setTimeout(() => {
      done();
    }, 9000);
  }

  function done() {
    stopTrickle();
    clearSafetyTimeout();

    // Remove is-refreshing class from any spinning icons/buttons
    document.querySelectorAll(".is-refreshing").forEach((el) => {
      el.classList.remove("is-refreshing");
    });

    setProgress(100);

    if (finishTimer) clearTimeout(finishTimer);
    finishTimer = setTimeout(() => {
      if (container) {
        container.classList.remove("is-active");
      }

      if (resetTimer) clearTimeout(resetTimer);
      resetTimer = setTimeout(() => {
        setProgress(0);
        activeRequests = 0;
      }, 300);
    }, 200);
  }

  function increment() {
    activeRequests += 1;
    start();
  }

  function decrement() {
    activeRequests = Math.max(0, activeRequests - 1);
    if (activeRequests === 0) {
      done();
    }
  }

  // Expose global controller
  window.YouTubeLoader = {
    start: start,
    done: done,
    set: setProgress,
    increment: increment,
    decrement: decrement,
  };

  // Custom Event Listeners
  window.addEventListener("yt-loader-start", start);
  window.addEventListener("yt-loader-done", done);

  // 1. Intercept Fetch API
  if (window.fetch) {
    const originalFetch = window.fetch;
    window.fetch = async function (...args) {
      increment();
      try {
        const response = await originalFetch.apply(this, args);
        return response;
      } finally {
        decrement();
      }
    };
  }

  // 2. Intercept XMLHttpRequest
  if (window.XMLHttpRequest) {
    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (...args) {
      return originalOpen.apply(this, args);
    };

    XMLHttpRequest.prototype.send = function (...args) {
      increment();
      const onEnd = () => {
        decrement();
        this.removeEventListener("loadend", onEnd);
      };
      this.addEventListener("loadend", onEnd);
      return originalSend.apply(this, args);
    };
  }

  // 3. Intercept Link Clicks for Instant Navigation Feedback
  document.addEventListener(
    "click",
    function (e) {
      const anchor = e.target.closest("a");
      if (!anchor) return;

      const href = anchor.getAttribute("href");
      if (
        !href ||
        href.startsWith("#") ||
        href.startsWith("javascript:") ||
        href.startsWith("mailto:") ||
        href.startsWith("tel:") ||
        anchor.getAttribute("target") === "_blank" ||
        anchor.hasAttribute("download")
      ) {
        return;
      }

      const currentPath = window.location.pathname + window.location.search;
      if (href !== currentPath) {
        start();
      }
    },
    true
  );

  // 4. Intercept Form Submissions
  document.addEventListener(
    "submit",
    function () {
      increment();
      setTimeout(decrement, 2500); // safety fallback for full page reloads
    },
    true
  );

  // 5. Intercept Buttons & Refresh Triggers
  document.addEventListener(
    "click",
    function (e) {
      const btn = e.target.closest("button, [role='button'], input[type='submit']");
      if (!btn) return;

      const text = (btn.textContent || "").toLowerCase();
      const label = (btn.getAttribute("aria-label") || "").toLowerCase();
      const title = (btn.getAttribute("title") || "").toLowerCase();
      const className = (btn.className || "").toString().toLowerCase();

      const isRefresh =
        text.includes("refresh") ||
        label.includes("refresh") ||
        title.includes("refresh") ||
        className.includes("refresh") ||
        Boolean(btn.querySelector("svg, i, .icon, [data-icon*='refresh']"));

      if (isRefresh) {
        btn.classList.add("is-refreshing");
        start();
      } else if (btn.getAttribute("type") === "submit" || btn.getAttribute("data-loading") === "true") {
        start();
      }
    },
    true
  );

  // Auto-complete on DOM ready and Page Show (e.g. Back/Forward cache)
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      ensureBarElements();
      done();
    });
  } else {
    ensureBarElements();
  }

  window.addEventListener("pageshow", function () {
    done();
  });
})();

