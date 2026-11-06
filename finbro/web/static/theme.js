/* Tryb jasny i ciemny: wybór użytkownika z localStorage, a bez wyboru ustawienie systemu.
   Skrypt ładowany w <head> bez defer, żeby strona nie mignęła w złym trybie. */
(function () {
  const KEY = "finbro-theme";
  const root = document.documentElement;
  const system = window.matchMedia("(prefers-color-scheme: dark)");

  function showToggle(theme) {
    const button = document.getElementById("theme-toggle");
    if (!button) { return; }
    const next = theme === "dark" ? "jasny" : "ciemny";
    button.querySelector(".theme-icon").textContent = theme === "dark" ? "☀" : "☾";
    button.querySelector(".theme-label").textContent = "Tryb " + next;
    button.setAttribute("aria-label", "Włącz tryb " + next);
  }

  function apply(theme) {
    root.dataset.theme = theme;
    showToggle(theme);
    document.dispatchEvent(new CustomEvent("finbro-theme"));
  }

  apply(localStorage.getItem(KEY) || (system.matches ? "dark" : "light"));

  system.addEventListener("change", function (event) {
    if (!localStorage.getItem(KEY)) { apply(event.matches ? "dark" : "light"); }
  });

  document.addEventListener("DOMContentLoaded", function () {
    showToggle(root.dataset.theme);
    document.getElementById("theme-toggle").addEventListener("click", function () {
      const theme = root.dataset.theme === "dark" ? "light" : "dark";
      localStorage.setItem(KEY, theme);
      apply(theme);
    });
  });
})();
