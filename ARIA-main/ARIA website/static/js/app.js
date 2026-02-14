/* ARIA Smart Home Dashboard — Core JS */

document.addEventListener("DOMContentLoaded", () => {
    const navLinks = document.querySelectorAll(".nav-link");
    const pages = document.querySelectorAll(".page");
    const pageTitle = document.getElementById("pageTitle");
    const menuToggle = document.getElementById("menuToggle");
    const sidebar = document.querySelector(".sidebar");
    const chatMessages = document.getElementById("chatMessages");
    const chatInput = document.getElementById("chatInput");
    const chatSend = document.getElementById("chatSend");
    const toastContainer = document.getElementById("toastContainer");

    // Mobile overlay
    const overlay = document.createElement("div");
    overlay.className = "sidebar-overlay";
    document.body.appendChild(overlay);

    // ═══════════════════════ THEME TOGGLE ═══════════════════════

    const themeToggle = document.getElementById("themeToggle");
    const themeIcon = document.getElementById("themeIcon");

    function setTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        themeIcon.textContent = theme === "light" ? "dark_mode" : "light_mode";
        localStorage.setItem("aria-theme", theme);
    }

    // Load saved theme or default to dark
    const savedTheme = localStorage.getItem("aria-theme") || "dark";
    setTheme(savedTheme);

    themeToggle.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme");
        setTheme(current === "light" ? "dark" : "light");
    });

    // ═══════════════════════ i18n TRANSLATIONS ═══════════════════════

    let currentLang = "EN";

    const translations = {
        EN: {
            // Navigation
            nav_dashboard: "Dashboard",
            nav_camera: "Camera",
            nav_functions: "Functions",
            nav_settings: "Settings",
            // Status
            status_online: "Online",
            status_offline: "Offline",
            server_online: "Server: Online",
            server_offline: "Server: Offline",
            // Dashboard
            quick_actions: "Quick Actions",
            light_onoff: "Light On/Off",
            call_robot: "Call Robot",
            status_ready: "Ready",
            status_active: "Active",
            status_processing: "Processing...",
            status_error: "Error",
            ai_chat: "AI Interaction Chat",
            chat_placeholder: "Type a message...",
            // Camera
            live_stream: "Live Stream",
            camera_unavailable: "Camera feed not available",
            // Functions
            youtube_music: "YouTube Music",
            music_integration: "Music integration",
            weather: "Weather",
            weather_widget: "Weather widget",
            email: "Email",
            email_integration: "Email integration",
            // Settings
            context_memory: "Context Memory",
            memory_placeholder: "Add a memory entry...",
            model_settings: "Model Settings",
            model_label: "Model",
            api_key_label: "API Key",
            save_settings: "Save Settings",
            language: "Language",
            // Toasts
            toast_lights_toggled: "Lights toggled",
            toast_robot_called: "Robot called",
            toast_action_failed: "Action failed",
            toast_settings_saved: "Settings saved",
            toast_save_failed: "Save failed",
            toast_cannot_connect: "Cannot connect",
            toast_added: "Added",
            toast_removed: "Removed",
            toast_failed_add: "Failed to add",
            toast_failed_delete: "Failed to delete",
            toast_lang_changed: "Language changed to",
            // Chat
            chat_label_you: "You",
            chat_label_aria: "ARIA",
            chat_error: "Something went wrong.",
            chat_no_server: "Cannot connect to server.",
            // Camera directions
            cam_up: "Camera: Up",
            cam_down: "Camera: Down",
            cam_left: "Camera: Left",
            cam_right: "Camera: Right",
            cam_center: "Camera: Center",
        },
        RU: {
            nav_dashboard: "Главная",
            nav_camera: "Камера",
            nav_functions: "Функции",
            nav_settings: "Настройки",
            status_online: "В сети",
            status_offline: "Не в сети",
            server_online: "Сервер: В сети",
            server_offline: "Сервер: Не в сети",
            quick_actions: "Быстрые действия",
            light_onoff: "Свет Вкл/Выкл",
            call_robot: "Вызвать робота",
            status_ready: "Готов",
            status_active: "Активен",
            status_processing: "Обработка...",
            status_error: "Ошибка",
            ai_chat: "AI Чат",
            chat_placeholder: "Введите сообщение...",
            live_stream: "Прямая трансляция",
            camera_unavailable: "Камера недоступна",
            youtube_music: "YouTube Музыка",
            music_integration: "Интеграция музыки",
            weather: "Погода",
            weather_widget: "Виджет погоды",
            email: "Почта",
            email_integration: "Интеграция почты",
            context_memory: "Контекстная память",
            memory_placeholder: "Добавить запись...",
            model_settings: "Настройки модели",
            model_label: "Модель",
            api_key_label: "API Ключ",
            save_settings: "Сохранить",
            language: "Язык",
            toast_lights_toggled: "Свет переключён",
            toast_robot_called: "Робот вызван",
            toast_action_failed: "Ошибка действия",
            toast_settings_saved: "Настройки сохранены",
            toast_save_failed: "Ошибка сохранения",
            toast_cannot_connect: "Нет подключения",
            toast_added: "Добавлено",
            toast_removed: "Удалено",
            toast_failed_add: "Ошибка добавления",
            toast_failed_delete: "Ошибка удаления",
            toast_lang_changed: "Язык изменён на",
            chat_label_you: "Вы",
            chat_label_aria: "ARIA",
            chat_error: "Что-то пошло не так.",
            chat_no_server: "Нет подключения к серверу.",
            cam_up: "Камера: Вверх",
            cam_down: "Камера: Вниз",
            cam_left: "Камера: Влево",
            cam_right: "Камера: Вправо",
            cam_center: "Камера: Центр",
        },
        KZ: {
            nav_dashboard: "Басты бет",
            nav_camera: "Камера",
            nav_functions: "Функциялар",
            nav_settings: "Баптаулар",
            status_online: "Онлайн",
            status_offline: "Офлайн",
            server_online: "Сервер: Онлайн",
            server_offline: "Сервер: Офлайн",
            quick_actions: "Жылдам әрекеттер",
            light_onoff: "Жарық Қосу/Өшіру",
            call_robot: "Роботты шақыру",
            status_ready: "Дайын",
            status_active: "Белсенді",
            status_processing: "Өңделуде...",
            status_error: "Қате",
            ai_chat: "AI Чат",
            chat_placeholder: "Хабарлама жазыңыз...",
            live_stream: "Тікелей эфир",
            camera_unavailable: "Камера қол жетімсіз",
            youtube_music: "YouTube Музыка",
            music_integration: "Музыка интеграциясы",
            weather: "Ауа райы",
            weather_widget: "Ауа райы виджеті",
            email: "Пошта",
            email_integration: "Пошта интеграциясы",
            context_memory: "Контекстік жады",
            memory_placeholder: "Жазба қосу...",
            model_settings: "Модель баптаулары",
            model_label: "Модель",
            api_key_label: "API Кілт",
            save_settings: "Сақтау",
            language: "Тіл",
            toast_lights_toggled: "Жарық ауыстырылды",
            toast_robot_called: "Робот шақырылды",
            toast_action_failed: "Әрекет қатесі",
            toast_settings_saved: "Баптаулар сақталды",
            toast_save_failed: "Сақтау қатесі",
            toast_cannot_connect: "Қосылу мүмкін емес",
            toast_added: "Қосылды",
            toast_removed: "Жойылды",
            toast_failed_add: "Қосу қатесі",
            toast_failed_delete: "Жою қатесі",
            toast_lang_changed: "Тіл өзгертілді:",
            chat_label_you: "Сіз",
            chat_label_aria: "ARIA",
            chat_error: "Бірдеңе дұрыс болмады.",
            chat_no_server: "Серверге қосылу мүмкін емес.",
            cam_up: "Камера: Жоғары",
            cam_down: "Камера: Төмен",
            cam_left: "Камера: Солға",
            cam_right: "Камера: Оңға",
            cam_center: "Камера: Ортаға",
        }
    };

    function t(key) {
        return (translations[currentLang] && translations[currentLang][key]) || translations.EN[key] || key;
    }

    function applyLanguage(lang) {
        currentLang = lang;
        document.documentElement.lang = lang.toLowerCase();

        // Update all elements with data-i18n (text content)
        document.querySelectorAll("[data-i18n]").forEach(el => {
            el.textContent = t(el.dataset.i18n);
        });

        // Update all elements with data-i18n-placeholder (input placeholders)
        document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
            el.placeholder = t(el.dataset.i18nPlaceholder);
        });

        // Update the page title to match the currently active nav
        const activePage = document.querySelector(".nav-link.active");
        if (activePage) {
            const pageKey = `nav_${activePage.dataset.page}`;
            pageTitle.textContent = t(pageKey);
            pageTitle.dataset.i18n = pageKey;
        }

        // Update browser title
        document.title = `ARIA — ${t("nav_dashboard")}`;
    }

    // ─── Navigation ───
    function navigateTo(pageName) {
        navLinks.forEach(l => l.classList.remove("active"));
        const active = document.querySelector(`.nav-link[data-page="${pageName}"]`);
        if (active) active.classList.add("active");
        pages.forEach(p => p.classList.remove("active"));
        const target = document.getElementById(`page-${pageName}`);
        if (target) target.classList.add("active");
        const titleKey = `nav_${pageName}`;
        pageTitle.textContent = t(titleKey);
        pageTitle.dataset.i18n = titleKey;
        sidebar.classList.remove("open");
        overlay.classList.remove("show");
    }

    navLinks.forEach(link => {
        link.addEventListener("click", (e) => { e.preventDefault(); navigateTo(link.dataset.page); });
    });
    menuToggle.addEventListener("click", () => { sidebar.classList.toggle("open"); overlay.classList.toggle("show"); });
    overlay.addEventListener("click", () => { sidebar.classList.remove("open"); overlay.classList.remove("show"); });

    // ─── Toast ───
    function showToast(message, type = "info") {
        const icons = { success: "check_circle", error: "error", info: "info" };
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span class="material-icons-round" style="font-size:18px">${icons[type] || "info"}</span>${message}`;
        toastContainer.appendChild(toast);
        setTimeout(() => { toast.classList.add("toast-exit"); setTimeout(() => toast.remove(), 300); }, 3000);
    }

    // ─── Chat ───
    function addChatBubble(role, text) {
        const bubble = document.createElement("div");
        bubble.className = `chat-bubble ${role}`;
        const label = role === "user" ? t("chat_label_you") : t("chat_label_aria");
        bubble.innerHTML = `<span class="chat-bubble-label">${label}</span>${escapeHtml(text)}`;
        chatMessages.appendChild(bubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function showTyping() {
        const el = document.createElement("div");
        el.className = "typing-indicator"; el.id = "typingIndicator";
        el.innerHTML = `<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>`;
        chatMessages.appendChild(el);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function removeTyping() { const el = document.getElementById("typingIndicator"); if (el) el.remove(); }

    async function sendMessage() {
        const text = chatInput.value.trim();
        if (!text) return;
        addChatBubble("user", text);
        chatInput.value = "";
        showTyping();
        try {
            const resp = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text }) });
            removeTyping();
            if (resp.ok) { const data = await resp.json(); addChatBubble("assistant", data.reply); }
            else addChatBubble("assistant", t("chat_error"));
        } catch { removeTyping(); addChatBubble("assistant", t("chat_no_server")); }
    }

    chatSend.addEventListener("click", sendMessage);
    chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); sendMessage(); } });

    // ─── Quick Actions ───
    document.querySelectorAll(".action-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
            const action = btn.dataset.action;
            const status = btn.querySelector(".action-status");
            status.textContent = t("status_processing");
            status.style.color = "var(--warning)";
            // Remove the i18n key while processing
            status.dataset.i18n = "status_processing";
            try {
                const resp = await fetch("/api/quick-action", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }) });
                if (resp.ok) {
                    const data = await resp.json();
                    btn.classList.toggle("active-state");
                    const isActive = btn.classList.contains("active-state");
                    status.textContent = isActive ? t("status_active") : t("status_ready");
                    status.dataset.i18n = isActive ? "status_active" : "status_ready";
                    status.style.color = isActive ? "var(--success)" : "var(--text-muted)";
                    const toastKey = action === "light" ? "toast_lights_toggled" : "toast_robot_called";
                    showToast(t(toastKey), "success");
                }
            } catch {
                status.textContent = t("status_error");
                status.dataset.i18n = "status_error";
                status.style.color = "var(--danger)";
                showToast(t("toast_action_failed"), "error");
            }
        });
    });

    // ─── Context Memory ───
    const memoryList = document.getElementById("memoryList");
    const memoryInput = document.getElementById("memoryInput");
    const memoryAddBtn = document.getElementById("memoryAddBtn");

    function renderMemory(items) {
        memoryList.innerHTML = "";
        items.forEach((item, i) => {
            const el = document.createElement("div"); el.className = "memory-item";
            el.innerHTML = `<span class="material-icons-round memory-item-icon">memory</span><span class="memory-item-text">${escapeHtml(item.text)}</span><button class="memory-delete-btn" data-index="${i}"><span class="material-icons-round" style="font-size:18px">close</span></button>`;
            memoryList.appendChild(el);
        });
        memoryList.querySelectorAll(".memory-delete-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                try {
                    const resp = await fetch(`/api/memory/${btn.dataset.index}`, { method: "DELETE" });
                    if (resp.ok) { renderMemory((await resp.json()).memory); showToast(t("toast_removed"), "info"); }
                } catch { showToast(t("toast_failed_delete"), "error"); }
            });
        });
    }

    async function loadMemory() {
        try { const resp = await fetch("/api/memory"); if (resp.ok) renderMemory((await resp.json()).memory); } catch {}
    }
    loadMemory();

    memoryAddBtn.addEventListener("click", addMemoryEntry);
    memoryInput.addEventListener("keydown", (e) => { if (e.key === "Enter") addMemoryEntry(); });

    async function addMemoryEntry() {
        const text = memoryInput.value.trim(); if (!text) return;
        try {
            const resp = await fetch("/api/memory", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
            if (resp.ok) { renderMemory((await resp.json()).memory); memoryInput.value = ""; showToast(t("toast_added"), "success"); }
        } catch { showToast(t("toast_failed_add"), "error"); }
    }

    // ─── Model Settings ───
    const modelSelect = document.getElementById("modelSelect");
    const apiKeyInput = document.getElementById("apiKeyInput");
    const toggleApiKey = document.getElementById("toggleApiKey");
    const saveSettingsBtn = document.getElementById("saveSettingsBtn");

    toggleApiKey.addEventListener("click", () => {
        const icon = toggleApiKey.querySelector(".material-icons-round");
        apiKeyInput.type = apiKeyInput.type === "password" ? "text" : "password";
        icon.textContent = apiKeyInput.type === "password" ? "visibility" : "visibility_off";
    });

    saveSettingsBtn.addEventListener("click", async () => {
        const payload = { model: modelSelect.value };
        if (apiKeyInput.value) payload.api_key = apiKeyInput.value;
        try {
            const resp = await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
            showToast(resp.ok ? t("toast_settings_saved") : t("toast_save_failed"), resp.ok ? "success" : "error");
        } catch { showToast(t("toast_cannot_connect"), "error"); }
    });

    async function loadSettings() {
        try {
            const resp = await fetch("/api/settings");
            if (resp.ok) {
                const d = await resp.json();
                modelSelect.value = d.model;
                // Apply the saved language
                if (d.language && translations[d.language]) {
                    currentLang = d.language;
                    document.querySelectorAll(".lang-btn").forEach(b => {
                        b.classList.toggle("active", b.dataset.lang === d.language);
                    });
                    applyLanguage(d.language);
                }
            }
        } catch {}
    }
    loadSettings();

    // ─── Language ───
    document.querySelectorAll(".lang-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
            document.querySelectorAll(".lang-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            const lang = btn.dataset.lang;
            applyLanguage(lang);
            showToast(`${t("toast_lang_changed")} ${lang}`, "info");
            try {
                await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ language: lang }) });
            } catch {}
        });
    });

    // ─── Server Status ───
    async function checkStatus() {
        const dots = document.querySelectorAll(".status-dot");
        const badge = document.getElementById("serverBadge");
        try {
            const resp = await fetch("/api/server-status");
            if (resp.ok) {
                dots.forEach(d => { d.classList.add("online"); d.classList.remove("offline"); });
                if (badge) badge.querySelector("span:last-child").textContent = t("server_online");
            }
        } catch {
            dots.forEach(d => { d.classList.remove("online"); d.classList.add("offline"); });
            if (badge) badge.querySelector("span:last-child").textContent = t("server_offline");
        }
    }
    setInterval(checkStatus, 15000);

    // ─── D-Pad ───
    document.querySelectorAll(".dpad-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const map = { "dpad-up": "cam_up", "dpad-down": "cam_down", "dpad-left": "cam_left", "dpad-right": "cam_right", "dpad-center": "cam_center" };
            for (const [cls, key] of Object.entries(map)) {
                if (btn.classList.contains(cls)) { showToast(t(key), "info"); break; }
            }
        });
    });

    // ─── Helpers ───
    function escapeHtml(text) { const d = document.createElement("div"); d.textContent = text; return d.innerHTML; }
});
