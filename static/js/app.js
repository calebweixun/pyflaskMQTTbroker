// 全局變量
let socket;
let broker_status = 'stopped';
let topics = {};
let clients = {};
let messages = {};

// 每個主題最大消息數
const MESSAGE_MAX_COUNT = 100;

// 滾動消息容器到底部
function scrollMessagesToBottom() {
    const container = $('#message-content');
    container.scrollTop(container[0].scrollHeight);
}

// 初始化頁面
$(document).ready(function () {
    // 連接到Socket.IO
    socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port);

    // 設置Socket事件
    setupSocketEvents();

    // 設置UI事件
    setupUIEvents();

    // 加載初始數據
    loadInitialData();

    // 默認顯示儀表板
    $('.sidebar .nav-link[href="#dashboard"]').click();

    // 更新當前時間
    updateCurrentTime();

    // 每秒更新一次時間
    setInterval(updateCurrentTime, 1000);

    // 響應式側邊欄控制
    setupResponsiveSidebar();

    // 在初始化時設置日誌滾動
    setupLogScrolling();
});

// 設置Socket.IO事件監聽
function setupSocketEvents() {
    // 接收初始配置
    socket.on('init_config', function (data) {
        $('#broker-host').val(data.broker.host);
        $('#broker-port').val(data.broker.port);
        $('#keep-alive').val(data.mqtt.keep_alive);
        $('#max-connections').val(data.broker.max_connections);
        $('#allow-anonymous').prop('checked', data.mqtt.allow_anonymous);
    });

    // 日誌監聽（處理 init_logs 事件）
    socket.on('init_logs', function (data) {
        $('#log-content').empty();
        $('#dashboard-logs').empty();
        // 支持 data.logs 或直接 data 作為日誌陣列
        const logs = Array.isArray(data.logs) ? data.logs : (Array.isArray(data) ? data : []);
        logs.forEach(function (log) {
            addLogEntry(log.time, log.level, log.message);
        });
        scrollLogsToBottom();
    });

    // 接收新日誌 (後端統一推送 log_update)
    socket.on('log_update', function (data) {
        addLogEntry(data.time, data.level, data.message);
        scrollLogsToBottom();
    });

    // 監聽初始化消息列表
    socket.on('init_messages', function (data) {
        messages = data || {};
        updateMessagesDisplay();
        // 限制每個主題數量
        Object.keys(messages).forEach(function (topic) {
            if (messages[topic].length > MESSAGE_MAX_COUNT) {
                messages[topic] = messages[topic].slice(-MESSAGE_MAX_COUNT);
            }
        });
        updateMessagesCount();
        scrollMessagesToBottom();
    });

    // 監聽後端推送的新消息
    socket.on('message_update', function (data) {
        // 檢查並初始化主題
        if (!topics[data.topic]) {
            topics[data.topic] = 1;
            // 只有在沒有選中主題時才更新主題列表
            if (!$('.topic-item.active').length) {
                updateTopicsList();
            } else {
                // 只添加新主題到列表
                addNewTopicToList(data.topic, 1);
            }
        } else {
            topics[data.topic]++;
            // 只更新計數器，不重新渲染整個列表
            updateTopicCount(data.topic, topics[data.topic]);
        }

        // 處理消息
        if (!messages[data.topic]) {
            messages[data.topic] = [];
        }

        // 添加新消息
        let newMessage = {
            time: data.time || new Date().toLocaleTimeString('zh-TW'),
            message: data.payload || data.message,
            qos: data.qos || 0
        };

        messages[data.topic].push(newMessage);

        // 限制消息數量
        if (messages[data.topic].length > 100) {
            messages[data.topic] = messages[data.topic].slice(-100);
        }

        // 更新顯示
        updateTopicMessages(data.topic);
        updateMessagesCount();
        updateTopicsCount();
    });

    // 監聽客戶端初始化列表
    socket.on('init_clients', function (data) {
        clients = data || {};
        updateClientsDisplay();
        updateClientsCount();
    });

    // 監聽客戶端更新
    socket.on('client_update', function (data) {
        clients = data || {};
        updateClientsDisplay();
        updateClientsCount();
    });

    // 客戶端連接
    socket.on('client_connected', function (data) {
        clients[data.client_id] = data;
        updateClientsDisplay();
        updateClientsCount();
    });

    // 客戶端斷開
    socket.on('client_disconnected', function (data) {
        delete clients[data.client_id];
        updateClientsDisplay();
        updateClientsCount();
    });

    // 監聽主題更新
    socket.on('init_topics', function (data) {
        topics = data.topics || {};
        updateTopicsList();
        updateTopicsCount();
    });

    // 新主題
    socket.on('new_topic', function (data) {
        topics[data.topic] = data.count || 1;
        updateTopicsList();
        updateTopicsCount();
    });

    // 主題消息更新
    socket.on('topic_message', function (data) {
        if (!messages[data.topic]) {
            messages[data.topic] = [];
        }
        messages[data.topic].push({
            time: data.time,
            message: data.message,
            qos: data.qos
        });
        if (messages[data.topic].length > 100) {
            messages[data.topic] = messages[data.topic].slice(-100);
        }
        updateTopicMessages(data.topic);
        updateMessagesCount();
    });

    // 初始化消息
    socket.on('init_messages', function (data) {
        messages = data || {};
        updateTopicMessages($('.topic-item.active').data('topic'));
        updateMessagesCount();
    });

    // 統計資訊更新，用於初始和持續的狀態及統計
    socket.on('stats_update', function (data) {
        // 更新全局狀態
        broker_status = data.running ? 'running' : 'stopped';
        updateBrokerStatus();
        updateStats(data);
    });

    // 系統資訊更新
    socket.on('system_info', function (data) {
        updateSystemInfo(data);
    });

    // 用戶列表更新
    socket.on('users_updated', function (data) {
        updateUsersTable(data.users);
    });
}

