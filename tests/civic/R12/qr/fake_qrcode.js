/* ТЕСТОВАЯ ЗАГЛУШКА генератора QR для стенда R12 — НЕ настоящий QR-код и НЕ qrcode-generator.
 * Тот же интерфейс, что у qrcode-generator 1.4.4 (Kazuhiko Arase): qrcode(type, ecl) -> {addData, make, getModuleCount, isDark}.
 * Узор зависит от текста (чтобы тест видел, что код строится из ссылки), но сканер его не прочитает.
 * Настоящий файл кладёт LOCAL-11 в web/vendor/qrcode/qrcode.js. */
window.qrcode = function () {
  var text = "", n = 29;
  return {
    addData: function (s) { text += s; },
    make: function () {},
    getModuleCount: function () { return n; },
    isDark: function (r, c) {
      var finder = function (a, b) { return a < 7 && b < 7 && (a === 0 || a === 6 || b === 0 || b === 6 || (a > 1 && a < 5 && b > 1 && b < 5)); };
      if (finder(r, c) || finder(r, n - 1 - c) || finder(n - 1 - r, c)) return true;
      var code = text.charCodeAt((r * n + c) % Math.max(1, text.length)) || 0;
      return ((code + r * 7 + c * 13) % 3) === 0;
    },
  };
};
window.qrcode.__fake = true;
