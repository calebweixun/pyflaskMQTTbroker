#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import logging
import json
import time
import sys
import os
import netifaces
from collections import defaultdict

# 獲取所有網絡接口的 IP 地址


def get_all_ip_addresses():
    """獲取所有網絡接口的 IP 地址"""
    ip_list = []
    interfaces = netifaces.interfaces()

    for interface in interfaces:
        # 跳過回環接口
        if interface == 'lo':
            continue

        addrs = netifaces.ifaddresses(interface)
        if netifaces.AF_INET in addrs:
            for addr in addrs[netifaces.AF_INET]:
                ip_list.append((interface, addr['addr']))

    return ip_list

# 載入配置


def load_config(config_file="config.json"):
    """載入配置文件"""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[錯誤] 無法載入配置文件 {config_file}: {e}")
        return {
            "broker": {"host": "0.0.0.0", "port": 1883},
            "logging": {"level": "INFO", "format": "%(asctime)s - [%(levelname)s] - %(message)s"},
            "mqtt": {"allow_anonymous": False}
        }

# 載入用戶


def load_users(user_file="users.json"):
    """載入用戶文件"""
    try:
        with open(user_file, 'r') as f:
            data = json.load(f)
            users = {}
            for user in data["users"]:
                users[user["username"]] = {
                    "password": user["password"],
                    "permissions": user["permissions"]
                }
            return users
    except Exception as e:
        print(f"[錯誤] 無法載入用戶文件 {user_file}: {e}")
        return {
            "user": {"password": "password", "permissions": ["read", "write"]},
            "test": {"password": "test123", "permissions": ["read", "write"]}
        }


# 載入配置和用戶
raw_config = load_config()
USERS = load_users()
# 使用默認值合併載入的配置
default_conf = {
    'broker': {'host': '0.0.0.0', 'port': 1883, 'max_connections': 5},
    'logging': {'level': 'INFO', 'format': '%(asctime)s - [%(levelname)s] - %(message)s'},
    'mqtt': {'allow_anonymous': False}
}
CONFIG = {}
for key, val in default_conf.items():
    # 若原始配置有該部分且為 dict，則合併其子項，否則使用預設
    if key in raw_config and isinstance(raw_config[key], dict):
        cfg_section = default_conf[key].copy()
        cfg_section.update(raw_config[key])
        CONFIG[key] = cfg_section
    else:
        CONFIG[key] = val

# 設置日誌
log_cfg = CONFIG.get('logging', {})
log_format = log_cfg.get(
    'format', '%(asctime)s - [%(levelname)s] - %(message)s')
log_level_name = log_cfg.get('level', 'INFO').upper()
log_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(level=log_level, format=log_format)
logger = logging.getLogger(__name__)

# MQTT 常量
CONNECT = 0x10
CONNACK = 0x20
PUBLISH = 0x30
PUBACK = 0x40
SUBSCRIBE = 0x80
SUBACK = 0x90
DISCONNECT = 0xE0

# 從配置中獲取設置
HOST = CONFIG['broker'].get('host', '0.0.0.0')
PORT = CONFIG['broker'].get('port', 1883)


