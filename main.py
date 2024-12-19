from fastapi import FastAPI, WebSocket, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import yt_dlp
import os
import json
import asyncio
from pathlib import Path
import humanize

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 配置静态文件和下载目录
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# 存储下载进度的字典
download_progress = {}

class VideoDownloader:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        
    async def hook(self, d):
        if d['status'] == 'downloading':
            progress = {
                'status': 'downloading',
                'downloaded_bytes': d.get('downloaded_bytes', 0),
                'total_bytes': d.get('total_bytes', 0),
                'speed': d.get('speed', 0),
                'eta': d.get('eta', 0),
                'filename': d.get('filename', '')
            }
            await self.websocket.send_json(progress)
        elif d['status'] == 'finished':
            await self.websocket.send_json({'status': 'finished'})

@app.get("/")
async def home(request: Request):
    # 获取已下载视频列表
    videos = []
    for video_file in DOWNLOAD_DIR.glob("*.mp4"):
        info_file = video_file.with_suffix('.info.json')
        if info_file.exists():
            with open(info_file, 'r', encoding='utf-8') as f:
                info = json.load(f)
                videos.append({
                    'title': info.get('title', '未知标题'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', '未知作者'),
                    'description': info.get('description', '无描述'),
                    'filesize': humanize.naturalsize(video_file.stat().st_size),
                    'filepath': f"/downloads/{video_file.name}",
                })
    
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "videos": videos}
    )

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        while True:
            url = await websocket.receive_text()
            downloader = VideoDownloader(websocket)
            
            ydl_opts = {
                'format': 'best',
                'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
                'progress_hooks': [downloader.hook],
                'writeinfojson': True,
            }
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    await asyncio.to_thread(ydl.download, [url])
            except Exception as e:
                await websocket.send_json({
                    'status': 'error',
                    'message': str(e)
                })
                
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 