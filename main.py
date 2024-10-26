import aiohttp
import uasyncio as asyncio
import network
import time
import ujson as json
from ili9341 import Display, color565
from machine import Pin, SPI
from xglcd_font import XglcdFont
import gc


# Display parameters
SCREEN_WIDTH = 239
SCREEN_HEIGHT = 319
ROTATION = 90 #0&180(W320-L240),90&270(W240-L320)
CHAR_WIDTH = 9
CHAR_HEIGHT = 19
MAX_CHARS_PER_LINE = (SCREEN_WIDTH + 1) // CHAR_WIDTH
BUFFER_SIZE = 1024
FONTS_NAME = '黑体9x19.c'

# Display initialization
spi = SPI(1, baudrate=40000000, sck=Pin(14), mosi=Pin(13))
display = Display(spi, dc=Pin(2), cs=Pin(15), rst=Pin(21), width=(SCREEN_HEIGHT+1), height=(SCREEN_WIDTH+1), rotation=ROTATION)
print('Loading fonts...')
print(f'Loading {FONTS_NAME}')
unispace = XglcdFont(FONTS_NAME, CHAR_WIDTH, CHAR_HEIGHT)
print('Fonts loaded.')


class MessageQueue:
    def __init__(self, maxsize=BUFFER_SIZE):
        self.queue = []
        self.maxsize = maxsize
        self._lock = asyncio.Lock()

    async def put(self, item):
        async with self._lock:
            if len(self.queue) >= self.maxsize:
                self.queue.pop(0)
            self.queue.append(item)

    async def get(self):
        async with self._lock:
            return self.queue.pop(0) if self.queue else None

    def empty(self):
        return len(self.queue) == 0

class TextDisplay:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.MAX_X = SCREEN_HEIGHT
        self.MAX_Y = SCREEN_WIDTH
        self.message_queue = MessageQueue()
        self.running = True
        self._display_task = asyncio.create_task(self._display_task())
        self._page_lock = asyncio.Lock()  # 添加页面锁

    async def _display_task(self):
        while self.running:
            char = await self.message_queue.get()
            if char:
                await self._write_char(char)
            await asyncio.sleep_ms(1)

    async def write_text(self, text):
        for char in text:
            await self.message_queue.put(char)

    async def _write_char(self, char):
        async with self._page_lock:  # 使用锁保护页面操作
            if char in ['\n', '\r']:
                self.x = 0
                self.y += CHAR_HEIGHT
                if self.y + CHAR_HEIGHT > self.MAX_Y:
                    await self._new_page()
                return

            if self.x + CHAR_WIDTH > self.MAX_X:
                self.x = 0
                self.y += CHAR_HEIGHT
                if self.y + CHAR_HEIGHT > self.MAX_Y:
                    await self._new_page()

            if 0 <= self.x <= self.MAX_X and 0 <= self.y <= self.MAX_Y:
                try:
                    display.draw_text(self.x, self.y, char, unispace, color565(255, 255, 0))
                    self.x += CHAR_WIDTH
                except Exception as e:
                    print(f"Display error: {e}")

    async def _new_page(self):
        """处理新页面"""
        self.y = 0
        self.x = 0
        # 添加短暂延时确保清屏前阅读完成
        await asyncio.sleep_ms(1000)
        display.clear()


    async def flush(self):
        """确保所有队列中的字符都被显示"""
        while self.message_queue.queue:
            await asyncio.sleep_ms(10)

    async def close(self):
        """关闭显示任务"""
        self.running = False
        await self.flush()
        self._display_task.cancel()  # 正确取消任务
        try:
            await self._display_task
        except asyncio.CancelledError:
            pass

async def process_response(response, text_display):
    buffer = ""
    try:
        while True:
            chunk = await response.content.read(BUFFER_SIZE)
            if not chunk:
                # 处理buffer中剩余的内容
                if buffer:
                    if buffer.startswith('data: '):
                        try:
                            data = buffer[6:]
                            if data != "[DONE]":
                                parsed = json.loads(data)
                                content = parsed['choices'][0]['delta'].get('content', '')
                                if content:
                                    await text_display.write_text(content)
                        except Exception as e:
                            print(f"Process remaining buffer error: {e}")
                break
                
            buffer += chunk.decode()
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if line.startswith('data: '):
                    try:
                        data = line[6:]
                        if data == "[DONE]":
                            return
                        parsed = json.loads(data)
                        content = parsed['choices'][0]['delta'].get('content', '')
                        if content:
                            await text_display.write_text(content)
                            #print(content)
                    except Exception as e:
                        print(f"Process error: {e}")
                        continue
            await asyncio.sleep_ms(1)
            gc.collect()
    finally:
        # 确保消息队列中的所有字符都被显示
        await asyncio.sleep_ms(100)

async def main(message):
    API_KEY = "xxxxxx" #replace by your chatglm api key
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    payload = {
        "model": "glm-4-flash",
        "messages": [{"role": "user", "content": message}],
        "temperature": 0.7,
        "top_p": 1,
        "n": 1,
        "stream": True,
        "max_tokens": BUFFER_SIZE,
        "presence_penalty": 0,
        "frequency_penalty": 0
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {API_KEY}'
    }

    text_display = TextDisplay()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                await process_response(response, text_display)
                # 确保所有内容都显示完毕
                await text_display.flush()
    except Exception as e:
        print(f"Connection error: {e}")
        await text_display.write_text('Connection error')
    finally:
        await text_display.close()
        gc.collect()

async def connect_wifi_async(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if not wlan.isconnected():
        print('Connecting to network...')
        wlan.connect(ssid, password)
        
        for _ in range(10):
            if wlan.isconnected():
                print('Network connected successfully')
                print('Network config:', wlan.ifconfig())
                return True
            await asyncio.sleep_ms(1000)
    
    return wlan.isconnected()

async def main_loop():
    ssid = 'ssid' #replace by your ssid
    password = 'pwd' #replace by your ssid
    
    if not await connect_wifi_async(ssid, password):
        print("WiFi connection failed")
        return
        
    while True:
        try:
            user_input = input("\nEnter your questions:->")
            display.clear()
            await main(user_input)
        except Exception as e:
            print(f"Error in main loop: {e}")
        await asyncio.sleep_ms(100)
        gc.collect()

if __name__ == '__main__':
    while True:
        try:
            gc.enable()
            asyncio.run(main_loop())
        except KeyboardInterrupt:
            print("\nProgram terminated by user")
        except Exception as e:
            print(f"Fatal error: {e}")
        finally:
            display.clear()