// 設置UI交互事件
function setupUIEvents() {
    // 標籤切換
    $('.sidebar .nav-link').on('click', function (e) {
        e.preventDefault();
        // 移除所有nav-link的active類
        $('.sidebar .nav-link').removeClass('active');
        // 添加active類到當前點擊的元素
        $(this).addClass('active');

        // 隱藏所有內容部分
        $('.tab-pane').removeClass('show active').hide();

        // 顯示目標內容
        const target = $(this).attr('href');
        $(target).addClass('show active').show();
    });

    // Broker控制按鈕
    $('#start-broker').click(function () {
        $.getJSON('/api/broker/start', function (res) {
            if (res.success) {
                broker_status = 'running';
                updateBrokerStatus();
            } else {
                // 顯示後端返回的錯誤訊息
                const err = res.error || '未知錯誤';
                alert(`啟動失敗: ${err}`);
            }
        }).fail(function (jqXHR, textStatus, errorThrown) {
            alert(`啟動請求失敗: ${textStatus}`);
        });
    });

    $('#stop-broker').click(function () {
        $.getJSON('/api/broker/stop', function (res) {
            if (res.success) {
                broker_status = 'stopped';
                updateBrokerStatus();
            } else {
                const err = res.error || '未知錯誤';
                alert(`停止失敗: ${err}`);
            }
        }).fail(function (jqXHR, textStatus, errorThrown) {
            alert(`停止請求失敗: ${textStatus}`);
        });
    });

    $('#pause-broker').click(function () {
        $.getJSON('/api/broker/pause', function (res) {
            if (res.success) {
                broker_status = 'paused';
                updateBrokerStatus();
            } else {
                const err = res.error || '未知錯誤';
                alert(`暫停失敗: ${err}`);
            }
        }).fail(function (jqXHR, textStatus, errorThrown) {
            alert(`暫停請求失敗: ${textStatus}`);
        });
    });

    // 日誌相關控制
    $('#clear-logs').click(function () {
        socket.emit('clear_logs');
        $('#log-content').empty();
        $('#dashboard-logs').empty();
    });

    // 清除儀表板
    $('#clear-dashboard').click(function () {
        if (confirm('確定要清除所有儀表板資訊嗎？')) {
            // 重置統計數據
            $('#client-count').text('0');
            $('#topic-count').text('0');
            $('#message-count').text('0');
            $('#uptime').text('00:00:00');

            // 清空客戶端列表
            $('#recent-clients').empty();

            // 清空日誌
            $('#dashboard-logs').empty();

            // 清空系統資訊
            $('#ip-list').empty();

            // 清空主題訊息
            topics = {};
            messages = {};
            updateTopicsList();
            $('#topic-messages').empty();

            // 通知後端清除數據
            socket.emit('clear_dashboard');

            // 重新載入必要資訊
            $.getJSON('/api/system', function (data) {
                updateSystemInfo(data);
            });

            // 重新載入客戶端列表
            $.getJSON('/api/clients', function (data) {
                clients = data || {};
                updateClientsDisplay();
                updateClientsCount();
            });

            // 重新載入主題列表
            $.getJSON('/api/topics', function (data) {
                topics = data.topics || {};
                updateTopicsList();
                updateTopicsCount();
            });
        }
    });

    // 配置保存
    $('#save-config').click(function () {
        let config = {
            broker: {
                host: $('#broker-host').val(),
                port: parseInt($('#broker-port').val()),
                max_connections: parseInt($('#max-connections').val())
            },
            mqtt: {
                keep_alive: parseInt($('#keep-alive').val()),
                allow_anonymous: $('#allow-anonymous').prop('checked')
            }
        };
        $.ajax({
            url: '/api/config',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(config),
            success: function (res) {
                if (res.success) alert('保存成功');
                else alert('保存失敗');
            }
        });
    });

    // 用戶管理
    $('#save-new-user').click(function () {
        let newUser = {
            username: $('#new-username').val(),
            password: $('#new-password').val(),
            permissions: []
        };

        if ($('#perm-read').prop('checked')) {
            newUser.permissions.push('read');
        }
        if ($('#perm-write').prop('checked')) {
            newUser.permissions.push('write');
        }
        if ($('#perm-admin').prop('checked')) {
            newUser.permissions.push('admin');
        }

        socket.emit('add_user', newUser);
        $('#add-user-form')[0].reset();
        $('#addUserModal').modal('hide');
    });

    // 主題點擊事件
    $(document).on('click', '.topic-item', function (e) {
        e.preventDefault();
        $('.topic-item').removeClass('active');
        $(this).addClass('active');

        let topic = $(this).data('topic');
        updateTopicMessages(topic);
    });

    // 刪除用戶事件
    $(document).on('click', '.delete-user', function () {
        let username = $(this).data('username');
        if (confirm('確定要刪除用戶 "' + username + '" 嗎?')) {
            socket.emit('delete_user', { username: username });
        }
    });

    // 清空消息按鈕
    $('#clear-messages').click(function () {
        const topic = $('#selected-topic').text();
        if (topic && messages[topic]) {
            messages[topic] = [];
        }
        $('#message-content').empty();
        updateMessagesCount();
    });
}

