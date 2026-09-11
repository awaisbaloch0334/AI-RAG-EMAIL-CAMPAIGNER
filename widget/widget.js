/**
 * Embeddable RAG Chatbot Widget Loader
 * Usage:
 *   <script src="https://YOUR-DOMAIN.com/static/widget.js" data-bot-id="YOUR_BOT_ID"></script>
 */
(function () {
  if (window.__RAG_WIDGET_LOADED__) return;
  window.__RAG_WIDGET_LOADED__ = true;

  // 1. Discover Script Configuration (prioritizes latest injected script)
  const currentScript =
    document.currentScript ||
    (function () {
      const scripts = document.querySelectorAll("script[data-bot-id]");
      return scripts.length > 0 ? scripts[scripts.length - 1] : null;
    })();

  if (!currentScript) {
    console.error("[RAG Widget] No script element found with 'data-bot-id' attribute.");
    return;
  }

  const botId = currentScript.getAttribute("data-bot-id");
  if (!botId) {
    console.error("[RAG Widget] Missing required 'data-bot-id' attribute.");
    return;
  }

  // Derive API host
  let apiHost = currentScript.getAttribute("data-api-host");
  if (!apiHost) {
    try {
      const url = new URL(currentScript.src);
      apiHost = url.origin;
    } catch (e) {
      apiHost = window.location.origin;
    }
  }

  // 2. Fetch Widget Configuration
  fetch(`${apiHost}/api/bots/${botId}/widget-config`)
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then((config) => {
      initWidget(config);
    })
    .catch((err) => {
      console.warn("[RAG Widget] Using fallback branding configuration:", err);
      initWidget({
        bot_id: botId,
        bot_name: "Website Assistant",
        branding: {
          primary_color: "#2563EB",
          position: "bottom-right",
          company_name: "AI Assistant",
        },
      });
    });

  function initWidget(config) {
    const branding = config.branding || {};
    const primaryColor = branding.primary_color || "#2563EB";
    const isLeft = branding.position === "bottom-left";

    // 3. Inject CSS Styles
    const style = document.createElement("style");
    style.id = "rag-widget-styles";
    style.innerHTML = `
      #rag-launcher-btn {
        position: fixed;
        bottom: 24px;
        ${isLeft ? "left: 24px;" : "right: 24px;"}
        width: 60px;
        height: 60px;
        border-radius: 30px;
        background-color: ${primaryColor};
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
        cursor: pointer;
        z-index: 2147483646;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease;
        border: none;
        outline: none;
        user-select: none;
        padding: 0;
      }
      #rag-launcher-btn:hover {
        transform: scale(1.08);
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.25);
      }
      #rag-launcher-btn:active {
        transform: scale(0.95);
      }
      #rag-launcher-btn svg {
        width: 28px;
        height: 28px;
        fill: #ffffff;
        transition: transform 0.2s ease;
      }
      #rag-chat-container {
        position: fixed;
        bottom: 96px;
        ${isLeft ? "left: 24px;" : "right: 24px;"}
        width: 400px;
        height: 620px;
        max-width: calc(100vw - 32px);
        max-height: calc(100vh - 120px);
        z-index: 2147483647;
        box-shadow: 0 16px 48px -4px rgba(0, 0, 0, 0.18), 0 6px 16px -2px rgba(0, 0, 0, 0.08);
        border-radius: 16px;
        overflow: hidden;
        opacity: 0;
        transform: scale(0.92) translateY(24px);
        pointer-events: none;
        transition: opacity 0.22s ease, transform 0.24s cubic-bezier(0.16, 1, 0.3, 1);
        background: transparent;
      }
      #rag-chat-container.rag-open {
        opacity: 1;
        transform: scale(1) translateY(0);
        pointer-events: auto;
      }
      #rag-chat-iframe {
        width: 100%;
        height: 100%;
        border: none;
        display: block;
        background: transparent;
      }
      @media (max-width: 600px) {
        #rag-chat-container {
          bottom: 0 !important;
          left: 0 !important;
          right: 0 !important;
          top: 0 !important;
          width: 100vw !important;
          height: 100vh !important;
          max-width: 100vw !important;
          max-height: 100vh !important;
          border-radius: 0 !important;
        }
      }
    `;
    document.head.appendChild(style);

    // 4. Create Launcher Button
    const launcher = document.createElement("button");
    launcher.id = "rag-launcher-btn";
    launcher.setAttribute("aria-label", "Open Chat Assistant");
    launcher.innerHTML = `
      <svg id="rag-icon-chat" viewBox="0 0 24 24">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
      </svg>
      <svg id="rag-icon-close" viewBox="0 0 24 24" style="display: none;">
        <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
      </svg>
    `;
    document.body.appendChild(launcher);

    // 5. Create Iframe Container
    const container = document.createElement("div");
    container.id = "rag-chat-container";

    const iframe = document.createElement("iframe");
    iframe.id = "rag-chat-iframe";
    iframe.title = `${config.bot_name || "Website"} AI Chatbot`;
    iframe.setAttribute("allow", "clipboard-write");
    iframe.src = `${apiHost}/widget/chat?bot_id=${encodeURIComponent(botId)}&api_host=${encodeURIComponent(apiHost)}&v=${Date.now()}`;
    container.appendChild(iframe);
    document.body.appendChild(container);

    let isOpen = false;

    function setChatOpen(open) {
      isOpen = open;
      const chatIcon = document.getElementById("rag-icon-chat");
      const closeIcon = document.getElementById("rag-icon-close");

      if (isOpen) {
        container.classList.add("rag-open");
        if (chatIcon) chatIcon.style.display = "none";
        if (closeIcon) closeIcon.style.display = "block";
      } else {
        container.classList.remove("rag-open");
        if (chatIcon) chatIcon.style.display = "block";
        if (closeIcon) closeIcon.style.display = "none";
      }
    }

    launcher.addEventListener("click", () => {
      setChatOpen(!isOpen);
    });

    // 6. Expose global controller for host integration
    window.RAGChatWidget = {
      open: () => setChatOpen(true),
      close: () => setChatOpen(false),
      toggle: () => setChatOpen(!isOpen),
      isOpen: () => isOpen,
      botId: botId,
    };

    // 7. Listen for PostMessage from Iframe
    window.addEventListener("message", (event) => {
      if (event.data && event.data.type === "CLOSE_CHAT") {
        setChatOpen(false);
      } else if (event.data && event.data.type === "OPEN_CHAT") {
        setChatOpen(true);
      }
    });
  }
})();

