import signal
import asyncio
import logging
from aiohttp import web

logging.basicConfig(level=logging.INFO)

ADDRESS = '0.0.0.0'
PORT = 80

async def main(loop):
    """
    This coroutine initiates our server as subsequent asyncio.Tasks on 
    the event loop. It is safe to let this coroutine die in a loop that's running
    forever. 
    """
    runner = web.ServerRunner(web.Server(handler))
    await runner.setup()
    site = web.TCPSite(runner, ADDRESS, PORT)
    await site.start()

async def handler(request):
    """
    Handle all requests as deemed necessary. 
    """

    logging.info("Received a request!")
    # this is just a placeholder for now. You can hit this at localhost:80 if you run the Makefile. 
    # We need to expand this to something more complicated that can handle proxying.
    return web.Response(text="OK")

if __name__ == '__main__':

    loop = asyncio.get_event_loop()
    loop.create_task(main(loop))
    logging.info("Initialized Qbox! Now serving...")

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.stop()
        loop.close()