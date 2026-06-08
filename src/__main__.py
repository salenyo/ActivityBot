import sys
sys.dont_write_bytecode = True

import asyncio

from .bot import run

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
