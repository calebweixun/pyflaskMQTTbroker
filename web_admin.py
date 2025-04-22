#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import logging
import threading
import subprocess
import netifaces
from datetime import datetime
from collections import defaultdict
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO
import sys

# 配置文件路徑（使用絕對路徑）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
LOG_BUFFER_SIZE = 1000  # 最大日誌條目數
BROKER_PROCESS = None
BROKER_SCRIPT = os.path.join(BASE_DIR, 'mqtt_broker.py')

# 初始化 Flask 應用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'mqtt_broker_secret_key'
socketio = SocketIO(app)

# 日誌緩存
log_buffer = []
message_buffer = defaultdict(list)
clients_info = {}
topics_info = defaultdict(list)
broker_stats = {
    'start_time': None,
    'running': False,
    'uptime': 0,
    'messages': 0,
    'connections': 0,
    'active_topics': 0
}

# 日誌處理


class WebLogHandler(logging.Handler):
    def emit(self, record):
        global log_buffer
        log_entry = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': record.levelname,
            'message': self.format(record)
        }
        log_buffer.append(log_entry)
        if len(log_buffer) > LOG_BUFFER_SIZE:
            log_buffer = log_buffer[-LOG_BUFFER_SIZE:]
        socketio.emit('log_update', log_entry)

# 獲取系統信息


def get_system_info():
    ip_addresses = []
    try:
        for interface in netifaces.interfaces():
            if interface != 'lo':  # 跳過回環接口
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        ip_addresses.append({
                            'interface': interface,
                            'ip': addr['addr']
                        })
    except:
        pass

    return {
        'ip_addresses': ip_addresses,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

# 載入配置


def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        app.logger.error(f"無法載入配置文件: {e}")
        return {
            "broker": {"host": "0.0.0.0", "port": 1883, "max_connections": 100},
            "logging": {"level": "INFO", "format": "%(asctime)s - [%(levelname)s] - %(message)s"},
            "mqtt": {"allow_anonymous": False, "keep_alive": 60}
        }

# 保存配置


def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        app.logger.error(f"保存配置失敗: {e}")
        return False

# 載入用戶


def load_users():
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        app.logger.error(f"無法載入用戶文件: {e}")
        return {"users": [{"username": "user", "password": "password", "permissions": ["read", "write"]}]}

# 保存用戶


def save_users(users):
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=4)
        return True
    except Exception as e:
        app.logger.error(f"保存用戶失敗: {e}")
        return False

# 啟動 Broker


def start_broker():
    global BROKER_PROCESS, broker_stats
    if BROKER_PROCESS is None or BROKER_PROCESS.poll() is not None:
        try:
            # 配置日誌處理器
            web_handler = WebLogHandler()
            web_handler.setFormatter(logging.Formatter('%(message)s'))

            # 檢查 BROKER_SCRIPT 文件是否存在
            if not os.path.exists(BROKER_SCRIPT):
                app.logger.error(f"[錯誤] Broker 腳本文件 {BROKER_SCRIPT} 不存在")
                log_entry = {
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'level': 'ERROR',
                    'message': f"[錯誤] Broker 腳本文件 {BROKER_SCRIPT} 不存在"
                }
                log_buffer.append(log_entry)
                socketio.emit('log_update', log_entry)
                return False

            # 確保使用正確的 Python 解釋器
            python_exe = sys.executable if hasattr(
                sys, 'executable') else 'python'
            app.logger.info(f"使用 Python: {python_exe}")

            log_entry = {
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': f"[啟動] 嘗試啟動 MQTT Broker: {python_exe} {BROKER_SCRIPT}"
            }
            log_buffer.append(log_entry)
            socketio.emit('log_update', log_entry)

            # 啟動 Broker 進程
            BROKER_PROCESS = subprocess.Popen(
                [python_exe, BROKER_SCRIPT],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # 檢查進程是否成功啟動
            time.sleep(1)
            if BROKER_PROCESS.poll() is not None:
                # 進程已退出
                exit_code = BROKER_PROCESS.returncode
                error_output = BROKER_PROCESS.stdout.read() if BROKER_PROCESS.stdout else "無法獲取錯誤輸出"

                error_message = f"[錯誤] Broker 啟動失敗，退出碼: {exit_code}, 錯誤: {error_output}"
                app.logger.error(error_message)
                log_entry = {
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'level': 'ERROR',
                    'message': error_message
                }
                log_buffer.append(log_entry)
                socketio.emit('log_update', log_entry)
                BROKER_PROCESS = None
                return False

            # 更新狀態
            broker_stats['running'] = True
            broker_stats['start_time'] = time.time()

            # 啟動日誌讀取線程
            threading.Thread(target=read_broker_output, daemon=True).start()

            success_message = f"[成功] MQTT Broker 已成功啟動，PID: {BROKER_PROCESS.pid}"
            app.logger.info(success_message)
            log_entry = {
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': success_message
            }
            log_buffer.append(log_entry)
            socketio.emit('log_update', log_entry)

            return True
        except Exception as e:
            error_message = f"啟動 Broker 失敗: {str(e)}"
            app.logger.error(error_message)

            # 添加到日誌並發送到前端
            log_entry = {
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'ERROR',
                'message': error_message
            }
            log_buffer.append(log_entry)
            socketio.emit('log_update', log_entry)

            # 清理可能存在的進程
            if BROKER_PROCESS is not None:
                try:
                    BROKER_PROCESS.terminate()
                except:
                    pass
                BROKER_PROCESS = None

            return False
    else:
        app.logger.info("Broker 已經在運行中")
        log_entry = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': 'INFO',
            'message': "Broker 已經在運行中"
        }
        log_buffer.append(log_entry)
        socketio.emit('log_update', log_entry)
        return True

