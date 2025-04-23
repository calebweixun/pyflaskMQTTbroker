# Python MQTT Broker with Web Admin Interface

一個基於 Python 實現的 MQTT Broker，包含 Web 管理介面，支持通過配置文件和用戶文件進行設置。

## 技術棧

### 核心技術

- Python 3.7+
- MQTT 協議
- Flask Web 框架
- WebSocket 即時通訊

### 主要套件

- paho-mqtt: MQTT 客戶端實現
- aiorun: 異步運行支持
- pymongo: MongoDB 數據庫支持
- netifaces: 網絡接口管理
- Flask: Web 框架
- Flask-SocketIO: WebSocket 支持
- eventlet: 異步網絡庫
- python-dotenv: 環境變量管理

### 前端技術

- HTML5
- CSS3
- JavaScript
- Bootstrap (用於響應式設計)
- Socket.IO 客戶端

## 功能特點

- 純 Python 實現的 MQTT Broker
- 內建 Web 管理介面
- 支持基本的 MQTT 連接、發布/訂閱功能
- 內置用戶認證和權限控制
- 支持多客戶端並發連接
- 支持主題通配符（+ 和 #）
- 實時狀態監控和日誌查看
- 通過配置文件進行設置
- 從用戶文件加載用戶信息
- 支持系統狀態監控
- 支持動態配置更新

## 系統需求

- Python 3.7 或更高版本
- 支援的作業系統：Windows、Linux、macOS

## 安裝

1. 克隆專案：

```bash
git clone https://github.com/calebweixun/pyflaskMQTTbroker.git
cd pyflaskMQTTbroker
```

2. 安裝必要的依賴：

```bash
pip install -r requirements.txt
```

## 快速開始

### 啟動 MQTT Broker

```bash
python mqtt_broker.py
```

### 啟動 Web 管理介面

```bash
python web_admin.py
```

啟動後，可以通過瀏覽器訪問 `http://localhost:5000` 來使用 Web 管理介面。

## 配置文件說明

### config.json

包含 MQTT Broker 的基本配置：

```json
{
    "broker": {
        "host": "0.0.0.0",
        "port": 1883,
        "connection_timeout": 60,
        "max_connections": 100
    },
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s - [%(levelname)s] - %(message)s"
    },
    "mqtt": {
        "allow_anonymous": false,
        "keep_alive": 60,
        "max_packet_size": 2048
    }
}
```

### users.json

包含用戶認證信息和權限：

```json
{
    "users": [
        {
            "username": "user",
            "password": "password",
            "permissions": ["read", "write"]
        },
        {
            "username": "admin",
            "password": "admin123",
            "permissions": ["read", "write", "admin"]
        }
    ]
}
```

## Web 管理介面功能

- 即時監控 MQTT Broker 狀態
- 查看連接的客戶端
- 查看主題訂閱情況
- 查看系統日誌
- 管理用戶帳號
- 修改系統配置
- 啟動/停止 Broker 服務

## 使用範例

### 使用 MQTT 客戶端

```bash
# 訂閱主題
python mqtt_client.py sub -u user -p password -t test/topic

# 發布消息
python mqtt_client.py pub -u admin -p admin123 -t control/lights -m "on"
```

## 專案結構

```
pyflaskMQTTbroker/
├── mqtt_broker.py      # MQTT Broker 主程式
├── web_admin.py        # Web 管理介面
├── mqtt_client.py      # MQTT 客戶端工具
├── config.json         # Broker 配置文件
├── users.json          # 用戶認證文件
├── requirements.txt    # 依賴套件列表
├── static/             # 靜態資源文件
└── templates/          # HTML 模板文件
```

## 安全注意事項

1. 請務必修改默認的用戶名和密碼
2. 在生產環境中建議使用更強的密碼
3. 可以通過配置文件禁用匿名訪問
4. 建議在生產環境中使用 TLS/SSL 加密

## 貢獻指南

歡迎提交 Pull Request 或報告問題。在提交之前，請確保：

1. 代碼符合 PEP 8 規範
2. 添加適當的註釋
3. 更新相關文檔
4. 測試所有修改的功能

## 授權

本專案採用 MIT 授權條款。詳見 [LICENSE](LICENSE) 文件。

## 聯絡方式

如有任何問題或建議，請通過 GitHub Issues 提交。
