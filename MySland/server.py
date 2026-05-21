#!/usr/bin/env python3
"""
MySland Multiplayer Server v2.0
Поддержка: HTTP API, WebSocket, музыка, иконка, порты
Запуск: python server.py
"""

import asyncio
import json
import os
import re
import secrets
from pathlib import Path
from datetime import datetime

import aiohttp
from aiohttp import web, WSMsgType
import aiohttp_cors

# ========== КОНФИГУРАЦИЯ ==========
HTTP_PORT = 8000
WS_PORT = 8443
USERS_FILE = "users.json"
MUSIC_DIR = "music"  # Папка с музыкальными файлами
HOST = "0.0.0.0"
MAX_MUSIC_FILES = 50  # Максимальное количество проверяемых файлов

# ========== БАЗА ПОЛЬЗОВАТЕЛЕЙ ==========
class UserDatabase:
    def __init__(self, filename):
        self.filename = filename
        self.users = {}
        self.load()
    
    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    self.users = json.load(f)
                print(f"✅ Загружено {len(self.users)} пользователей")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки пользователей: {e}")
                self.users = {}
    
    def save(self):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"⚠️ Ошибка сохранения пользователей: {e}")
            return False
    
    def register(self, nick, password):
        if nick in self.users:
            return False, "Ник уже занят"
        self.users[nick] = {
            "password": password,
            "created": datetime.now().isoformat(),
            "last_login": datetime.now().isoformat()
        }
        self.save()
        return True, "Регистрация успешна"
    
    def login(self, nick, password):
        if nick not in self.users:
            return False, "Пользователь не найден"
        if self.users[nick]["password"] != password:
            return False, "Неверный пароль"
        self.users[nick]["last_login"] = datetime.now().isoformat()
        self.save()
        return True, "Вход выполнен"

db = UserDatabase(USERS_FILE)

# ========== АДМИН-ПАРОЛИ ==========
ADMIN_PASSWORDS = [
    '1234', '123456', '1234578', '123456789', '1379', '13795',
    '139742685', '11397426850', '139742680', '1379548620'
]
SECRET_CODE = 'yorner'

# ========== СКАНИРОВАНИЕ МУЗЫКИ ==========
def scan_music_files():
    """Сканирует папку music/ и возвращает список найденных MP3-файлов"""
    music_files = []
    
    # Создаём папку, если её нет
    if not os.path.exists(MUSIC_DIR):
        os.makedirs(MUSIC_DIR)
        print(f"📁 Создана папка {MUSIC_DIR}/")
        return music_files
    
    # Ищем файлы music1.mp3, music2.mp3, ..., musicN.mp3
    for i in range(1, MAX_MUSIC_FILES + 1):
        filename = f"music{i}.mp3"
        filepath = os.path.join(MUSIC_DIR, filename)
        if os.path.exists(filepath) and os.path.isfile(filepath):
            # Получаем размер файла
            size = os.path.getsize(filepath)
            music_files.append({
                "id": i,
                "name": f"Music {i}",
                "filename": filename,
                "path": f"/music/{filename}",
                "size": size,
                "size_formatted": format_file_size(size)
            })
    
    # Также ищем любые другие MP3-файлы в папке
    for entry in os.scandir(MUSIC_DIR):
        if entry.is_file() and entry.name.lower().endswith('.mp3'):
            # Проверяем, не добавлен ли уже
            if not any(m['filename'] == entry.name for m in music_files):
                size = entry.stat().st_size
                music_files.append({
                    "id": len(music_files) + 1,
                    "name": entry.name.replace('.mp3', '').replace('music', 'Music '),
                    "filename": entry.name,
                    "path": f"/music/{entry.name}",
                    "size": size,
                    "size_formatted": format_file_size(size)
                })
    
    # Сортируем по ID
    music_files.sort(key=lambda x: x['id'])
    
    return music_files

def format_file_size(bytes_size):
    """Форматирует размер файла в читаемый вид"""
    for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} ТБ"

# ========== ИГРОВЫЕ СЕРВЕРЫ ==========
class GameServer:
    def __init__(self, name, host, ws_port, http_port=None):
        self.name = name
        self.host = host
        self.ws_port = ws_port
        self.http_port = http_port or ws_port - 443
        self.players = {}
        self.clients = set()

class ServerManager:
    def __init__(self):
        self.servers = {}
        self.create_server("default", "saevst.mimo.run", 8443)
    
    def create_server(self, name, host, ws_port):
        server = GameServer(name, host, ws_port)
        self.servers[name] = server
        return server
    
    def get_server(self, name):
        return self.servers.get(name, self.servers.get("default"))

