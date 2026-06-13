/*
 * Global mermaid fallback config for diagrams that cannot carry %%{init:...}%%
 * (frozen byte-identical blocks). Runs synchronously and on DOMContentLoaded
 * so it fires before mkdocs-material processes .mermaid divs.
 *
 * Diagrams that DO carry %%{init:...}%% take precedence over this config.
 */
(function () {
  var cfg = {
    startOnLoad: false,
    theme: "base",
    themeVariables: {
      background: "transparent",
      primaryColor: "#3f51b5",
      primaryTextColor: "#ffffff",
      primaryBorderColor: "#283593",
      lineColor: "#7986cb",
      secondaryColor: "#3949ab",
      tertiaryColor: "#5c6bc0",
      clusterBkg: "#e8eaf6",
      clusterBorder: "#7986cb",
      edgeLabelBackground: "#e8eaf6",
      titleColor: "#1a237e",
      nodeTextColor: "#ffffff",
      actorBkg: "#3f51b5",
      actorTextColor: "#ffffff",
      actorBorder: "#283593",
      actorLineColor: "#7986cb",
      signalColor: "#5c6bc0",
      signalTextColor: "#1a237e",
      noteBkgColor: "#e8eaf6",
      noteTextColor: "#1a237e",
    },
  };

  function apply() {
    if (typeof mermaid !== "undefined") {
      mermaid.initialize(cfg);
    }
  }

  apply();
  document.addEventListener("DOMContentLoaded", apply);
})();
