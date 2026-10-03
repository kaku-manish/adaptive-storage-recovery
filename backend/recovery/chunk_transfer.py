import httpx
import hashlib
import asyncio

async def stream_transfer(source_url: str, dest_url: str, block_id: str, token_bucket, chunk_size: int = 1024 * 1024):
    """
    Streams a block from source to destination in chunks of chunk_size.
    Returns (size_bytes, checksum).
    """
    hasher = hashlib.sha256()
    size_bytes = 0
    
    async def chunk_generator():
        nonlocal size_bytes
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("GET", f"{source_url}/blocks/{block_id}") as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size):
                    await token_bucket.consume(len(chunk))
                    hasher.update(chunk)
                    size_bytes += len(chunk)
                    yield chunk

    async with httpx.AsyncClient(timeout=60.0) as dest_client:
        resp = await dest_client.post(f"{dest_url}/blocks/{block_id}", content=chunk_generator())
        resp.raise_for_status()
        
    return size_bytes, hasher.hexdigest()