// 響應式側邊欄設置
function setupResponsiveSidebar() {
    // 漢堡選單點擊事件
    $('.sidebar-toggle').click(function () {
        $('.sidebar').toggleClass('show');
    });

    // 點擊主內容區時關閉側邊欄（僅在小屏幕上）
    $('.main-content').click(function () {
        if ($(window).width() <= 768) {
            $('.sidebar').removeClass('show');
        }
    });

    // 監聽窗口大小變化
    $(window).resize(function () {
        if ($(window).width() > 768) {
            $('.sidebar').removeClass('show');
        }
    });
}

// 加載初始數據
function loadInitialData() {
    // 獲取初始統計信息
    $.getJSON('/api/stats', function (data) {
        broker_status = data.running ? 'running' : 'stopped';
        updateBrokerStatus();
        updateStats(data);
    });

    // 獲取配置
    $.getJSON('/api/config', function (data) {
        $('#broker-host').val(data.broker.host);
        $('#broker-port').val(data.broker.port);
        $('#keep-alive').val(data.mqtt.keep_alive);
        $('#max-connections').val(data.broker.max_connections);
        $('#allow-anonymous').prop('checked', data.mqtt.allow_anonymous);
    });

    // 獲取日誌
    $.getJSON('/api/logs', function (data) {
        $('#log-content').empty(); $('#dashboard-logs').empty();
        data.forEach(function (log) { addLogEntry(log.time, log.level, log.message); });
        scrollLogsToBottom();
    });

    // 獲取客戶端列表
    $.getJSON('/api/clients', function (data) {
        clients = data;
        updateClientsDisplay();
        updateClientsCount();
    });

    // 獲取主題列表
    $.getJSON('/api/topics', function (data) {
        topics = data.topics || {};
        updateTopicsTree();
        updateTopicsCount();
    });

    // 獲取消息列表
    $.getJSON('/api/messages', function (data) {
        messages = data;
        updateMessagesDisplay();
        updateMessagesCount();
    });

    // 獲取用戶列表
    $.getJSON('/api/users', function (data) {
        let usersObj = {};
        data.users.forEach(function (u) { usersObj[u.username] = u; });
        updateUsersTable(usersObj);
    });

    // 獲取系統信息
    $.getJSON('/api/system', function (data) {
        updateSystemInfo(data);
    });
}