server_manager = ServerManager()

# ========== WEBSOCKET ОБРАБОТЧИК ==========
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    player_nick = None
    player_data = {"x": 2500, "y": 2500, "color": "#f97316"}
    
    server_name = request.match_info.get('server', 'default')
    server = server_manager.get_server(server_name)
    server.clients.add(ws)
    
    print(f"🔗 Новое подключение к серверу '{server_name}'")
    
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    msg_type = data.get('type')
                    
                    if msg_type == 'join':
                        player_nick = data.get('nick')
                        player_data = {
                            "x": data.get('x', 2500),
                            "y": data.get('y', 2500),
                            "color": data.get('color', '#f97316'),
                            "ws": ws
                        }
                        server.players[player_nick] = player_data
                        
                        players_info = {
                            n: {"x": p["x"], "y": p["y"], "color": p["color"]}
                            for n, p in server.players.items()
                        }
                        await ws.send_json({"type": "players", "players": players_info})
                        
                        for client in server.clients:
                            if client != ws and not client.closed:
                                await client.send_json({
                                    "type": "player_joined",
                                    "nick": player_nick,
                                    "color": data.get('color'),
                                    "x": data.get('x', 2500),
                                    "y": data.get('y', 2500)
                                })
                        
                        print(f"👤 {player_nick} присоединился к серверу '{server_name}'")
                    
                    elif msg_type == 'position':
                        if player_nick and player_nick in server.players:
                            server.players[player_nick]["x"] = data.get('x')
                            server.players[player_nick]["y"] = data.get('y')
                            server.players[player_nick]["color"] = data.get('color', player_data["color"])
                            
                            for client in server.clients:
                                if client != ws and not client.closed:
                                    await client.send_json({
                                        "type": "position",
                                        "nick": player_nick,
                                        "x": data.get('x'),
                                        "y": data.get('y'),
                                        "color": data.get('color')
                                    })
                    
                    elif msg_type == 'chat':
                        text = data.get('text', '')
                        to = data.get('to', 'all')
                        
                        chat_msg = {
                            "type": "chat",
                            "nick": player_nick,
                            "text": text,
                            "to": to
                        }
                        
                        if to == 'all':
                            for client in server.clients:
                                if not client.closed:
                                    await client.send_json(chat_msg)
                        else:
                            for nick, pdata in server.players.items():
                                if nick == to:
                                    target_ws = pdata.get('ws')
                                    if target_ws and not target_ws.closed:
                                        await target_ws.send_json(chat_msg)
                                    break
                            await ws.send_json(chat_msg)
                        
                        print(f"💬 {player_nick} → {to}: {text}")
                    
                    elif msg_type == 'command':
                        command = data.get('command', '')
                        result = execute_server_command(command, player_nick, server)
                        await ws.send_json({"type": "command_result", "result": result})
                
                except json.JSONDecodeError:
                    print(f"⚠️ Неверный JSON от клиента")
            
            elif msg.type == WSMsgType.ERROR:
                print(f"⚠️ WebSocket ошибка: {ws.exception()}")
    
    except Exception as e:
        print(f"⚠️ Ошибка WebSocket: {e}")
    
    finally:
        if player_nick and player_nick in server.players:
            del server.players[player_nick]
            for client in server.clients:
                if client != ws and not client.closed:
                    await client.send_json({"type": "player_left", "nick": player_nick})
            print(f"👋 {player_nick} покинул сервер '{server_name}'")
        
        server.clients.discard(ws)
    
    return ws

def execute_server_command(command, player_nick, server):
    """Обработка серверных команд"""
    parts = command.strip().split()
    if not parts:
        return "Пустая команда"
    
    cmd = parts[0].lower()
    
    if cmd == '/help':
        return """
📋 Список команд:
/help — показать эту справку
/tp biome Ocean|Beach|Forest — телепорт в биом (пример: /tp biome Forest)
/tp coord X Y — телепорт по координатам (пример: /tp coord 3000 2000)
/creative — режим творчества
/survival — режим выживания
/give <предмет> <кол-во> — выдать предмет (пример: /give wood 10)
/spawn tiger|giraffe — заспавнить животное (пример: /spawn tiger)
/clear — очистить инвентарь
/players — список игроков на сервере
/server — информация о сервере
/music — список доступной музыки
        """.strip()
    
    elif cmd == '/players':
        players = list(server.players.keys())
        return f"👥 Игроки ({len(players)}): " + ", ".join(players) if players else "Нет игроков"
    
    elif cmd == '/server':
        return f"🖥️ Сервер: {server.name}\n📍 Хост: {server.host}\n🔌 Порт: {server.ws_port}\n👥 Игроков: {len(server.players)}"
    
    elif cmd == '/music':
        music = scan_music_files()
        if not music:
            return "🎵 Нет доступных треков"
        tracks = [f"{m['id']}. {m['name']} ({m['size_formatted']})" for m in music]
        return "🎵 Доступные треки:\n" + "\n".join(tracks)
    
    else:
        return f"Команда '{cmd}' обработана клиентом"

