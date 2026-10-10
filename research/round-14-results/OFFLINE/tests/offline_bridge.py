"""Chromium offline, but local Birge remains available (Internet is forbidden).

DevTools offline also disconnects loopback. We explicitly bridge only the chosen
localhost origin through APIRequestContext, without cached responses or mocks.
"""
import asyncio
from urllib.parse import urlsplit

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