// 添加日誌條目
function addLogEntry(time, level, message) {
    let logClass = 'log-info';
    if (level === 'ERROR') {
        logClass = 'log-error';
    } else if (level === 'WARNING') {
        logClass = 'log-warning';
    }

    let logEntry = $('<div class="log-entry"></div>');
    logEntry.append($('<span class="log-time"></span>').text(time));
    logEntry.append($('<span class="' + logClass + '"></span>').text(level + ': ' + message));

    // 檢查是否在底部
    let logContent = $('#log-content');
    let dashboardLogs = $('#dashboard-logs');
    let shouldScrollLogContent = isScrolledToBottom(logContent);
    let shouldScrollDashboard = isScrolledToBottom(dashboardLogs);

    // 添加到主日誌和儀表板日誌
    logContent.append(logEntry.clone());
    dashboardLogs.append(logEntry);

    // 如果之前在底部，則滾動到新內容
    if (shouldScrollLogContent) {
        scrollToBottom(logContent);
    }
    if (shouldScrollDashboard) {
        scrollToBottom(dashboardLogs);
    }

    // 限制儀表板日誌數量
    while ($('#dashboard-logs .log-entry').length > 100) {
        $('#dashboard-logs .log-entry:first').remove();
    }
}

// 檢查是否滾動到底部
function isScrolledToBottom(element) {
    if (element.length === 0) return true;
    let scrollHeight = element[0].scrollHeight;
    let scrollTop = element.scrollTop();
    let clientHeight = element.height();
    return Math.abs(scrollHeight - scrollTop - clientHeight) < 5;
}

// 滾動到底部
function scrollToBottom(element) {
    element.scrollTop(element[0].scrollHeight);
}

// 將日誌滾動到底部
function scrollLogsToBottom() {
    scrollToBottom($('#log-content'));
    scrollToBottom($('#dashboard-logs'));
}

// 設置自動滾動狀態
let autoScroll = {
    logContent: true,
    dashboardLogs: true,
    topicMessages: true
};

// 添加自動滾動切換按鈕
function addScrollToggle(containerId, property) {
    let container = $(`#${containerId}`);
    let toggleBtn = $('<button class="btn btn-sm btn-outline-secondary position-absolute top-0 end-0 m-2">自動滾動: 開</button>');

    container.parent().css('position', 'relative');
    container.parent().append(toggleBtn);

    toggleBtn.click(function () {
        autoScroll[property] = !autoScroll[property];
        $(this).text('自動滾動: ' + (autoScroll[property] ? '開' : '關'));
        if (autoScroll[property]) {
            scrollToBottom(container);
        }
    });

    // 添加滾動事件監聽器
    container.on('scroll', function () {
        // 如果用戶手動滾動到底部，則重新啟用自動滾動
        if (isScrolledToBottom(container)) {
            autoScroll[property] = true;
            toggleBtn.text('自動滾動: 開');
        }
    });

    // 定期檢查是否需要滾動
    setInterval(function () {
        if (autoScroll[property]) {
            scrollToBottom(container);
        }
    }, 1000);
}