# ========== HTTP API ==========
async def handle_api_register(request):
    try:
        data = await request.json()
        nick = data.get('nick', '').strip()
        password = data.get('password', '').strip()
        
        if not nick or not password:
            return web.json_response({"success": False, "error": "Введите ник и пароль"})
        
        success, message = db.register(nick, password)
        return web.json_response({"success": success, "message": message})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_api_login(request):
    try:
        data = await request.json()
        nick = data.get('nick', '').strip()
        password = data.get('password', '').strip()
        
        if nick == '@admin':
            if password in ADMIN_PASSWORDS:
                return web.json_response({
                    "success": True,
                    "message": "Требуется код администратора",
                    "require_admin_code": True
                })
            return web.json_response({"success": False, "error": "Неверный пароль администратора"})
        
        success, message = db.login(nick, password)
        return web.json_response({"success": success, "message": message})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_api_verify_admin(request):
    try:
        data = await request.json()
        code = data.get('code', '').strip().lower()
        if code == SECRET_CODE:
            return web.json_response({"success": True, "message": "Код верен"})
        return web.json_response({"success": False, "error": "Неверный код"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_api_music(request):
    """Возвращает список доступных музыкальных файлов"""
    try:
        music_files = scan_music_files()
        return web.json_response({
            "success": True,
            "tracks": music_files,
            "count": len(music_files),
            "directory": MUSIC_DIR
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_index(request):
    return web.FileResponse('index.html')

async def handle_favicon(request):
    if os.path.exists('favicon.ico'):
        return web.FileResponse('favicon.ico')
    return web.Response(status=404)

# ========== ЗАПУСК СЕРВЕРА ==========
async def init_app():
    app = web.Application()
    
    # CORS
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods=["GET", "POST", "OPTIONS"]
        )
    })
    
    # HTTP маршруты
    app.router.add_get('/', handle_index)
    app.router.add_get('/favicon.ico', handle_favicon)
    
    # API
    app.router.add_post('/api/register', handle_api_register)
    app.router.add_post('/api/login', handle_api_login)
    app.router.add_post('/api/verify-admin', handle_api_verify_admin)
    app.router.add_get('/api/music', handle_api_music)
    
    # WebSocket
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/ws/{server}', websocket_handler)
    app.router.add_get('/{server}', handle_index)
    
    # Статические файлы (музыка)
    if os.path.exists(MUSIC_DIR):
        app.router.add_static('/music/', path=MUSIC_DIR, show_index=False)
        print(f"🎵 Папка с музыкой: {MUSIC_DIR}/ ({len(scan_music_files())} треков)")
    else:
        os.makedirs(MUSIC_DIR)
        app.router.add_static('/music/', path=MUSIC_DIR, show_index=False)
        print(f"📁 Создана пустая папка {MUSIC_DIR}/")
    
    # CORS для всех маршрутов
    for route in list(app.router.routes()):
        cors.add(route)
    
    return app

def main():
    # Сканируем музыку при запуске
    music_files = scan_music_files()
    
    print(f"""
╔══════════════════════════════════════════════════╗
║          MySland Server v2.0                    ║
║          saevst.mimo.run                        ║
╠══════════════════════════════════════════════════╣
║ HTTP порт:      {HTTP_PORT}                              ║
║ WebSocket порт: {WS_PORT}                             ║
║ Пользователи:   {len(db.users)} активны                     ║
║ Музыка:         {len(music_files)} треков в {MUSIC_DIR}/              ║
╚══════════════════════════════════════════════════╝
    """)
    
    # Выводим список треков
    if music_files:
        print("🎵 Доступные треки:")
        for track in music_files:
            print(f"   {track['id']:2d}. {track['name']:20s} {track['size_formatted']:>10s}")
    else:
        print("🎵 Нет треков. Добавьте music1.mp3 ... musicN.mp3 в папку music/")
    
    app = init_app()
    web.run_app(app, host=HOST, port=HTTP_PORT)

if __name__ == '__main__':
    main()
