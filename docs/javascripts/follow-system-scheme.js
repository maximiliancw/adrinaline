// The site has no theme toggle: always follow the OS colour scheme, on load and
// on live changes. Without this the theme reuses the scheme stored on an earlier
// visit, while the README banner's <picture> follows the OS.
(() => {
  const dark = window.matchMedia("(prefers-color-scheme: dark)");
  const apply = () => {
    document.body.setAttribute("data-md-color-scheme", dark.matches ? "slate" : "default");
    if (typeof __md_set === "function") __md_set("__palette", null);
  };
  apply();
  dark.addEventListener("change", apply);
})();