// 設置日誌容器的滾動事件
function setupLogScrolling() {
    // 添加滾動切換按鈕
    addScrollToggle('log-content', 'logContent');
    addScrollToggle('dashboard-logs', 'dashboardLogs');
    addScrollToggle('topic-messages', 'topicMessages');
}

// 更新Broker狀態
function updateBrokerStatus() {
    $('.status-badge').removeClass('status-badge-stopped status-badge-running status-badge-paused');

    if (broker_status === 'running') {
        $('.status-badge').addClass('status-badge-running').text('運行中');
        $('#start-broker').attr('disabled', true);
        $('#stop-broker').attr('disabled', false);
        $('#pause-broker').attr('disabled', false);
    } else if (broker_status === 'paused') {
        $('.status-badge').addClass('status-badge-paused').text('已暫停');
        $('#start-broker').attr('disabled', false);
        $('#stop-broker').attr('disabled', false);
        $('#pause-broker').attr('disabled', true);
    } else {
        $('.status-badge').addClass('status-badge-stopped').text('已停止');
        $('#start-broker').attr('disabled', false);
        $('#stop-broker').attr('disabled', true);
        $('#pause-broker').attr('disabled', true);
    }
}

// 更新統計信息
function updateStats(data) {
    $('#client-count').text(data.connections || 0);
    $('#topic-count').text(data.active_topics || 0);
    $('#message-count').text(data.messages || 0);
    $('#uptime').text(formatUptime(data.uptime || 0));
}

// 更新系統信息
function updateSystemInfo(data) {
    // 更新IP地址列表
    $('#ip-list').empty();
    if (data.ip_addresses && data.ip_addresses.length > 0) {
        data.ip_addresses.forEach(function (item) {
            $('#ip-list').append($('<li></li>').text(item.interface + ': ' + item.ip));
        });
    } else {
        $('#ip-list').append($('<li></li>').text('無可用IP地址'));
    }
}

// 更新當前時間
function updateCurrentTime() {
    const now = new Date();
    const options = {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    };
    $('#current-time').text(now.toLocaleString('zh-TW', options));
}

// 格式化運行時間
function formatUptime(seconds) {
    if (!seconds || isNaN(seconds)) return '00:00:00';

    let hours = Math.floor(seconds / 3600);
    let minutes = Math.floor((seconds % 3600) / 60);
    let secs = Math.floor(seconds % 60);

    return [hours, minutes, secs]
        .map(v => v < 10 ? '0' + v : v)
        .join(':');
}

// 更新用戶表格
function updateUsersTable(users) {
    $('#user-list').empty();

    if (users && Object.keys(users).length > 0) {
        Object.keys(users).forEach(function (username) {
            let user = users[username];
            let permissions = user.permissions || [];

            let tr = $('<tr></tr>');
            tr.append($('<td></td>').text(username));
            tr.append($('<td></td>').text('******'));  // 不顯示實際密碼

            let permText = [];
            if (permissions.includes('read')) permText.push('讀取');
            if (permissions.includes('write')) permText.push('寫入');
            if (permissions.includes('admin')) permText.push('管理員');

            tr.append($('<td></td>').text(permText.join(', ') || '無'));

            let actionTd = $('<td></td>');
            let deleteButton = $('<button class="btn btn-sm btn-danger delete-user"></button>')
                .attr('data-username', username)
                .html('<i class="bi bi-trash"></i>');

            actionTd.append(deleteButton);
            tr.append(actionTd);

            $('#user-list').append(tr);
        });
    } else {
        $('#user-list').append('<tr><td colspan="4" class="text-center">尚無用戶</td></tr>');
    }
}

