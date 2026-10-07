/* Contract mock of R01 api.request for the R03 stand and browser tests.
 * Implements only the public civic-v1 reads: GET /objects[?cursor=] and GET /objects/{id}.
 * It is NOT the R02 backend. Anything else answers 404/405 like the contract says.
 */
(function () {
  "use strict";
  function createMockApi(opts) {
    const o = Object.assign({ items: [], history: {}, pageSize: 5, delay: 80, failList: 0, failCard: 0, slow: {}, status: 500 }, opts || {});
    const calls = [];
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const err = (status, code, message) => Object.assign(new Error(message), { status, code });
    // leakDrafts simulates a buggy backend so the module's own publication guard is tested.
    const published = () => o.items.filter((x) => o.leakDrafts || x.publication === "published");
    async function request(method, path, body) {
      calls.push({ method, path, body: body === undefined ? null : body, at: Date.now() });
      const url = new URL(path, "http://mock.invalid");
      const delay = o.slow[url.pathname] != null ? o.slow[url.pathname] : o.delay;
      // The answer is computed when the request arrives, then delayed: a slow old
      // response carries old data, which is what stale-response tests need.
      let result, failure;
      try { result = answer(method, url, body); } catch (e) { failure = e; }
      await wait(delay);
      if (failure) throw failure;
      return result;
    }
    function answer(method, url) {
      if (method !== "GET") throw err(405, "method_not_allowed", "Публичная карта только читает");
      if (url.pathname.startsWith("/staff")) throw err(401, "unauthenticated", "staff endpoint");
      if (url.pathname === "/objects") {
        if (o.failList > 0) { o.failList--; throw err(o.status, "server_error", "Internal error"); }
        const all = published();
        const start = Number(url.searchParams.get("cursor") || 0);
        const page = all.slice(start, start + o.pageSize);
        const next = start + o.pageSize < all.length ? String(start + o.pageSize) : null;
        return { items: JSON.parse(JSON.stringify(page)), next_cursor: next };
      }
      const m = /^\/objects\/([^/]+)$/.exec(url.pathname);
      if (m) {
        if (o.failCard > 0) { o.failCard--; throw err(o.status, "server_error", "Internal error"); }
        const id = decodeURIComponent(m[1]);
        const item = published().find((x) => x.id === id);
        if (!item) throw err(404, "not_found", "Объект не найден");
        return { item: JSON.parse(JSON.stringify(item)), history: JSON.parse(JSON.stringify(o.history[id] || [])) };
      }
      throw err(404, "not_found", "unknown path");
    }
    return { request, calls, options: o };
  }
  window.R03CreateMockApi = createMockApi;
})();
