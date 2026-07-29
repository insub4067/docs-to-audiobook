import asyncio
import os
import sys

from main import generate_default_book, default_book_state, default_book_paths

async def main():
    print("Starting generation...")
    # Delete existing to force generation
    audio_path, meta_path = default_book_paths()
    if os.path.exists(audio_path): os.remove(audio_path)
    if os.path.exists(meta_path): os.remove(meta_path)
    
    await generate_default_book()
    print("State:", default_book_state)

if __name__ == "__main__":
    asyncio.run(main())