// 更新主題樹
function updateTopicsTree() {
    $('#topic-tree').empty();

    if (topics && Object.keys(topics).length > 0) {
        let tree = $('<ul class="tree"></ul>');

        Object.keys(topics).sort().forEach(function (topic) {
            let li = $('<li class="topic-item"></li>').attr('data-topic', topic);
            li.append($('<i class="bi bi-diagram-3 me-2"></i>'));
            li.append($('<span></span>').text(topic));
            li.append($('<span class="badge bg-info ms-2"></span>').text(topics[topic]));

            tree.append(li);
        });

        $('#topic-tree').append(tree);
    } else {
        $('#topic-tree').append('<div class="text-muted text-center">尚無活動主題</div>');
    }
}

// 更新主題數量
function updateTopicsCount() {
    $('#topic-count').text(Object.keys(topics).length || 0);
}

// 更新客戶端數量
function updateClientsCount() {
    $('#client-count').text(Object.keys(clients).length || 0);
}

// 更新消息數量
function updateMessagesCount() {
    let count = 0;
    Object.keys(messages).forEach(function (topic) {
        count += messages[topic].length;
    });
    $('#message-count').text(count);
}

// 更新客戶端顯示
function updateClientsDisplay() {
    // 更新客戶端列表
    $('#client-list').empty();
    $('#recent-clients').empty();

    if (clients && Object.keys(clients).length > 0) {
        // 排序客戶端，最新連接的在前面
        let sortedClients = Object.values(clients).sort((a, b) => {
            return new Date(b.connected_at) - new Date(a.connected_at);
        });

        sortedClients.forEach(function (client) {
            // 主客戶端列表
            let tr = $('<tr></tr>');
            tr.append($('<td></td>').text(client.client_id));
            tr.append($('<td></td>').text(client.username || '匿名'));
            tr.append($('<td></td>').text(client.connected_at));
            tr.append($('<td></td>').html('<span class="badge bg-success">已連接</span>'));

            let topicsList = $('<ul class="mb-0 ps-3"></ul>');
            if (client.subscriptions && client.subscriptions.length > 0) {
                client.subscriptions.forEach(function (sub) {
                    topicsList.append($('<li></li>').text(sub));
                });
            } else {
                topicsList.append($('<li></li>').text('無訂閱'));
            }
            tr.append($('<td></td>').append(topicsList));

            $('#client-list').append(tr);

            // 儀表板最近客戶端列表(只顯示前5個)
            if ($('#recent-clients tr').length < 5) {
                let recentTr = $('<tr></tr>');
                recentTr.append($('<td></td>').text(client.client_id));
                recentTr.append($('<td></td>').text(client.username || '匿名'));
                recentTr.append($('<td></td>').text(client.connected_at));
                recentTr.append($('<td></td>').html('<span class="badge bg-success">已連接</span>'));

                $('#recent-clients').append(recentTr);
            }
        });
    } else {
        $('#client-list').append('<tr><td colspan="5" class="text-center">尚無已連接的客戶端</td></tr>');
        $('#recent-clients').append('<tr><td colspan="4" class="text-center">尚無已連接的客戶端</td></tr>');
    }
}

// 更新消息顯示
function updateMessagesDisplay() {
    const topic = $('#selected-topic').text();
    if (topic && messages[topic]) {
        loadTopicMessages(topic);
        scrollMessagesToBottom();
    }
}

// 加載主題消息
function loadTopicMessages(topic) {
    $('#message-content').empty();

    if (messages[topic] && messages[topic].length > 0) {
        messages[topic].forEach(function (message) {
            addMessageToDisplay(message);
        });
    } else {
        $('#message-content').html(
            '<div class="text-center text-muted">此主題尚無消息</div>'
        );
    }
}

// 添加消息到顯示
function addMessageToDisplay(message) {
    let msgDiv = $('<div class="message-item"></div>');

    let header = $('<div class="message-header"></div>');
    header.append($('<span class="message-time"></span>').text(message.time));
    header.append($('<span class="message-qos"></span>').text('QoS: ' + (message.qos || 0)));

    msgDiv.append(header);

    let content = $('<div class="message-content"></div>');

    // 嘗試解析JSON
    try {
        let jsonContent = JSON.parse(message.payload);
        content.append($('<pre class="json-content"></pre>').text(JSON.stringify(jsonContent, null, 2)));
    } catch (e) {
        // 純文本
        content.append($('<div></div>').text(message.payload));
    }

    msgDiv.append(content);
    $('#message-content').append(msgDiv);
    scrollMessagesToBottom();
}

