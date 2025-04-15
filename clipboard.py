# -*- coding: utf-8 -*-
# @Time    : 2025/04/15
# @Author  : naihe
# @File    : SyncPaste.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import time
import ui
import keyboard
import requests
import clipboard
import json
import os
import logging
import hashlib
import objc_util
from typing import Optional, Dict, Any, Union, BinaryIO
from urllib.parse import urljoin


def get_documents_path() -> str:
    """
    获取 Pythonista 中的 Documents 路径，若不存在则使用当前工作目录。
    """
    documents = os.path.join(os.path.expanduser("~"), "Documents")
    if not os.path.isdir(documents):
        documents = os.getcwd()
    return documents

def load_api_config_file(filename: str = "api_config.json") -> Optional[Dict[str, Any]]:
    """
    尝试从 Documents 下加载配置文件。若失败则返回 None。
    """
    config_path = os.path.join(get_documents_path(), filename)
    if not os.path.isfile(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"读取配置文件 {filename} 失败: {e}")
    return None

def save_api_config_file(config: Dict[str, Any], filename: str = "api_config.json") -> None:
    """
    将配置写入到 Documents 下的指定文件中（JSON 格式）。
    """
    config_path = os.path.join(get_documents_path(), filename)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存配置文件 {filename} 失败: {e}")

def prompt_for_api_config(defaults: Dict[str, Any]) -> Dict[str, Any]:
    """
    通过控制台交互提示用户输入配置，若用户不输入则保留默认值。
    """
    print("===== 配置向导 =====")
    base_url = input(f"请输入 访问地址 (默认: {defaults.get('base_url','')}): ").strip()
    if not base_url:
        base_url = defaults.get("base_url", "")

    # headers 下的子项
    headers_default = defaults.get("headers", {})
    x_expire = input(f"请输入 内容过期时间/秒 (默认: {headers_default.get('x-expire','')}): ").strip()
    if not x_expire:
        x_expire = headers_default.get("x-expire", "")
    cookie = input(f"请输入 Token (http://访问地址/home#settings 获取): ").strip()
    if not cookie:
        cookie = defaults.get("cookie", "")

    resource = input(f"请输入 共享路径 (默认: {defaults.get('resource','')}): ").strip()
    if not resource:
        resource = defaults.get("resource", "")

    password = input(f"请输入 访问密码 (默认空，如无需密码可直接回车): ").strip()
    # 若不输则为空字符串或原值
    if not password:
        password = defaults.get("password", "")

    # 组装新的配置字典
    return {
        "base_url": base_url,
        "headers": {
            "x-expire": x_expire,
            "cookie": cookie
        },
        "resource": resource,
        "password": password
    }

def load_or_prompt_api_config(default_config: Dict[str, Any], filename: str = "api_config.json") -> Dict[str, Any]:
    """
    先尝试读取配置文件；若读取失败（或文件不存在），则通过交互方式获取并保存到文件；
    最后在控制台打印当前使用的配置并返回。
    """
    config_from_file = load_api_config_file(filename)
    if config_from_file is None:
        # 文件不存在或读取失败，进行交互式配置
        config_from_file = prompt_for_api_config(default_config)
        save_api_config_file(config_from_file, filename)
        print("\n配置已保存。")
    else:
        print(f"检测到已有配置文件 {filename}，将直接使用。")

    print("当前配置如下：")
    print(json.dumps(config_from_file, indent=2, ensure_ascii=False))
    path = f"/e/{config_from_file['resource']}/{config_from_file['password']}"
    print(f"你还可以通过浏览器同步剪贴板\n{urljoin(config_from_file['base_url'], path)}")
    print("================== 结束 ====================\n")
    return config_from_file

MODE: str = sys.argv[1].lower() if len(sys.argv) > 1 else "send"

def setup_logger() -> logging.Logger:
    documents = get_documents_path()
    log_file = os.path.join(documents, "log.txt")
    logger = logging.getLogger("ClipboardSync")
    logger.setLevel(logging.ERROR)
    if not logger.handlers:
        handler = logging.FileHandler(log_file, encoding="utf-8")
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

logger = setup_logger()