# 停止 Broker


def stop_broker():
    global BROKER_PROCESS, broker_stats
    if BROKER_PROCESS is not None and BROKER_PROCESS.poll() is None:
        try:
            BROKER_PROCESS.terminate()
            BROKER_PROCESS.wait(timeout=5)
            broker_stats['running'] = False
            broker_stats['uptime'] = 0
            return True
        except Exception as e:
            app.logger.error(f"停止 Broker 失敗: {e}")
            try:
                BROKER_PROCESS.kill()
            except:
                pass
            return False
    return True

# 暫停/恢復 Broker (僅模擬功能)


def toggle_pause_broker():
    # 這裡只是示意功能，實際需要修改 broker 代碼以支持暫停
    return True

# 更新 Broker 統計信息


def update_broker_stats():
    global broker_stats
    if broker_stats['running'] and broker_stats['start_time']:
        broker_stats['uptime'] = int(time.time() - broker_stats['start_time'])
        broker_stats['connections'] = len(clients_info)
        broker_stats['active_topics'] = len(topics_info)
    socketio.emit('stats_update', broker_stats)

# 從 Broker 讀取輸出


def read_broker_output():
    global BROKER_PROCESS

    if BROKER_PROCESS is None:
        return

    log_line_buffer = ""
    while BROKER_PROCESS.poll() is None:
        output = BROKER_PROCESS.stdout.readline()
        if output:
            log_line_buffer += output
            if log_line_buffer.endswith('\n'):
                process_log_line(log_line_buffer.strip())
                log_line_buffer = ""
        else:
            time.sleep(0.1)

    # 進程結束時的處理
    if log_line_buffer:
        process_log_line(log_line_buffer.strip())

    broker_stats['running'] = False
    BROKER_PROCESS = None

# 處理日誌行


def process_log_line(line):
    global log_buffer, message_buffer, broker_stats

    # 添加到日誌緩衝區
    log_entry = {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'level': 'INFO' if '[錯誤]' not in line else 'ERROR',
        'message': line
    }
    log_buffer.append(log_entry)
    if len(log_buffer) > LOG_BUFFER_SIZE:
        log_buffer = log_buffer[-LOG_BUFFER_SIZE:]

    # 發送到前端
    socketio.emit('log_update', log_entry)

    # 從日誌中解析信息
    if '[發布]' in line and '主題' in line:
        try:
            # 解析主題和消息 - 處理新格式 "[發布] 客戶端 X 發布到主題 'Y': Z"
            topic_start = line.find("'") if "'" in line else line.find('"')
            if topic_start < 0:
                return

            topic_end = line.find(
                "'", topic_start + 1) if "'" in line else line.find('"', topic_start + 1)
            if topic_end < 0:
                return

            topic = line[topic_start + 1:topic_end]

            # 從日誌中提取消息內容
            message_start = line.find(':', topic_end) + 1
            if message_start <= 0:
                return

            message = line[message_start:].strip()

            # 存儲消息
            message_data = {
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'topic': topic,
                'message': message
            }
            message_buffer[topic].append(message_data)
            if len(message_buffer[topic]) > 100:  # 每個主題最多保留100條消息
                message_buffer[topic] = message_buffer[topic][-100:]

            # 更新統計
            broker_stats['messages'] += 1

            # 發送到前端
            socketio.emit('message_update', message_data)
        except Exception as e:
            app.logger.error(f"處理消息日誌錯誤: {e}")

    # 解析客戶端連接信息
    elif '[認證]' in line and '連接成功' in line:
        try:
            # 從日誌中提取客戶端ID和用戶名
            parts = line.split('客戶端 ')[1].split(' (用戶: ')
            client_id = parts[0]
            username = parts[1].split(')')[0]

            # 更新客戶端信息
            clients_info[client_id] = {
                'id': client_id,
                'username': username,
                'connected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'active': True
            }

            # 發送到前端
            socketio.emit('client_update', clients_info)
        except Exception as e:
            app.logger.error(f"處理客戶端信息錯誤: {e}")

    # 解析客戶端斷開連接
    elif '[斷開]' in line and '客戶端' in line:
        try:
            parts = line.split('客戶端 ')[1].split(' 正常斷開')
            client_id = parts[0]

            if client_id in clients_info:
                clients_info[client_id]['active'] = False

            # 發送到前端
            socketio.emit('client_update', clients_info)
        except Exception as e:
            app.logger.error(f"處理客戶端斷開錯誤: {e}")

    # 解析訂閱信息
    elif '[訂閱]' in line and '訂閱主題' in line:
        try:
            parts = line.split('客戶端 ')[1].split(' 訂閱主題：')
            client_id = parts[0]
            topic = parts[1]

            if client_id not in topics_info[topic]:
                topics_info[topic].append(client_id)

            # 發送到前端
            socketio.emit('topic_update', {'topics': dict(topics_info)})
        except Exception as e:
            app.logger.error(f"處理訂閱信息錯誤: {e}")

