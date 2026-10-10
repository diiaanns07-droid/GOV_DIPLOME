"""Chromium offline, but local Birge remains available (Internet is forbidden).

DevTools offline also disconnects loopback. We explicitly bridge only the chosen
localhost origin through APIRequestContext, without cached responses or mocks.
"""
import asyncio
import time
from urllib.parse import urlsplit

async def wait_js(page, expression, timeout=45000):
    # Playwright wait_for_function uses eval in the page. R15 correctly forbids
    # unsafe-eval; poll via DevTools evaluate without disabling the app's CSP.
    deadline=time.monotonic()+timeout/1000
    while time.monotonic()<deadline:
        if await page.evaluate(expression):return
        await asyncio.sleep(0.1)
    raise TimeoutError('Condition timed out: '+expression)

async def install_bridge(context, origin, network, *, offline=True):
    limit=asyncio.Semaphore(4)
    await context.set_offline(offline)
    async def handle(route):
        req=route.request
        parsed=urlsplit(req.url)
        if parsed.scheme+'://'+parsed.netloc != origin:
            network.append({'url':req.url,'blocked':True})
            await route.abort('internetdisconnected')
            return
        async with limit:
            try:
                response=await context.request.fetch(req,timeout=60000,max_retries=2)
                network.append({'url':req.url,'method':req.method,'status':response.status,'range':req.headers.get('range')})
                await route.fulfill(response=response)
            except Exception as e:
                # Do not log request headers, cookies, bodies or local passwords.
                network.append({'url':req.url,'error':str(e).split('\n')[0]})
                try:await route.abort()
                except Exception:pass
    await context.route('**/*',handle)