default_api_config = {
    'base_url': 'http://localhost:8000',  # 可替换成你的服务地址
    'headers': {
        'x-expire': '3600',         # 剪贴板内容过期时间
        'cookie': ''  # 进入 /home#settings 路径生成 token, 例如token=eyJhbGcixxxxxx
    },
    'resource': 'clipboard',        # 可修改为其他资源名称
    'password': '',
}

api_config = load_or_prompt_api_config(default_api_config, "api_config.json")

class API:
    def __init__(self, config: Dict[str, Any]):
        self.base_url = config.get('base_url', '').rstrip('/')
        self.headers = config.get('headers', {})
        self.resource = config.get('resource', 'clipboard')
        self.password = config.get('password', '')

    def get_clipboard(self) -> str:
        response = requests.get(
            f"{self.base_url}/r/{self.resource}?t={int(time.time())}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.text

    def save_clipboard(self, content: Union[str, bytes]) -> str:
        response = requests.post(
            f"{self.base_url}/s/{self.resource}?t={int(time.time())}",
            data=content,
            headers=self.headers
        )
        response.raise_for_status()
        return response.json().get("message", "No message")

    def upload_file(
        self,
        file_data: Union[BinaryIO, bytes],
        filename: Optional[str] = None,
        file_type: Optional[str] = None
    ) -> Dict[str, Any]:
        headers = self.headers.copy()
        response = requests.put(
            f"{self.base_url}/s/{self.resource}?t={int(time.time())}",
            headers=headers,
            data=file_data,
        )
        response.raise_for_status()
        return response.json().get("message", {})

api = API(api_config)

class StateManager:
    """
    状态管理器，将剪贴板同步状态持久化到本地文件，
    包括：
      - last_sent_hash: 最近成功上传的剪贴板内容的 hash
      - last_remote_hash: 最近从服务端同步下来的剪贴板内容的 hash
      - uptime: 上次同步成功的时间戳
    """

    def __init__(self, filename: str = "sync_state.json") -> None:
        documents = get_documents_path()
        self.filename = os.path.join(documents, filename)
        self.state = {
            "last_sent_hash": "",
            "last_remote_hash": "",
            "uptime": 0.0
        }
        self.load()

    def load(self) -> None:
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                self.state = json.load(f)
        except Exception:
            pass  # 若读取失败则使用默认初始值

    def save(self) -> None:
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.state, f)
        except Exception as ex:
            logger.error("保存状态失败：%s", ex)

    @property
    def last_sent_hash(self) -> str:
        return self.state.get("last_sent_hash", "")

    @last_sent_hash.setter
    def last_sent_hash(self, value: str) -> None:
        self.state["last_sent_hash"] = value
        self.save()

    @property
    def last_remote_hash(self) -> str:
        return self.state.get("last_remote_hash", "")

    @last_remote_hash.setter
    def last_remote_hash(self, value: str) -> None:
        self.state["last_remote_hash"] = value
        self.save()

    @property
    def uptime(self) -> float:
        return self.state.get("uptime", 0.0)

    @uptime.setter
    def uptime(self, value: float) -> None:
        self.state["uptime"] = value
        self.save()