// 更新主題列表
function updateTopicsList() {
    // 保存當前選中的主題
    let selectedTopic = $('.topic-item.active').data('topic');

    $('#topic-list').empty();

    if (Object.keys(topics).length > 0) {
        // 按照主題名稱排序
        Object.keys(topics).sort().forEach(function (topic) {
            let count = topics[topic] || 0;
            let item = $('<a href="#" class="list-group-item list-group-item-action topic-item d-flex justify-content-between align-items-center"></a>')
                .attr('data-topic', topic);

            let content = $('<div class="d-flex justify-content-between align-items-center w-100"></div>');
            content.append($('<span class="topic-name"></span>').text(topic));
            content.append($('<span class="badge bg-primary rounded-pill"></span>').text(count));

            item.append(content);

            // 如果是當前選中的主題，添加active類
            if (topic === selectedTopic) {
                item.addClass('active');
            }

            $('#topic-list').append(item);
        });

        // 如果沒有選中的主題，且列表不為空，選中第一個主題
        if (!selectedTopic && !$('.topic-item.active').length) {
            $('#topic-list .topic-item:first').addClass('active');
            updateTopicMessages($('#topic-list .topic-item:first').data('topic'));
        }
    } else {
        $('#topic-list').append('<div class="text-center text-muted">尚無活動主題</div>');
    }
}

// 添加新主題到列表
function addNewTopicToList(topic, count) {
    if (!$('.topic-item[data-topic="' + topic + '"]').length) {
        let item = $('<a href="#" class="list-group-item list-group-item-action topic-item d-flex justify-content-between align-items-center"></a>')
            .attr('data-topic', topic);

        let content = $('<div class="d-flex justify-content-between align-items-center w-100"></div>');
        content.append($('<span class="topic-name"></span>').text(topic));
        content.append($('<span class="badge bg-primary rounded-pill"></span>').text(count));

        item.append(content);

        // 按照字母順序插入
        let inserted = false;
        $('#topic-list .topic-item').each(function () {
            if ($(this).data('topic') > topic) {
                item.insertBefore($(this));
                inserted = true;
                return false;
            }
        });

        // 如果沒有找到合適的位置，添加到末尾
        if (!inserted) {
            $('#topic-list').append(item);
        }
    }
}

// 更新特定主題的計數
function updateTopicCount(topic, count) {
    $('.topic-item[data-topic="' + topic + '"] .badge').text(count);
}

// 更新主題消息顯示
function updateTopicMessages(topic) {
    let activeTopic = $('.topic-item.active').data('topic');

    if (activeTopic === topic || (!activeTopic && topic)) {
        let container = $('#topic-messages');

        if (!activeTopic) {
            $(`.topic-item[data-topic="${topic}"]`).addClass('active');
        }

        // 檢查是否需要自動滾動
        let shouldScroll = autoScroll.topicMessages && isScrolledToBottom(container);

        container.empty();

        if (messages[topic] && messages[topic].length > 0) {
            messages[topic].forEach(function (msg) {
                let messageDiv = $('<div class="topic-message mb-2 p-2 border-bottom"></div>');

                let header = $('<div class="d-flex justify-content-between mb-1"></div>');
                header.append($('<small class="text-muted"></small>').text(msg.time));
                if (msg.qos !== undefined) {
                    header.append($('<small class="text-muted"></small>').text('QoS: ' + msg.qos));
                }

                messageDiv.append(header);
                messageDiv.append($('<div class="message-content"></div>').text(msg.message));

                container.append(messageDiv);
            });

            // 如果需要，滾動到底部
            if (shouldScroll) {
                scrollToBottom(container);
            }
        } else {
            container.append('<div class="text-center text-muted">此主題尚無消息</div>');
        }
    }
} 