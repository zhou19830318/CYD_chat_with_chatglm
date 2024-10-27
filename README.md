# CYD_chat_with_chatglm
chat with chatglm on CYD


Asynchronous HTTP Client/Server for asyncio and Python.
https://docs.aiohttp.org/en/stable/

Streaming Response Content
While methods read(), json() and text() are very convenient you should use them carefully. All these methods load the whole response in memory. For example if you want to download several gigabyte sized files, these methods will load all the data in memory. Instead you can use the content attribute. It is an instance of the aiohttp.StreamReader class. The gzip and deflate transfer-encodings are automatically decoded for you:
'''python
async with session.get('https://api.github.com/events') as resp:
    await resp.content.read(10)
In general, however, you should use a pattern like this to save what is being streamed to a file:
'''python
with open(filename, 'wb') as fd:
    async for chunk in resp.content.iter_chunked(chunk_size):
        fd.write(chunk)
It is not possible to use read(), json() and text() after explicit reading from content.