class ClipboardSyncView(ui.View):
    """
    剪贴板同步视图
    支持两种模式：
      - send 模式：检测本地剪贴板内容变化，上传到服务器；
      - receive 模式：定时从远程获取内容
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.background_color = "#00436e"

        # 状态显示 Label
        self.label = ui.Label(frame=self.bounds.inset(0, 4, 0, 36), flex='WH')
        self.label.font = ("Menlo", 12)
        self.label.text_color = "white"
        self.label.number_of_lines = 0
        self.add_subview(self.label)
        self.label.text = f"模式: {MODE}\nloading..."
        self.state_manager = StateManager()

        # 轮询延时相关
        self.base_delay: float = 5.0
        self.delay: float = self.base_delay

        # 保存本地剪贴板缓存：文本及其 hash
        try:
            self.local_clip_cache: str = clipboard.get() or ""
        except Exception as ex:
            logger.error("读取本地剪贴板异常：%s", ex)
            self.local_clip_cache = ""
        self.local_clip_hash: str = self._calc_hash(self.local_clip_cache)

        # 记录是否需要主动进行同步
        self.sync_needed = True

        if not self.state_manager.uptime:
            self.state_manager.uptime = time.time()
        self.schedule_poll(self.delay)

    def will_close(self) -> None:
        ui.cancel_delays(self.poll)

    @staticmethod
    def _calc_hash(text: str) -> str:
        """计算文本的 MD5 hash 值。"""
        if text:
            return hashlib.md5(text.encode("utf-8")).hexdigest()

    def kb_text_changed(self) -> None:
        if MODE == "send":
            self.sync_needed = True

    def schedule_poll(self, delay: float) -> None:
        ui.delay(self.poll, delay)

    def poll(self) -> None:
        """
        poll 方法确保上次同步（state_manager.uptime）与当前时间间隔至少为 delay 秒，否则延后调用
        """
        current = time.time()
        elapsed = current - self.state_manager.uptime
        if elapsed < self.delay:
            # 若距离上次成功同步还不满 delay 秒，则在剩余时间后再执行
            ui.delay(self.poll, self.delay - elapsed)
            return

        # 如果需要同步（send模式）或处于receive模式，执行同步
        if (MODE == "send" and self.sync_needed) or MODE == "receive":
            self.sync_clipboard()

        # 安排下一次 poll
        self.schedule_poll(self.delay)

    def sync_clipboard(self) -> None:
        """
        执行同步操作：
         - send 模式：若本地剪贴板 hash 与 state_manager.last_sent_hash 不一致，则上传更新；
         - receive 模式：拉取远程内容后，与本地缓存的 hash 对比，若不同则更新本地剪贴板。
        """
        status_info = f"模式: {MODE}\n"
        current = time.time()

        if MODE == "send":
            # 读取最新本地剪贴板文本
            try:
                local_clip = clipboard.get() or ""
                local_hash = self._calc_hash(local_clip)
                self.local_clip_cache = local_clip
                self.local_clip_hash = local_hash
            except Exception as ex:
                status_info += "读取本地剪贴板异常。\n"
                logger.error("读取本地剪贴板异常：%s", ex)
                local_clip = ""
                local_hash = ""

            # 若与上次发送的 hash 不同，则进行上传
            if local_clip and local_hash != self.state_manager.last_sent_hash:
                try:
                    result = api.save_clipboard(local_clip.encode("utf-8"))
                    self.state_manager.last_sent_hash = local_hash
                    status_info += f"上传成功: {result}\n"
                except Exception as ex:
                    status_info += "上传异常。\n"
                    logger.error("上传异常：%s", ex)
            else:
                status_info += "本地无变化，不上传。\n"

            # 成功执行一次同步后，重置标志位、恢复基础延时
            self.sync_needed = False
            self.delay = self.base_delay

        elif MODE == "receive":
            remote_clip = ""
            try:
                remote_clip = api.get_clipboard()
                remote_hash = self._calc_hash(remote_clip)
                self.delay = self.base_delay
                status_info += "获取远程数据成功。\n"

                # 若远端内容 hash 变化，则更新到本地剪贴板
                if remote_clip and remote_hash != self.local_clip_hash:
                    try:
                        clipboard.set(remote_clip)
                        self.local_clip_cache = remote_clip
                        self.local_clip_hash = remote_hash
                        status_info += "本地剪贴板已更新。\n"
                    except Exception as ex:
                        status_info += "更新本地剪贴板异常。\n"
                        logger.error("更新本地剪贴板异常：%s", ex)
                else:
                    status_info += "远程无更新。\n"

                self.state_manager.last_remote_hash = remote_hash
            except Exception as ex:
                status_info += "获取远程数据异常。\n"
                logger.error("获取远程数据异常：%s", ex)
                self.delay = min(self.delay * 2, 300.0)
                status_info += f"当前轮询延时调整为: {self.delay:.1f}s（指数退避）\n"
        else:
            status_info += "未知模式，请使用 'send' 或 'receive'.\n"

        self.state_manager.uptime = current
        status_info += f"下次同步延时: {self.delay:.1f}s\n"
        self.label.text = status_info


if __name__ == "__main__":
    view = ClipboardSyncView()
    keyboard.set_view(view)