# 定時更新 Broker 統計


def update_stats_periodically():
    while True:
        update_broker_stats()
        time.sleep(5)  # 每5秒更新一次

# 路由定義


@app.route('/')
def index():
    """主頁"""
    return render_template('index.html',
                           config=load_config(),
                           users=load_users(),
                           system_info=get_system_info(),
                           broker_stats=broker_stats)


@app.route('/api/logs')
def get_logs():
    """獲取日誌"""
    return jsonify(log_buffer)


@app.route('/api/messages')
def get_messages():
    """獲取所有消息"""
    return jsonify(message_buffer)


@app.route('/api/topics')
def get_topics():
    """獲取所有主題"""
    return jsonify({'topics': dict(topics_info)})


@app.route('/api/clients')
def get_clients():
    """獲取所有客戶端"""
    return jsonify(clients_info)


@app.route('/api/stats')
def get_stats():
    """獲取統計信息"""
    return jsonify(broker_stats)


@app.route('/api/config', methods=['GET', 'POST'])
def manage_config():
    """管理配置"""
    if request.method == 'GET':
        return jsonify(load_config())
    elif request.method == 'POST':
        try:
            config = request.json
            success = save_config(config)
            return jsonify({'success': success})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})


@app.route('/api/users', methods=['GET', 'POST'])
def manage_users():
    """管理用戶"""
    if request.method == 'GET':
        return jsonify(load_users())
    elif request.method == 'POST':
        try:
            users = request.json
            success = save_users(users)
            return jsonify({'success': success})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})


@app.route('/api/broker/start')
def api_start_broker():
    """啟動 Broker 並返回是否成功與錯誤信息"""
    try:
        success = start_broker()
        error_msg = None
        if not success and log_buffer:
            # 取最近一條錯誤信息
            last = log_buffer[-1]
            error_msg = last.get('message')
        return jsonify({'success': success, 'error': error_msg})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/broker/stop')
def api_stop_broker():
    """停止 Broker"""
    success = stop_broker()
    return jsonify({'success': success})


@app.route('/api/broker/pause')
def api_pause_broker():
    """暫停/恢復 Broker"""
    success = toggle_pause_broker()
    return jsonify({'success': success})


@app.route('/api/system')
def api_system_info():
    """獲取系統信息"""
    return jsonify(get_system_info())

# 啟動 SocketIO 事件


@socketio.on('connect')
def handle_connect():
    """處理客戶端連接"""
    socketio.emit('init_logs', log_buffer)
    socketio.emit('init_messages', message_buffer)
    socketio.emit('init_clients', clients_info)
    socketio.emit('init_topics', {'topics': dict(topics_info)})
    socketio.emit('stats_update', broker_stats)
    socketio.emit('init_config', load_config())
    # 推送系統信息（IP 地址等）
    socketio.emit('system_info', get_system_info())


@socketio.on('clear_dashboard')
def handle_clear_dashboard():
    """處理清除儀表板請求"""
    try:
        # 重置統計數據
        broker_stats = {
            'connections': 0,
            'active_topics': 0,
            'messages': 0,
            'uptime': 0
        }

        # 清空客戶端列表
        clients_info.clear()

        # 清空日誌
        log_buffer.clear()

        # 清空主題列表
        topics_info.clear()

        # 清空消息列表
        message_buffer.clear()

        # 通知所有客戶端更新
        socketio.emit('dashboard_cleared', {'success': True})

    except Exception as e:
        socketio.emit('dashboard_cleared', {'success': False, 'error': str(e)})


if __name__ == '__main__':
    # 啟動統計更新線程
    threading.Thread(target=update_stats_periodically, daemon=True).start()

    # 啟動 Web 服務器
    socketio.run(app, host='0.0.0.0', port=8083, debug=True)
