#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import paho.mqtt.client as mqtt
import time
import sys
import logging
import json
import os

# 載入配置


def load_config(config_file="config.json"):
    """載入配置文件"""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[錯誤] 無法載入配置文件 {config_file}: {e}")
        return {
            "broker": {"host": "localhost", "port": 1883},
            "logging": {"level": "INFO", "format": "%(asctime)s - [%(levelname)s] - %(message)s"},
            "mqtt": {"allow_anonymous": False}
        }

# 載入用戶配置


def load_user_info(user_file="users.json", username="user"):
    """載入用戶配置"""
    try:
        with open(user_file, 'r') as f:
            data = json.load(f)
            for user in data["users"]:
                if user["username"] == username:
                    return user
            print(f"[錯誤] 在用戶文件中未找到用戶 {username}")
            return {"username": "user", "password": "password"}
    except Exception as e:
        print(f"[錯誤] 無法載入用戶文件 {user_file}: {e}")
        return {"username": "user", "password": "password"}


# 載入配置
CONFIG = load_config()

# 設置日誌
log_format = CONFIG["logging"]["format"]
log_level = getattr(logging, CONFIG["logging"]["level"])
logging.basicConfig(level=log_level, format=log_format)
logger = logging.getLogger(__name__)

# MQTT 設置
MQTT_BROKER = CONFIG["broker"]["host"]
MQTT_PORT = CONFIG["broker"]["port"]
MQTT_TOPIC = "test/topic"  # 預設主題
CLIENT_ID = f"python-mqtt-client-{os.getpid()}"  # 使用進程 ID 確保唯一性

# 連接回調函數


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"[連接] 已連接到 MQTT Broker 地址 {MQTT_BROKER}")
        # 訂閱主題
        if userdata.get("mode") == "sub":
            client.subscribe(userdata.get("topic", MQTT_TOPIC))
            logger.info(f"[訂閱] 已訂閱主題: {userdata.get('topic', MQTT_TOPIC)}")
    else:
        logger.error(f"[錯誤] 連接失敗，錯誤碼: {rc}")
        # 顯示錯誤信息
        conn_codes = {
            1: "協議版本錯誤",
            2: "無效的客戶端標識符",
            3: "服務器不可用",
            4: "用戶名或密碼錯誤",
            5: "未授權"
        }
        if rc in conn_codes:
            logger.error(f"[錯誤] 原因: {conn_codes[rc]}")

# 消息接收回調函數


def on_message(client, userdata, msg):
    logger.info(f"[消息] 接收到主題 '{msg.topic}' 的消息: {msg.payload.decode()}")

# 連接中斷回調函數


def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.warning(f"[斷開] 非預期的斷開連接 (代碼: {rc})，正在嘗試重新連接...")
    else:
        logger.info(f"[斷開] 已與服務器斷開連接")

# 發布回調函數


def on_publish(client, userdata, mid):
    logger.debug(f"[發布] 消息 ID {mid} 已發布")

# 訂閱回調函數


def on_subscribe(client, userdata, mid, granted_qos):
    logger.debug(f"[訂閱] 訂閱 ID {mid} 已被服務器確認，QoS: {granted_qos}")

# 訂閱者功能


def run_subscriber(username="user", password=None, topic=MQTT_TOPIC):
    """運行 MQTT 訂閱者"""
    # 如果沒有提供密碼，則從配置中獲取
    if password is None:
        user_info = load_user_info(username=username)
        password = user_info.get("password", "password")

    # 設置用戶資料字典
    userdata = {
        "mode": "sub",
        "topic": topic,
        "username": username
    }

    client = mqtt.Client(CLIENT_ID + "-sub", userdata=userdata)

    # 設置回調函數
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    client.on_subscribe = on_subscribe

    # 設置用戶名密碼
    client.username_pw_set(username, password)

    # 設置自動重連
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    try:
        logger.info(f"[啟動] MQTT 訂閱者，用戶: {username}")
        logger.info(f"[連接] 正在連接到 {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)

        # 開始消息處理循環
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("[關閉] 收到鍵盤中斷，關閉中...")
        client.disconnect()
    except Exception as e:
        logger.error(f"[錯誤] 連接錯誤: {e}")
        sys.exit(1)

# 發布者功能


def run_publisher(username="user", password=None, topic=MQTT_TOPIC):
    """運行 MQTT 發布者"""
    # 如果沒有提供密碼，則從配置中獲取
    if password is None:
        user_info = load_user_info(username=username)
        password = user_info.get("password", "password")

    # 設置用戶資料字典
    userdata = {
        "mode": "pub",
        "topic": topic,
        "username": username
    }

    client = mqtt.Client(CLIENT_ID + "-pub", userdata=userdata)

    # 設置回調函數
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish

    # 設置用戶名密碼
    client.username_pw_set(username, password)

    try:
        logger.info(f"[啟動] MQTT 發布者，用戶: {username}")
        logger.info(f"[連接] 正在連接到 {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)

        # 啟動網路循環
        client.loop_start()

        # 等待連接成功
        time.sleep(1)

        counter = 0
        while True:
            try:
                message = f"測試消息 #{counter} 從 {username}"
                logger.info(f"[發布] 正在發布消息到主題 '{topic}': {message}")
                result = client.publish(topic, message)
                if result.rc == 0:
                    logger.info(f"[發布] 消息已成功發布")
                else:
                    logger.warning(f"[發布] 消息發布失敗，錯誤碼: {result.rc}")
                counter += 1
                time.sleep(5)
            except KeyboardInterrupt:
                break

        logger.info("[關閉] 發布者已停止")
        client.disconnect()
        client.loop_stop()

    except KeyboardInterrupt:
        logger.info("[關閉] 收到鍵盤中斷，關閉中...")
        client.disconnect()
        client.loop_stop()
    except Exception as e:
        logger.error(f"[錯誤] 連接錯誤: {e}")
        sys.exit(1)


def print_usage():
    """打印用法信息"""
    print("用法: python mqtt_client.py [mode] [options]")
    print("模式:")
    print("  pub             - 運行為發布者")
    print("  sub             - 運行為訂閱者")
    print("選項:")
    print("  -u, --user      - 用戶名 (默認: user)")
    print("  -p, --password  - 密碼")
    print("  -t, --topic     - 主題 (默認: test/topic)")
    print("  -h, --help      - 顯示此幫助信息")
    print("例子:")
    print("  python mqtt_client.py sub -u test -t sensors/temp")
    print("  python mqtt_client.py pub -u admin -p admin123 -t control/lights")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ['-h', '--help']:
        print_usage()
        sys.exit(0)

    mode = sys.argv[1].lower()

    # 解析命令行參數
    username = "user"
    password = None
    topic = MQTT_TOPIC

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] in ['-u', '--user'] and i+1 < len(sys.argv):
            username = sys.argv[i+1]
            i += 2
        elif sys.argv[i] in ['-p', '--password'] and i+1 < len(sys.argv):
            password = sys.argv[i+1]
            i += 2
        elif sys.argv[i] in ['-t', '--topic'] and i+1 < len(sys.argv):
            topic = sys.argv[i+1]
            i += 2
        else:
            i += 1

    if mode == "pub":
        run_publisher(username, password, topic)
    elif mode == "sub":
        run_subscriber(username, password, topic)
    else:
        logger.error(f"[錯誤] 未知模式: {mode}")
        print_usage()
        sys.exit(1)