class MQTTBroker:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.socket = None
        self.clients = {}  # client_id -> socket
        self.client_info = {}  # client_id -> {'username', 'connected', 'last_seen'}
        self.topics = defaultdict(list)  # topic -> [client_ids]
        self.running = False

    def start(self):
        """啟動 MQTT Broker"""
        # 獲取所有網絡接口的 IP 地址
        ip_addresses = get_all_ip_addresses()

        # 開始監聽
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(CONFIG["broker"].get("max_connections", 5))
        self.running = True

        # 顯示啟動信息
        logger.info(f"[啟動] MQTT Broker 已啟動並監聽在 {self.host}:{self.port}")

        # 顯示所有可用的 IP 地址
        if ip_addresses:
            logger.info(f"[網絡] MQTT Broker 可通過以下 IP 地址訪問:")
            for interface, ip in ip_addresses:
                logger.info(f"[網絡] 接口: {interface}, IP: {ip}:{self.port}")
        else:
            logger.info(f"[網絡] 未發現任何網絡接口")

        try:
            while self.running:
                client_socket, address = self.socket.accept()
                logger.info(f"[連接] 收到來自 {address} 的新連接")
                client_thread = threading.Thread(
                    target=self.handle_client, args=(client_socket, address))
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            logger.info("[關閉] 收到中斷信號，正在關閉 Broker...")
        except Exception as e:
            logger.error(f"[錯誤] 發生錯誤：{e}")
        finally:
            self.stop()

    def stop(self):
        """停止 MQTT Broker"""
        self.running = False
        if self.socket:
            self.socket.close()
        active_clients = list(self.clients.keys())
        for client_id in active_clients:
            try:
                self.clients[client_id].close()
                logger.info(f"[關閉] 關閉客戶端 {client_id} 的連接")
            except:
                pass
        logger.info("[關閉] MQTT Broker 已完全關閉")

    def handle_client(self, client_socket, address):
        """處理客戶端連接"""
        client_id = None

        try:
            while self.running:
                # 解析 MQTT 報文頭
                packet_type_byte = client_socket.recv(1)
                if not packet_type_byte:
                    logger.info(f"[斷開] 客戶端連接已關閉")
                    break  # 客戶端斷開連接

                packet_type = packet_type_byte[0] & 0xF0

                # 解析剩餘長度
                multiplier = 1
                remaining_length = 0
                while True:
                    byte = client_socket.recv(1)[0]
                    remaining_length += (byte & 127) * multiplier
                    multiplier *= 128
                    if (byte & 128) == 0:
                        break

                # 讀取完整的報文
                payload = b''
                if remaining_length > 0:
                    payload = client_socket.recv(remaining_length)

                # 處理不同類型的 MQTT 報文
                if packet_type == CONNECT:
                    client_id, username, password = self.parse_connect(payload)
                    if not client_id or not self.authenticate(client_id, username, password):
                        # 認證失敗
                        logger.warning(f"[認證] 客戶端 {client_id} 認證失敗")
                        self.send_connack(client_socket, 0x05)  # 認證失敗
                        break

                    # 認證成功，存儲客戶端信息
                    self.clients[client_id] = client_socket
                    self.client_info[client_id] = {
                        'username': username,
                        'connected': True,
                        'last_seen': time.time(),
                        'address': address
                    }

                    # 發送連接確認
                    self.send_connack(client_socket, 0x00)  # 連接接受
                    logger.info(f"[認證] 客戶端 {client_id} (用戶: {username}) 連接成功")

                elif packet_type == PUBLISH:
                    if not client_id:
                        logger.warning(f"[發布] 未認證客戶端嘗試發布消息")
                        continue  # 忽略未認證客戶端

                    topic, message = self.parse_publish(payload)
                    logger.info(
                        f"[發布] 客戶端 {client_id} 發布到主題 '{topic}': {message}")

                    # 檢查權限
                    username = self.client_info[client_id]['username']
                    if not self.check_permission(username, "write"):
                        logger.warning(
                            f"[權限] 客戶端 {client_id} (用戶: {username}) 沒有發布權限")
                        continue

                    # 轉發消息給訂閱者
                    self.broadcast_message(client_id, topic, message)

                elif packet_type == SUBSCRIBE:
                    if not client_id:
                        logger.warning(f"[訂閱] 未認證客戶端嘗試訂閱主題")
                        continue  # 忽略未認證客戶端

                    # 檢查權限
                    username = self.client_info[client_id]['username']
                    if not self.check_permission(username, "read"):
                        logger.warning(
                            f"[權限] 客戶端 {client_id} (用戶: {username}) 沒有訂閱權限")
                        self.send_suback(client_socket, 0, [
                                         0x80] * 10)  # 拒絕所有訂閱
                        continue

                    packet_id, topics = self.parse_subscribe(payload)

                    # 訂閱主題
                    for topic, qos in topics:
                        if client_id not in self.topics[topic]:
                            self.topics[topic].append(client_id)
                        logger.info(f"[訂閱] 客戶端 {client_id} 訂閱主題：{topic}")

                    # 發送訂閱確認
                    self.send_suback(client_socket, packet_id,
                                     [0] * len(topics))

                elif packet_type == DISCONNECT:
                    logger.info(f"[斷開] 客戶端 {client_id} 正常斷開連接")
                    break

        except Exception as e:
            logger.error(f"[錯誤] 處理客戶端 {client_id} 時出錯：{e}")
        finally:
            # 清理客戶端資源
            if client_id and client_id in self.clients:
                del self.clients[client_id]
                if client_id in self.client_info:
                    self.client_info[client_id]['connected'] = False

                # 從主題訂閱列表中移除
                for topic in self.topics:
                    if client_id in self.topics[topic]:
                        self.topics[topic].remove(client_id)

                logger.info(f"[清理] 已移除客戶端 {client_id} 的所有資源")

            try:
                client_socket.close()
            except:
                pass

    def parse_connect(self, payload):
        """解析 CONNECT 報文"""
        try:
            # 跳過協議名稱和版本
            offset = 0
            protocol_len = (payload[offset] << 8) + payload[offset+1]
            offset += 2 + protocol_len + 1  # 加上版本號

            # 跳過連接標誌
            connect_flags = payload[offset]
            offset += 1

            # 跳過保持連接
            offset += 2

            # 獲取客戶端 ID
            client_id_len = (payload[offset] << 8) + payload[offset+1]
            offset += 2
            client_id = payload[offset:offset+client_id_len].decode('utf-8')
            offset += client_id_len

            # 檢查是否有用戶名
            username = None
            password = None
            if connect_flags & 0x80:  # 用戶名標誌
                username_len = (payload[offset] << 8) + payload[offset+1]
                offset += 2
                username = payload[offset:offset+username_len].decode('utf-8')
                offset += username_len

                # 檢查是否有密碼
                if connect_flags & 0x40:  # 密碼標誌
                    password_len = (payload[offset] << 8) + payload[offset+1]
                    offset += 2
                    password = payload[offset:offset +
                                       password_len].decode('utf-8')

            return client_id, username, password
        except Exception as e:
            logger.error(f"[錯誤] 解析 CONNECT 時出錯：{e}")
            return None, None, None

    def authenticate(self, client_id, username, password):
        """驗證客戶端憑據"""
        # 檢查是否允許匿名連接
        if CONFIG["mqtt"].get("allow_anonymous", False):
            logger.info(f"[認證] 允許匿名連接，客戶端 {client_id} 被授權")
            return True

        # 檢查用戶名
        if not username:
            logger.warning(f"[認證] 客戶端 {client_id} 未提供用戶名")
            return False

        # 檢查用戶是否存在
        if username not in USERS:
            logger.warning(f"[認證] 用戶 {username} 不存在")
            return False

        # 檢查密碼
        if USERS[username]["password"] != password:
            logger.warning(f"[認證] 用戶 {username} 密碼錯誤")
            return False

        logger.info(f"[認證] 用戶 {username} 認證成功")
        return True

    def check_permission(self, username, permission_type):
        """檢查用戶是否有指定的權限"""
        # 如果允許匿名，則所有人都有權限
        if CONFIG["mqtt"].get("allow_anonymous", False):
            return True

        # 檢查用戶是否存在
        if username not in USERS:
            return False

        # 檢查權限
        return permission_type in USERS[username]["permissions"]

    def send_connack(self, client_socket, return_code):
        """發送 CONNACK 報文"""
        packet = bytearray()
        packet.append(CONNACK)  # 報文類型
        packet.append(2)        # 剩餘長度
        packet.append(0)        # 連接確認標誌
        packet.append(return_code)  # 返回碼
        client_socket.send(packet)

    def parse_publish(self, payload):
        """解析 PUBLISH 報文"""
        try:
            offset = 0

            # 獲取主題名稱
            topic_len = (payload[offset] << 8) + payload[offset+1]
            offset += 2
            topic = payload[offset:offset+topic_len].decode('utf-8')
            offset += topic_len

            # 跳過報文標識符（QoS > 0 時）
            if (payload[0] & 0x06) > 0:
                offset += 2

            # 獲取消息內容
            message = payload[offset:].decode('utf-8')

            return topic, message
        except Exception as e:
            logger.error(f"[錯誤] 解析 PUBLISH 時出錯：{e}")
            return None, None

    def broadcast_message(self, sender_id, topic, message):
        """向訂閱者廣播消息"""
        broadcast_count = 0
        for subscriber_topic in self.topics:
            if self.topic_matches(subscriber_topic, topic):
                for client_id in self.topics[subscriber_topic]:
                    if client_id != sender_id and client_id in self.clients:
                        try:
                            username = self.client_info[client_id]['username']
                            # 檢查接收者的讀取權限
                            if not self.check_permission(username, "read"):
                                continue

                            self.send_publish(
                                self.clients[client_id], topic, message)
                            broadcast_count += 1
                            logger.debug(
                                f"[廣播] 轉發消息到 {client_id}：'{topic}' => {message}")
                        except Exception as e:
                            logger.error(f"[錯誤] 向客戶端 {client_id} 發送消息時出錯：{e}")

        logger.info(f"[廣播] 已將消息 '{topic}' 廣播給 {broadcast_count} 個訂閱者")

    def topic_matches(self, subscription, topic):
        """檢查訂閱的主題是否匹配發布的主題"""
        # 實現通配符主題匹配
        # 如 a/b/c 匹配 a/b/c，a/# 匹配 a/b/c，a/+/c 匹配 a/b/c
        sub_parts = subscription.split('/')
        topic_parts = topic.split('/')

        # 如果訂閱以 # 結尾，則匹配此級別及其以下的所有主題
        if len(sub_parts) > 0 and sub_parts[-1] == '#':
            return len(topic_parts) >= len(sub_parts) - 1 and \
                all(p == '+' or p == t for p,
                    t in zip(sub_parts[:-1], topic_parts[:len(sub_parts)-1]))

        # 如果長度不同且不是通配符，則不匹配
        if len(sub_parts) != len(topic_parts):
            return False

        # 逐級比較
        for i in range(len(sub_parts)):
            if sub_parts[i] != '+' and sub_parts[i] != topic_parts[i]:
                return False

        return True

    def send_publish(self, client_socket, topic, message):
        """發送 PUBLISH 報文"""
        try:
            topic_bytes = topic.encode('utf-8')
            message_bytes = message.encode('utf-8')

            packet = bytearray()
            packet.append(PUBLISH)  # 報文類型

            # 計算剩餘長度
            remaining_length = 2 + len(topic_bytes) + len(message_bytes)

            # 編碼剩餘長度
            while True:
                byte = remaining_length % 128
                remaining_length = remaining_length // 128
                if remaining_length > 0:
                    byte |= 0x80
                packet.append(byte)
                if remaining_length == 0:
                    break

            # 主題名稱
            packet.append((len(topic_bytes) >> 8) & 0xFF)
            packet.append(len(topic_bytes) & 0xFF)
            packet.extend(topic_bytes)

            # 消息內容
            packet.extend(message_bytes)

            client_socket.send(packet)
        except Exception as e:
            logger.error(f"[錯誤] 發送 PUBLISH 時出錯：{e}")

    def parse_subscribe(self, payload):
        """解析 SUBSCRIBE 報文"""
        try:
            offset = 0

            # 獲取報文標識符
            packet_id = (payload[offset] << 8) + payload[offset+1]
            offset += 2

            topics = []
            while offset < len(payload):
                # 獲取主題過濾器
                topic_len = (payload[offset] << 8) + payload[offset+1]
                offset += 2
                topic = payload[offset:offset+topic_len].decode('utf-8')
                offset += topic_len

                # 獲取 QoS
                qos = payload[offset]
                offset += 1

                topics.append((topic, qos))

            return packet_id, topics
        except Exception as e:
            logger.error(f"[錯誤] 解析 SUBSCRIBE 時出錯：{e}")
            return None, []

    def send_suback(self, client_socket, packet_id, return_codes):
        """發送 SUBACK 報文"""
        try:
            packet = bytearray()
            packet.append(SUBACK)  # 報文類型

            # 計算剩餘長度
            remaining_length = 2 + len(return_codes)  # 報文標識符 + 返回碼列表
            packet.append(remaining_length)

            # 報文標識符
            packet.append((packet_id >> 8) & 0xFF)
            packet.append(packet_id & 0xFF)

            # 返回碼列表
            for code in return_codes:
                packet.append(code)

            client_socket.send(packet)
        except Exception as e:
            logger.error(f"[錯誤] 發送 SUBACK 時出錯：{e}")

    def print_status(self):
        """打印 Broker 狀態信息"""
        connected_clients = sum(
            1 for info in self.client_info.values() if info['connected'])

        print("\n=== MQTT Broker 狀態 ===")
        print(f"[狀態] 運行地址: {self.host}:{self.port}")
        print(f"[狀態] 已連接客戶端: {connected_clients}")
        print(
            f"[狀態] 活動訂閱: {sum(len(clients) for clients in self.topics.values())}")
        print(f"[狀態] 主題數量: {len(self.topics)}")

        print("\n活動客戶端:")
        for client_id, info in self.client_info.items():
            if info['connected']:
                last_seen = time.strftime(
                    '%Y-%m-%d %H:%M:%S', time.localtime(info['last_seen']))
                print(
                    f"[客戶端] ID: {client_id}, 用戶: {info['username']}, 地址: {info['address']}, 最後活動: {last_seen}")

        print("\n活動訂閱:")
        for topic, clients in self.topics.items():
            if clients:
                print(f"[訂閱] 主題: {topic}, 訂閱者: {len(clients)}")


if __name__ == "__main__":
    # 檢查 netifaces 庫是否安裝
    try:
        import netifaces
    except ImportError:
        print("[警告] 缺少 netifaces 庫，無法顯示網絡接口信息。請使用 pip install netifaces 安裝。")
        # 定義一個簡單的替代函數

        def get_all_ip_addresses():
            try:
                hostname = socket.gethostname()
                ip = socket.gethostbyname(hostname)
                return [("local", ip)]
            except:
                return []

    broker = MQTTBroker(host=HOST, port=PORT)

    # 創建狀態監控線程
    def status_monitor(broker):
        while broker.running:
            broker.print_status()
            time.sleep(30)  # 每30秒更新一次

    monitor_thread = threading.Thread(target=status_monitor, args=(broker,))
    monitor_thread.daemon = True
    monitor_thread.start()

    try:
        print(f"[啟動] MQTT Broker 正在啟動，配置從 config.json 加載")
        print(f"[啟動] 用戶信息從 users.json 加載")
        broker.start()
    except KeyboardInterrupt:
        print("[關閉] 收到 KeyboardInterrupt，正在關閉...")
    finally:
        broker.stop()
