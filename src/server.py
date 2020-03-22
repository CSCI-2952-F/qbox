import signal
import asyncio
import logging
from aiohttp import web
from configuration import ConfigurationManager

logging.basicConfig(level=logging.INFO)

ADDRESS = "0.0.0.0"
PORT = 3001

configuration = ConfigurationManager().get_config()


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


if __name__ == "__main__":

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
