/* ARIA Smart Home Dashboard — Core JS */


function escapeHtml(unsafe) {
    return (unsafe || '').toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

document.addEventListener("DOMContentLoaded", () => {
    // Auto-play music on request
    async function playMusicByQuery(query) {
        if (!query) return;
        musicError.style.display = "none";
        musicTitle.textContent = "Поиск музыки...";
        try {
            const resp = await fetch("/api/play-music", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query })
            });
            const data = await resp.json();
            if (resp.ok && data.videoId) {
                // Load video
                if (player && typeof player.loadVideoById === "function") {
                    // Set autoplay flag
                    shouldAutoPlay = true;

                    player.loadVideoById(data.videoId);

                    // Show cover image
                    if (data.thumbnail) {
                        const coverImage = document.getElementById("coverImage");
                        const coverIcon = document.getElementById("coverIcon");
                        coverImage.src = data.thumbnail;
                        coverImage.style.display = "block";
                        coverIcon.style.display = "none";
                    }

                    // Update title
                    setTimeout(() => {
                        musicTitle.textContent = data.title || query;
                    }, 500);
                }
            } else {
                musicTitle.textContent = "Выберите трек или скажите команду";
                musicError.style.display = "block";
                musicError.textContent = data.error || "Видео не найдено";

                // Reset cover image
                const coverImage = document.getElementById("coverImage");
                const coverIcon = document.getElementById("coverIcon");
                coverImage.src = "";
                coverImage.style.display = "none";
                coverIcon.style.display = "block";
            }
        } catch (e) {
            musicTitle.textContent = "Выберите трек или скажите команду";
            musicError.style.display = "block";
            musicError.textContent = "Ошибка поиска видео: " + e.message;

            // Reset cover image
            const coverImage = document.getElementById("coverImage");
            const coverIcon = document.getElementById("coverIcon");
            coverImage.src = "";
            coverImage.style.display = "none";
            coverIcon.style.display = "block";
        }
    }
    // Global function for chat integration
    window.playMusicByQuery = playMusicByQuery;
    // ═══════════════════════ YOUTUBE MUSIC PLAYER ═══════════════════════
    let player = null;
    let isPlaying = false;

    const musicTitle = document.getElementById("musicTitle");
    const playPauseBtn = document.getElementById("playPause");
    const playPauseIcon = document.getElementById("playPauseIcon");
    const youtubePlayerContainer = document.getElementById("youtubePlayerContainer");
    const musicError = document.getElementById("musicError");

    // YouTube iframe container
    youtubePlayerContainer.innerHTML = '<div id="ytIframePlayer"></div>';

    function loadYouTubeAPI() {
        if (window.YT && window.YT.Player) {
            onYouTubeIframeAPIReady();
        } else {
            const tag = document.createElement('script');
            tag.src = "https://www.youtube.com/iframe_api";
            document.body.appendChild(tag);
            window.onYouTubeIframeAPIReady = onYouTubeIframeAPIReady;
        }
    }

    function onYouTubeIframeAPIReady() {
        player = new YT.Player('ytIframePlayer', {
            height: '300',
            width: '500',
            videoId: "",
            playerVars: { 'autoplay': 0, 'controls': 0 },
            events: {
                'onReady': onPlayerReady,
                'onStateChange': onPlayerStateChange,
                'onError': onPlayerError
            }
        });
    }

    function onPlayerReady(event) {
        // Player ready - auto-play if needed
        if (shouldAutoPlay) {
            player.playVideo();
        }
    }

    function onPlayerError(event) {
        // Handle video errors (blocked, not found, etc)
        console.log("YouTube Error Code:", event.data);
        musicError.style.display = "block";
        musicError.textContent = "❌ Видео недоступно (авторские права или географ. блокировка).";
    }

    let shouldAutoPlay = false;  // Auto-play flag

    function onPlayerStateChange(event) {
        // 1 = PLAYING, 2 = PAUSED, 3 = BUFFERING, 5 = CUED, 0 = ENDED
        if (event.data === YT.PlayerState.PLAYING) {
            musicError.style.display = "none";
            isPlaying = true;
            playPauseIcon.textContent = "pause";
        } else if (event.data === YT.PlayerState.PAUSED) {
            isPlaying = false;
            playPauseIcon.textContent = "play_arrow";
        } else if (event.data === YT.PlayerState.ENDED) {
            musicError.style.display = "block";
            musicError.textContent = "Трек завершён. Скажите следующий трек!";
        }
    }

    function updateTrackInfo() {
        if (player && typeof player.getVideoData === "function") {
            try {
                const data = player.getVideoData();
                if (data && data.title) {
                    musicTitle.textContent = data.title;
                }
            } catch (e) {
                //IgnoreError
            }
        }
    }

    function playTrack() {
        if (player) {
            player.playVideo();
            isPlaying = true;
            playPauseIcon.textContent = "pause";
        }
    }

    function pauseTrack() {
        if (player) {
            player.pauseVideo();
            isPlaying = false;
            playPauseIcon.textContent = "play_arrow";
        }
    }

    function rewind10s() {
        if (player && typeof player.getCurrentTime === "function" && typeof player.seekTo === "function") {
            const currentTime = player.getCurrentTime();
            const newTime = Math.max(0, currentTime - 10);  // Min 0
            player.seekTo(newTime);
        }
    }

    function forward10s() {
        if (player && typeof player.getCurrentTime === "function" && typeof player.getDuration === "function" && typeof player.seekTo === "function") {
            const currentTime = player.getCurrentTime();
            const duration = player.getDuration();
            const newTime = Math.min(duration, currentTime + 10);  // Max duration
            player.seekTo(newTime);
        }
    }

    if (playPauseBtn && youtubePlayerContainer) {
        loadYouTubeAPI();
        playPauseBtn.addEventListener("click", () => {
            if (isPlaying) pauseTrack();
            else playTrack();
        });

        // Rewind 10s button
        const rewindBtn = document.getElementById("rewindBtn");
        if (rewindBtn) {
            rewindBtn.addEventListener("click", rewind10s);
        }

        // Forward 10s button
        const forwardBtn = document.getElementById("forwardBtn");
        if (forwardBtn) {
            forwardBtn.addEventListener("click", forward10s);
        }
    }
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
            api_keys_status: "API Keys",
            save_settings: "Save Settings",
            personality: "AI Personality",
            persona_default: "Default",
            persona_chill: "Chill",
            persona_bro: "Bro",
            persona_angry: "Angry",
            persona_formal: "Formal",
            persona_pirate: "Pirate",
            persona_sassy: "Sassy",
            persona_nerd: "Nerd",
            toast_personality_changed: "Personality set to",
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
            api_keys_status: "API Ключи",
            save_settings: "Сохранить",
            personality: "Личность ИИ",
            persona_default: "Обычный",
            persona_chill: "Спокойный",
            persona_bro: "Братан",
            persona_angry: "Злой",
            persona_formal: "Формальный",
            persona_pirate: "Пират",
            persona_sassy: "Дерзкий",
            persona_nerd: "Ботан",
            toast_personality_changed: "Личность:",
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
            api_keys_status: "API Кілттер",
            save_settings: "Сақтау",
            personality: "AI Тұлғасы",
            persona_default: "Қалыпты",
            persona_chill: "Сабырлы",
            persona_bro: "Бро",
            persona_angry: "Ашулы",
            persona_formal: "Ресми",
            persona_pirate: "Қарақшы",
            persona_sassy: "Өжет",
            persona_nerd: "Нерд",
            toast_personality_changed: "Тұлға:",
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
        if (pageName === "camera" && !cameraIp) discoverCamera();
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

        // Check for music play command
        const musicCommands = ["включи", "play", "запусти", "воспроизведи"];
        const musicMatch = musicCommands.find(cmd => text.toLowerCase().startsWith(cmd));
        if (musicMatch) {
            let query = text.substring(musicMatch.length).trim();
            if (query) {
                // Send request (backend handles cover/remix search)
                playMusicByQuery(query);
            }
        }

        try {
            // Get current email if modal is open
            const modal = document.getElementById('emailDetailModal');
            let emailContent = null;
            if (modal && modal.style.display === 'flex') {
                // Extract email details from the modal
                const subject = document.getElementById('emailDetailSubject')?.textContent || '';
                const from = document.getElementById('emailDetailFrom')?.textContent || '';
                const to = document.getElementById('emailDetailTo')?.textContent || '';
                const date = document.getElementById('emailDetailDate')?.textContent || '';
                const body = document.getElementById('emailDetailBody')?.innerText || '';

                if (subject || from || body) {
                    emailContent = {
                        subject,
                        from,
                        to,
                        date,
                        body: body.substring(0, 5000) // Limit to 5000 chars to avoid token overflow
                    };
                }
            }

            const payload = { message: text };
            if (emailContent) {
                payload.email = emailContent;
            }

            const resp = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
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
        try { const resp = await fetch("/api/memory"); if (resp.ok) renderMemory((await resp.json()).memory); } catch { }
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
    const saveSettingsBtn = document.getElementById("saveSettingsBtn");
    const apiKeyCount = document.getElementById("apiKeyCount");
    const apiKeyBadge = document.getElementById("apiKeyBadge");

    saveSettingsBtn.addEventListener("click", async () => {
        const payload = { model: modelSelect.value };
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
                if (d.api_keys_count) {
                    apiKeyCount.textContent = `${d.api_keys_count} keys loaded`;
                    apiKeyBadge.textContent = "Active";
                }
                if (d.language && translations[d.language]) {
                    currentLang = d.language;
                    document.querySelectorAll(".lang-btn").forEach(b => {
                        b.classList.toggle("active", b.dataset.lang === d.language);
                    });
                    applyLanguage(d.language);
                }
                if (d.personality) {
                    document.querySelectorAll(".persona-btn").forEach(b => {
                        b.classList.toggle("active", b.dataset.persona === d.personality);
                    });
                }
            }
        } catch { }
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
            } catch { }
        });
    });

    // ─── Personality ───
    document.querySelectorAll(".persona-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
            document.querySelectorAll(".persona-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            const persona = btn.dataset.persona;
            const label = btn.querySelector(".persona-name").textContent;
            showToast(`${t("toast_personality_changed")} ${label}`, "info");
            try {
                await fetch("/api/settings", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ personality: persona }),
                });
            } catch { }
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

    // ═══════════════════════ WEATHER ═══════════════════════

    const weatherBody = document.getElementById("weatherBody");
    const weatherForecastSection = document.getElementById("weatherForecastSection");
    const weatherCityInput = document.getElementById("weatherCityInput");
    const weatherGoBtn = document.getElementById("weatherGoBtn");
    const weatherLiveDot = document.getElementById("weatherLiveDot");

    const WX_ICONS = {
        "01d": "wb_sunny", "01n": "nights_stay",
        "02d": "cloud_queue", "02n": "nights_stay",
        "03d": "cloud", "03n": "cloud",
        "04d": "filter_drama", "04n": "filter_drama",
        "09d": "grain", "09n": "grain",
        "10d": "opacity", "10n": "opacity",
        "11d": "flash_on", "11n": "flash_on",
        "13d": "ac_unit", "13n": "ac_unit",
        "50d": "blur_on", "50n": "blur_on",
    };
    function wxIcon(code) { return WX_ICONS[code] || "cloud"; }

    function windDir(deg) {
        const dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
        return dirs[Math.round(deg / 45) % 8];
    }

    let wxClockInterval = null;
    let wxLastData = null;

    function startWxClock(localtimeStr) {
        if (wxClockInterval) clearInterval(wxClockInterval);
        const parts = localtimeStr.split(" ");
        if (parts.length < 2) return;
        const [datePart, timePart] = parts;
        const [y, m, d] = datePart.split("-").map(Number);
        const [h, mi] = timePart.split(":").map(Number);
        let cityTime = new Date(y, m - 1, d, h, mi, 0);
        const fetchedAt = Date.now();

        function updateClockDisplay() {
            const elapsed = Date.now() - fetchedAt;
            const now = new Date(cityTime.getTime() + elapsed);
            const hh = now.getHours().toString().padStart(2, "0");
            const mm = now.getMinutes().toString().padStart(2, "0");
            const ss = now.getSeconds().toString().padStart(2, "0");
            const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
            const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
            const dayName = dayNames[now.getDay()];
            const monthName = monthNames[now.getMonth()];
            const dateNum = now.getDate();
            const el = document.getElementById("wxLocalClock");
            if (el) el.textContent = `${dayName}, ${monthName} ${dateNum}  ${hh}:${mm}:${ss}`;
        }
        updateClockDisplay();
        wxClockInterval = setInterval(updateClockDisplay, 1000);
    }

    async function loadWeather(city, silent) {
        if (!city) return;
        if (!silent) {
            weatherBody.innerHTML = `<div class="weather-placeholder-state"><span class="material-icons-round weather-spin">sync</span><p>Loading...</p></div>`;
            weatherForecastSection.innerHTML = "";
            weatherLiveDot.classList.remove("live");
        }

        try {
            const r = await fetch(`/api/weather?city=${encodeURIComponent(city)}`);
            if (!r.ok) {
                const e = await r.json();
                weatherBody.innerHTML = `<div class="weather-placeholder-state error"><span class="material-icons-round">cloud_off</span><p>${escapeHtml(e.error || "City not found")}</p></div>`;
                weatherLiveDot.classList.remove("live");
                return;
            }
            const w = await r.json();
            w._fetchedAtMs = Date.now();
            wxLastData = w;
            weatherLiveDot.classList.add("live");

            const sunrise = w.sunrise || "--:--";
            const sunset = w.sunset || "--:--";

            const temp = Math.round(w.temp);
            const feelsLike = Math.round(w.feels_like);
            const tempMin = Math.round(w.temp_min);
            const tempMax = Math.round(w.temp_max);
            const windKph = Math.round(w.wind_kph);
            const pressure = Math.round(w.pressure);
            const visKm = w.vis_km;

            weatherBody.innerHTML = `
                <div class="wx-time-bar">
                    <span class="material-icons-round wx-time-icon">schedule</span>
                    <span class="wx-local-clock" id="wxLocalClock">--:--:--</span>
                    <span class="wx-tz-label">${escapeHtml(w.tz_id || "")}</span>
                </div>
                <div class="wx-hero">
                    <div class="wx-hero-left">
                        <div class="wx-icon-wrap"><span class="material-icons-round">${wxIcon(w.icon)}</span></div>
                        <div class="wx-hero-info">
                            <div class="wx-temp">${temp}<span class="wx-deg">°C</span></div>
                            <div class="wx-location">${escapeHtml(w.city)}, ${escapeHtml(w.country)}</div>
                            <div class="wx-condition">${escapeHtml(w.description)}</div>
                        </div>
                    </div>
                    <div class="wx-hero-right">
                        <div class="wx-minmax">
                            <span class="material-icons-round">arrow_upward</span>${tempMax}°
                            <span class="material-icons-round">arrow_downward</span>${tempMin}°
                        </div>
                        <div class="wx-feels">Feels like ${feelsLike}°C</div>
                    </div>
                </div>
                <div class="wx-grid">
                    <div class="wx-stat">
                        <span class="material-icons-round">air</span>
                        <div class="wx-stat-info">
                            <span class="wx-stat-val">${windKph} km/h ${w.wind_dir || windDir(w.wind_deg)}</span>
                            <span class="wx-stat-lbl">Wind</span>
                        </div>
                    </div>
                    <div class="wx-stat">
                        <span class="material-icons-round">opacity</span>
                        <div class="wx-stat-info">
                            <span class="wx-stat-val">${w.humidity}%</span>
                            <span class="wx-stat-lbl">Humidity</span>
                        </div>
                    </div>
                    <div class="wx-stat">
                        <span class="material-icons-round">speed</span>
                        <div class="wx-stat-info">
                            <span class="wx-stat-val">${pressure} hPa</span>
                            <span class="wx-stat-lbl">Pressure</span>
                        </div>
                    </div>
                    <div class="wx-stat">
                        <span class="material-icons-round">visibility</span>
                        <div class="wx-stat-info">
                            <span class="wx-stat-val">${visKm} km</span>
                            <span class="wx-stat-lbl">Visibility</span>
                        </div>
                    </div>
                    <div class="wx-stat">
                        <span class="material-icons-round">cloud</span>
                        <div class="wx-stat-info">
                            <span class="wx-stat-val">${w.clouds}%</span>
                            <span class="wx-stat-lbl">Clouds</span>
                        </div>
                    </div>
                    <div class="wx-stat">
                        <span class="material-icons-round">wb_sunny</span>
                        <div class="wx-stat-info">
                            <span class="wx-stat-val">${sunrise} / ${sunset}</span>
                            <span class="wx-stat-lbl">Rise / Set</span>
                        </div>
                    </div>
                </div>
                <div class="wx-updated-bar">Updated: ${escapeHtml(w.last_updated || w.localtime || "just now")}</div>
            `;

            if (w.localtime) startWxClock(w.localtime);
            loadForecast(city);
        } catch {
            weatherBody.innerHTML = `<div class="weather-placeholder-state error"><span class="material-icons-round">cloud_off</span><p>Cannot connect</p></div>`;
        }
    }

    async function loadForecast(city) {
        try {
            const r = await fetch(`/api/forecast?city=${encodeURIComponent(city)}`);
            if (!r.ok) return;
            const d = await r.json();

            const nowEpoch = d.localtime_epoch || (wxLastData && wxLastData.localtime_epoch) || Math.floor(Date.now() / 1000);
            const upcoming = d.forecast.filter(f => f.dt >= nowEpoch - 1800);
            if (!upcoming.length) return;

            const todayDate = upcoming[0].date;

            let html = `<div class="wx-forecast-title">Forecast</div><div class="wx-forecast-scroll">`;
            upcoming.slice(0, 16).forEach(f => {
                const lt = f.local_time || "";
                const timePart = lt.split(" ")[1] || "??:??";
                const hour = timePart.slice(0, 5);
                const dayLabel = f.date === todayDate ? "Today" : "Tmrw";
                html += `
                    <div class="wx-fc-item">
                        <span class="wx-fc-day">${dayLabel}</span>
                        <span class="wx-fc-hour">${hour}</span>
                        <span class="material-icons-round wx-fc-icon">${wxIcon(f.icon)}</span>
                        <span class="wx-fc-temp">${Math.round(f.temp)}°</span>
                        <span class="wx-fc-wind"><span class="material-icons-round" style="font-size:12px">air</span>${Math.round(f.wind_kph)}</span>
                    </div>`;
            });
            html += `</div>`;
            weatherForecastSection.innerHTML = html;
        } catch { }
    }

    weatherGoBtn.addEventListener("click", () => {
        const city = weatherCityInput.value.trim();
        if (city) loadWeather(city);
    });
    weatherCityInput.addEventListener("keydown", e => {
        if (e.key === "Enter") {
            const city = weatherCityInput.value.trim();
            if (city) loadWeather(city);
        }
    });

    loadWeather("Almaty");
    setInterval(() => {
        const city = weatherCityInput.value.trim() || "Almaty";
        loadWeather(city, true);
    }, 180000);

    // ─── Camera & D-Pad ───
    let cameraIp = null;
    let cameraDiscovering = false;
    const cameraStream = document.getElementById("cameraStream");
    const cameraPlaceholder = document.getElementById("cameraPlaceholder");
    const cameraStatusEl = document.getElementById("cameraStatus");
    const cameraRetryBtn = document.getElementById("cameraRetryBtn");

    function setCameraOnline(ip, streamUrl) {
        cameraIp = ip;
        cameraStream.src = streamUrl;
        cameraStream.style.display = "block";
        cameraPlaceholder.style.display = "none";
        cameraStatusEl.textContent = "● LIVE";
        cameraStatusEl.style.color = "var(--danger)";
    }

    function setCameraOffline() {
        cameraIp = null;
        cameraStream.src = "";
        cameraStream.style.display = "none";
        cameraPlaceholder.style.display = "flex";
        cameraStatusEl.textContent = "● OFFLINE";
        cameraStatusEl.style.color = "var(--text-muted)";
    }

    async function discoverCamera() {
        if (cameraDiscovering) return;
        cameraDiscovering = true;
        cameraStatusEl.textContent = "● SCANNING...";
        cameraStatusEl.style.color = "var(--warning)";
        try {
            const resp = await fetch("/api/camera/discover");
            if (resp.ok) {
                const data = await resp.json();
                setCameraOnline(data.ip, data.stream_url);
                showToast(`Camera found: ${data.ip}`, "success");
            } else {
                setCameraOffline();
                showToast("Camera not found", "error");
            }
        } catch {
            setCameraOffline();
        }
        cameraDiscovering = false;
    }

    if (cameraRetryBtn) cameraRetryBtn.addEventListener("click", discoverCamera);

    if (cameraStream) {
        cameraStream.addEventListener("error", () => {
            setCameraOffline();
        });
    }

    document.querySelectorAll(".dpad-btn[data-dir]").forEach(btn => {
        btn.addEventListener("click", async () => {
            const dir = btn.dataset.dir;
            if (!cameraIp) { showToast("Camera offline", "error"); return; }
            btn.style.transform = "scale(0.85)";
            setTimeout(() => btn.style.transform = "", 150);
            try {
                const resp = await fetch("/api/camera/control", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ direction: dir })
                });
                if (!resp.ok) showToast("Camera control failed", "error");
            } catch {
                showToast("Camera unreachable", "error");
            }
        });
    });

    // ─── Audio Intercom (browser <-> ESP32) ───
    const micToggleBtn = document.getElementById("micToggleBtn");
    let micActive = false;
    let _aSocket = null;
    let _aMicCtx = null, _aMicStream = null, _aMicProc = null;
    let _aPlayCtx = null, _aNextTime = 0;

    async function startIntercom() {
        _aSocket = io("/audio");

        _aPlayCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        _aNextTime = 0;

        _aSocket.on("esp_audio", (raw) => {
            if (!_aPlayCtx) return;
            const pcm = new Int16Array(raw);
            const f32 = new Float32Array(pcm.length);
            for (let i = 0; i < pcm.length; i++) f32[i] = pcm[i] / 32768.0;
            const buf = _aPlayCtx.createBuffer(1, f32.length, 16000);
            buf.getChannelData(0).set(f32);
            const src = _aPlayCtx.createBufferSource();
            src.buffer = buf;
            src.connect(_aPlayCtx.destination);
            const now = _aPlayCtx.currentTime;
            if (_aNextTime < now) _aNextTime = now + 0.05;
            src.start(_aNextTime);
            _aNextTime += buf.duration;
        });

        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            try {
                _aMicCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
                const rate = _aMicCtx.sampleRate;
                _aMicStream = await navigator.mediaDevices.getUserMedia({
                    audio: { echoCancellation: true, noiseSuppression: true }
                });
                const source = _aMicCtx.createMediaStreamSource(_aMicStream);
                const bufSz = rate <= 16000 ? 512 : 2048;
                _aMicProc = _aMicCtx.createScriptProcessor(bufSz, 1, 1);

                _aMicProc.onaudioprocess = (e) => {
                    if (!_aSocket) return;
                    let f = e.inputBuffer.getChannelData(0);
                    if (rate !== 16000) {
                        const ratio = rate / 16000;
                        const newLen = Math.round(f.length / ratio);
                        const rs = new Float32Array(newLen);
                        for (let i = 0; i < newLen; i++) rs[i] = f[Math.round(i * ratio)];
                        f = rs;
                    }
                    const pcm = new Int16Array(f.length);
                    for (let i = 0; i < f.length; i++) {
                        const s = Math.max(-1, Math.min(1, f[i]));
                        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                    }
                    _aSocket.emit("browser_audio", pcm.buffer);
                };

                const mute = _aMicCtx.createGain();
                mute.gain.value = 0;
                source.connect(_aMicProc);
                _aMicProc.connect(mute);
                mute.connect(_aMicCtx.destination);
            } catch (err) {
                showToast("Mic blocked (HTTPS required) — listen only", "error");
            }
        } else {
            showToast("No mic on HTTP — listen only mode", "error");
        }
    }

    function stopIntercom() {
        if (_aMicProc) { _aMicProc.disconnect(); _aMicProc = null; }
        if (_aMicStream) { _aMicStream.getTracks().forEach(t => t.stop()); _aMicStream = null; }
        if (_aMicCtx) { _aMicCtx.close(); _aMicCtx = null; }
        if (_aPlayCtx) { _aPlayCtx.close(); _aPlayCtx = null; }
        if (_aSocket) { _aSocket.disconnect(); _aSocket = null; }
    }

    if (micToggleBtn) {
        micToggleBtn.addEventListener("click", async () => {
            micActive = !micActive;
            const icon = micToggleBtn.querySelector(".material-icons-round");
            if (micActive) {
                try {
                    await startIntercom();
                    icon.textContent = "mic";
                    micToggleBtn.classList.add("mic-active");
                    showToast("Intercom active", "success");
                } catch (e) {
                    micActive = false;
                    showToast("Failed: " + e.message, "error");
                }
            } else {
                stopIntercom();
                icon.textContent = "mic_off";
                micToggleBtn.classList.remove("mic-active");
                showToast("Intercom off", "info");
            }
        });
    }

    // ═══════════════════════ EMAIL AUTHENTICATION ═══════════════════════
    const accountIconBtn = document.getElementById('accountIconBtn');
    const emailAuthModal = document.getElementById('emailAuthModal');
    const modalOverlay = document.getElementById('modalOverlay');
    const modalCloseBtn = document.getElementById('modalCloseBtn');
    const accountAvatar = document.getElementById('accountAvatar');
    const accountAvatarLarge = document.getElementById('accountAvatarLarge');
    const loggedInEmail = document.getElementById('loggedInEmail');
    const accountsList = document.getElementById('accountsList');

    // Auth sections
    const loginSection = document.getElementById('loginSection');
    const registerSection = document.getElementById('registerSection');
    const loggedInSection = document.getElementById('loggedInSection');

    // Forms
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const switchToRegisterLink = document.getElementById('switchToRegister');
    const switchToLoginLink = document.getElementById('switchToLogin');
    const switchAccountBtn = document.getElementById('switchAccountBtn');
    const logoutBtn = document.getElementById('logoutBtn');
    const gmailLoginBtn = document.getElementById('gmailLoginBtn');
    const gmailDisconnectBtn = document.getElementById('gmailDisconnectBtn');
    const gmailSection = document.getElementById('gmailSection');

    // Email storage key
    const ACCOUNTS_STORAGE_KEY = 'emailAccounts';
    const CURRENT_ACCOUNT_KEY = 'currentEmailAccount';
    const SESSION_TOKEN_KEY = 'sessionToken';
    const GMAIL_AUTH_KEY = 'gmailAuthenticated';

    // Initialize email service
    function initEmailService() {
        checkAuthStatus();
        updateAccountDisplay();
        checkGmailStatus();
    }

    // Check authentication status with backend
    async function checkAuthStatus() {
        try {
            const sessionToken = localStorage.getItem(SESSION_TOKEN_KEY);
            if (!sessionToken) {
                return;
            }

            const resp = await fetch('/api/email/verify', {
                headers: { 'X-Session-Token': sessionToken }
            });

            if (resp.ok) {
                const data = await resp.json();
                if (data.authenticated) {
                    localStorage.setItem(CURRENT_ACCOUNT_KEY, data.email);
                }
            } else {
                localStorage.removeItem(SESSION_TOKEN_KEY);
                localStorage.removeItem(CURRENT_ACCOUNT_KEY);
            }
        } catch (e) {
            console.error('Auth check error:', e);
        }
    }

    // Check Gmail authentication status
    async function checkGmailStatus() {
        try {
            const resp = await fetch('/api/gmail/status');
            const data = await resp.json();

            if (data.authenticated && data.email) {
                localStorage.setItem(GMAIL_AUTH_KEY, JSON.stringify({
                    authenticated: true,
                    email: data.email
                }));
                if (gmailSection) {
                    gmailSection.style.display = 'block';
                }
                // Load emails when Gmail is authenticated
                loadEmails();
            }
        } catch (e) {
            console.error('Gmail status check error:', e);
        }
    }

    // Load and display emails
    async function loadEmails() {
        try {
            // First sync emails from Gmail
            const syncResp = await fetch('/api/emails/sync', {
                method: 'POST'
            });

            if (!syncResp.ok) {
                console.warn('Email sync failed:', await syncResp.json());
            }

            // Then fetch cached emails
            const resp = await fetch('/api/emails/inbox?max_results=50');
            const data = await resp.json();

            // Ищем правильный контейнер из твоего HTML!
            const emailsList = document.getElementById('emails-list');
            if (!emailsList) return;

            // Если писем нет - показываем красивую заглушку в emails-list
            if (!data.emails || data.emails.length === 0) {
                emailsList.innerHTML = `
                    <div class="placeholder-content" style="padding: 30px; text-align: center; color: var(--text-secondary);">
                        <span class="material-icons-round" style="font-size: 32px; opacity: 0.5;">mail_outline</span>
                        <p style="margin-top: 8px; font-size: 14px;">No emails yet</p>
                    </div>
                `;
                return;
            }

            // ── Email classification helpers ──────────────────────────────
            const AD_SENDER_PATTERNS = [
                /no.?reply/i, /noreply/i, /newsletter/i, /promo/i, /marketing/i,
                /notify/i, /notification/i, /info@/i, /hello@/i, /support@/i,
                /news@/i, /updates@/i, /deals@/i, /offer/i, /digest@/i,
                /mailer/i, /mail\..*\.(com|net|io)/i, /donotreply/i,
                /bounce/i, /bulk/i, /campaign/i, /subscri/i,
            ];
            const AD_SUBJECT_PATTERNS = [
                /\bsale\b/i, /\bdeal\b/i, /\boffer\b/i, /\bdiscount\b/i,
                /\bpromo/i, /\boff\b.*%/i, /%\s*off/i, /limited time/i,
                /\bunsubscribe\b/i, /\bnewsletter\b/i, /\bweekly digest\b/i,
                /\bexclusive\b/i, /\bwin\b/i, /\bgiveaway\b/i, /\bfree\b.*trial/i,
                /\bspecial offer/i, /\byou('ve| have) been selected/i,
                /\bcongratulations.*won/i, /\bact now\b/i, /\buy now\b/i,
                /\bnew releases? this week/i, /\btop picks\b/i,
            ];
            const IMPORTANT_SUBJECT_PATTERNS = [
                /\bpayment\b/i, /\binvoice\b/i, /\breceipt\b/i, /\btransaction\b/i,
                /\bconfirm/i, /\bverif/i, /\bsecurity\b/i, /\balert\b/i,
                /\burgent\b/i, /\bimportant\b/i, /\baction required\b/i,
                /\bpassword\b/i, /\bmeeting\b/i, /\binterview\b/i,
                /\bship/i, /\bdelivery\b/i, /\border.*confirm/i,
            ];
            const BULK_SENDER_DOMAINS = [
                'mailer.', 'mail.', 'em.', 'send.', 'bounce.', 'reply.',
                'bulk.', 'lists.', 'news.', 'promo.', 'email.', 'notify.',
            ];

            function classifyEmail(email) {
                const from = (email.from || '').toLowerCase();
                const subject = (email.subject || '').toLowerCase();
                const body = (email.body || '').toLowerCase();

                // Extract sender domain
                const domainMatch = from.match(/@([\w.\-]+)/);
                const domain = domainMatch ? domainMatch[1] : '';
                const isBulkDomain = BULK_SENDER_DOMAINS.some(p => domain.startsWith(p));

                const isAdSender = AD_SENDER_PATTERNS.some(p => p.test(from));
                const isAdSubject = AD_SUBJECT_PATTERNS.some(p => p.test(subject));
                const hasUnsubscribe = body.includes('unsubscribe') || body.includes('opt out') || body.includes('opt-out');

                // Spam/ad score
                let adScore = 0;
                if (isAdSender) adScore += 2;
                if (isAdSubject) adScore += 2;
                if (isBulkDomain) adScore += 2;
                if (hasUnsubscribe) adScore += 1;

                if (adScore >= 3) return 'ad';

                // Important check
                const isImportantSubject = IMPORTANT_SUBJECT_PATTERNS.some(p => p.test(subject));
                // Personal = looks like a real person's email (name@domain, no bulk patterns)
                const looksPersonal = /^[a-z]+[\.\-_]?[a-z]+@/.test(from.match(/<(.+)>/)?.[1] || from);
                const isPersonal = looksPersonal && !isAdSender && !isBulkDomain;

                if (isImportantSubject) return 'important';
                if (isPersonal) return 'people';
                return 'other'; // still shown in "All" but not ads
            }

            // Pad with mock emails if fewer than 10 real ones
            const mockEmails = [
                { from: 'Alex Johnson <alex.johnson@gmail.com>', subject: 'Project update', body: 'Hey! Just wanted to check in on the dashboard project. Are we still on track for the Friday deadline?', date: new Date(Date.now() - 1 * 3600000).toISOString() },
                { from: 'Bank Alert <alerts@mybank.com>', subject: 'Transaction confirmed: $49.99', body: "A payment of $49.99 was charged to your card ending in 4821 at Adobe Inc. If this wasn't you, please contact us immediately.", date: new Date(Date.now() - 2 * 3600000).toISOString() },
                { from: 'Netflix <info@mailer.netflix.com>', subject: 'New releases this week 🎬', body: "This week's top picks are now available! Check out the latest episodes and movies added to your region's catalogue.", date: new Date(Date.now() - 3 * 3600000).toISOString() },
                { from: 'Sarah K. <sarah.k@work.com>', subject: 'Meeting tomorrow at 10am', body: 'Hi, confirming our meeting tomorrow at 10am in conference room B. Please bring the Q4 report.', date: new Date(Date.now() - 5 * 3600000).toISOString() },
                { from: 'GitHub <noreply@github.com>', subject: 'Your pull request was merged', body: 'Congratulations! Your pull request #42 has been successfully merged into main.', date: new Date(Date.now() - 6 * 3600000).toISOString() },
                { from: 'Spotify <promo@email.spotify.com>', subject: '🎵 3 months Premium for $0.99 — Limited offer!', body: 'Act now! Get 3 months of Spotify Premium for just $0.99. This exclusive deal expires soon.', date: new Date(Date.now() - 8 * 3600000).toISOString() },
                { from: 'Amazon <deals@amazon-offers.com>', subject: 'Flash Sale: Up to 70% OFF today only!', body: 'Hurry! Thousands of items on sale. Limited time deal ends at midnight. Shop now and save big.', date: new Date(Date.now() - 10 * 3600000).toISOString() },
                { from: 'Vercel <no-reply@vercel.com>', subject: 'Action required: Deployment failed', body: 'Your latest deployment to production failed. Please check your build logs and fix the issue.', date: new Date(Date.now() - 12 * 3600000).toISOString() },
                { from: 'mom <mama.bekova@gmail.com>', subject: 'Dinner this Sunday?', body: 'Hi honey! Are you coming for dinner on Sunday? I am making your favourite. Let me know!', date: new Date(Date.now() - 24 * 3600000).toISOString() },
                { from: 'LinkedIn <newsletter@linkedin.com>', subject: 'This week in your network — 5 people viewed your profile', body: 'See who viewed your profile and discover new opportunities. Upgrade to Premium to unlock full insights.', date: new Date(Date.now() - 30 * 3600000).toISOString() },
                { from: 'Figma <no-reply@figma.com>', subject: 'Someone shared a file with you', body: 'Alex shared "Dashboard Redesign v3" with you. Open the file to view the latest mockups.', date: new Date(Date.now() - 48 * 3600000).toISOString() },
                { from: 'dan.smith@gmail.com', subject: 'Re: Weekend plans', body: 'Sounds great! I will bring snacks. See you Saturday around 3pm. Let me know if plans change.', date: new Date(Date.now() - 50 * 3600000).toISOString() },
            ];

            const allEmails = [...(data.emails || [])];
            const needed = Math.max(0, 10 - allEmails.length);
            allEmails.push(...mockEmails.slice(0, needed));

            // Classify every email
            allEmails.forEach(e => { e._category = classifyEmail(e); });

            // Filter out ads from all views — ads are NEVER shown
            const visibleEmails = allEmails.filter(e => e._category !== 'ad');

            // Store for modal & filter use
            window._ariaEmails = visibleEmails;
            window._ariaAllEmails = visibleEmails;
            window._ariaActiveFilter = window._ariaActiveFilter || 'all';

            function renderEmailList(filter) {
                window._ariaActiveFilter = filter;
                const filtered = filter === 'all'
                    ? visibleEmails
                    : visibleEmails.filter(e => e._category === filter);

                let listEl = document.getElementById('emails-list');
                if (!listEl) {
                    listEl = document.getElementById('emailContent');
                }
                if (!listEl) return;

                if (filtered.length === 0) {
                    listEl.innerHTML = `<div style="padding:30px; text-align:center; color:var(--text-secondary);">
                        <span class="material-icons-round" style="font-size:32px; opacity:0.4;">inbox</span>
                        <p style="margin:8px 0 0; font-size:13px;">No emails in this category</p>
                    </div>`;
                    return;
                }

                // Apply pagination
                const emailsPerPage = 10;
                const start = currentPageIndex * emailsPerPage;
                const end = start + emailsPerPage;
                const pagedEmails = filtered.slice(start, end);
                const totalPages = Math.ceil(filtered.length / emailsPerPage);

                // Update pagination info
                const pageInfo = document.getElementById('emailPageInfo');
                if (pageInfo) {
                    pageInfo.textContent = `${currentPageIndex + 1} / ${totalPages}`;
                }
                document.getElementById('emailNewerBtn').disabled = currentPageIndex === 0;
                document.getElementById('emailOlderBtn').disabled = currentPageIndex >= totalPages - 1;
                document.getElementById('emailNewerBtn').style.opacity = currentPageIndex === 0 ? '0.5' : '1';
                document.getElementById('emailOlderBtn').style.opacity = currentPageIndex >= totalPages - 1 ? '0.5' : '1';

                listEl.innerHTML = pagedEmails.map((email) => {
                    const date = new Date(email.date);
                    const diffH = (Date.now() - date) / 3600000;

                    // Format date like on screenshot: "06:32" or "4 Mar"
                    let dateStr;
                    if (diffH < 1) {
                        dateStr = 'Just now';
                    } else if (diffH < 24) {
                        dateStr = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
                    } else {
                        dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    }

                    const safeFrom = escapeHtml(email.from || '');
                    const safeSubject = escapeHtml(email.subject || '(No subject)');
                    const rawBodyForPreview = (email.body || '')
                        .replace(/<head[\s\S]*?<\/head>/gi, '')
                        .replace(/<style[\s\S]*?<\/style>/gi, '')
                        .replace(/<script[\s\S]*?<\/script>/gi, '')
                        .replace(/<[^>]*>/g, ' ')
                        .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>')
                        .replace(/\s+/g, ' ').trim();
                    const safeBody = escapeHtml(rawBodyForPreview.substring(0, 100));

                    // Extract name from email
                    const nameMatch = safeFrom.match(/^([^<]*)</);
                    const displayName = nameMatch ? nameMatch[1].trim() : safeFrom.split('@')[0];
                    const initial = displayName.charAt(0).toUpperCase() || '?';

                    // Generate color based on initial
                    const colors = ['#667eea', '#764ba2', '#f093fb', '#4facfe', '#43e97b', '#fa709a', '#fee140', '#30b0fe'];
                    const colorIndex = initial.charCodeAt(0) % colors.length;
                    const avatarColor = colors[colorIndex];

                    return `
                        <div class="email-row" style="display: flex; padding: 12px 14px; border-bottom: 1px solid var(--border-color); cursor: pointer; gap: 10px; align-items: flex-start; transition: background 0.2s;"
                            onmouseenter="this.style.background='var(--accent-bg)'; this.style.boxShadow='0 2px 8px rgba(0,0,0,0.1)';"
                            onmouseleave="this.style.background=''; this.style.boxShadow='';"
                        >
                            <div style="flex-shrink: 0; width: 40px; height: 40px; border-radius: 50%; background: ${avatarColor}; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 14px; color: white; flex: 0 0 40px;">
                                ${initial}
                            </div>
                            <div style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px;">
                                <p style="margin: 0; font-weight: 600; font-size: 13px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${displayName}</p>
                                <p style="margin: 0; font-size: 12px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${safeSubject}</p>
                                <p style="margin: 0; font-size: 12px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${safeBody}</p>
                            </div>
                            <span style="font-size: 11px; color: var(--text-secondary); flex-shrink: 0; white-space: nowrap;">${dateStr}</span>
                        </div>
                    `;
                }).join('');

                // Re-attach click listeners
                listEl.querySelectorAll('.email-row').forEach((el, idx) => {
                    if (idx < pagedEmails.length) {
                        el.addEventListener('click', () => {
                            openEmailDetail(pagedEmails[idx]);
                        });
                    }
                });
            }

            // Initialize modal for email details (if not exists)
            if (!document.getElementById('emailDetailModal')) {
                const modalHtml = `
                    <div id="emailDetailModal" style="display:none; position:fixed; inset:0; z-index:9999; align-items:center; justify-content:center; padding:16px; box-sizing:border-box;">
                        <div id="emailDetailOverlay" style="position:absolute; inset:0; background:rgba(0,0,0,0.5); backdrop-filter:blur(6px);"></div>
                        <div style="position:relative; z-index:1; background:var(--bg-card); border:1px solid var(--border-color); border-radius:12px; width:min(700px, 100%); max-height:80vh; display:flex; flex-direction:column; box-shadow:0 12px 48px rgba(0,0,0,0.3); overflow:hidden;">
                            <!-- Modal Header -->
                            <div style="flex-shrink:0; display:flex; align-items:center; justify-content:space-between; padding:16px 20px; border-bottom:1px solid var(--border-color); background:var(--bg-card);">
                                <div style="display:flex; align-items:center; gap:10px;">
                                    <span class="material-icons-round" style="color:var(--accent); font-size:20px;">mark_email_read</span>
                                    <span style="font-weight:600; font-size:15px; color:var(--text-primary);">Email</span>
                                </div>
                                <button id="emailDetailClose" style="background:none; border:none; cursor:pointer; color:var(--text-secondary); display:flex; align-items:center; padding:6px; border-radius:8px; transition:background 0.15s;" onmouseover="this.style.background='var(--bg-input)'" onmouseout="this.style.background='none'">
                                    <span class="material-icons-round">close</span>
                                </button>
                            </div>
                            <!-- Subject + Meta (fixed) -->
                            <div style="flex-shrink:0; padding:16px 20px 14px; border-bottom:1px solid var(--border-color); background:var(--bg-input);">
                                <p id="emailDetailSubject" style="margin:0 0 12px; font-size:16px; font-weight:700; line-height:1.4; color:var(--text-primary);"></p>
                                <table style="border-collapse:collapse; width:100%; font-size:13px;">
                                    <tr>
                                        <td style="color:var(--text-secondary); padding:3px 12px 3px 0; white-space:nowrap; vertical-align:top; font-weight:500; width:42px;">From</td>
                                        <td id="emailDetailFrom" style="color:var(--text-primary); padding:3px 0; word-break:break-all;"></td>
                                    </tr>
                                    <tr>
                                        <td style="color:var(--text-secondary); padding:3px 12px 3px 0; white-space:nowrap; vertical-align:top; font-weight:500;">To</td>
                                        <td id="emailDetailTo" style="color:var(--text-primary); padding:3px 0; word-break:break-all;"></td>
                                    </tr>
                                    <tr>
                                        <td style="color:var(--text-secondary); padding:3px 12px 3px 0; white-space:nowrap; font-weight:500;">Date</td>
                                        <td id="emailDetailDate" style="color:var(--text-primary); padding:3px 0;"></td>
                                    </tr>
                                </table>
                            </div>
                            <!-- Body — scrollable area -->
                            <div style="flex:1; min-height:200px; overflow-y:auto; background:var(--bg-secondary);">
                                <div id="emailDetailBody" style="display:flex; flex-direction:column; width:100%; min-height:100%;"></div>
                            </div>
                        </div>
                    </div>
                `;
                document.body.insertAdjacentHTML('beforeend', modalHtml);

                document.getElementById('emailDetailClose').addEventListener('click', closeEmailDetail);
                document.getElementById('emailDetailOverlay').addEventListener('click', closeEmailDetail);
                document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeEmailDetail(); });
            }

            // Back to email list from in-place detail view
            function backToEmailList() {
                // Show pagination controls
                const paginationContainer = document.getElementById('emailPaginationContainer');
                if (paginationContainer) {
                    paginationContainer.style.display = 'flex';
                }
                // Re-render the email list
                renderEmailList(window._ariaActiveFilter);
            }

            // Opening email detail in in-place view
            function openEmailDetail(email) {
                const listEl = document.getElementById('emails-list');
                if (!listEl) return;

                // Hide pagination controls
                const paginationContainer = document.getElementById('emailPaginationContainer');
                if (paginationContainer) {
                    paginationContainer.style.display = 'none';
                }

                const date = new Date(email.date);
                const formattedDate = date.toLocaleString(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

                // Create the detail view header and body structure
                listEl.innerHTML = `
                    <!-- In-place Detail View Header -->
                    <div style="position: sticky; top: 0; z-index: 100; background: var(--bg-card); border-bottom: 1px solid var(--border-color); padding: 16px 14px; display: flex; flex-direction: column; gap: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                        <!-- Back Button Row -->
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <button id="emailDetailBackBtn" style="background: none; border: none; cursor: pointer; color: var(--accent); padding: 6px; border-radius: 8px; font-size: 20px; display: flex; align-items: center; justify-content: center; transition: background 0.15s;" onmouseover="this.style.background='var(--accent-bg)'" onmouseout="this.style.background='none'">
                                <span class="material-icons-round">arrow_back</span>
                            </button>
                            <span style="font-weight: 600; color: var(--text-primary);">Email</span>
                        </div>
                        
                        <!-- Subject -->
                        <div style="padding: 0 0 8px 0;">
                            <p id="emailDetailSubject" style="margin: 0; font-size: 18px; font-weight: 700; line-height: 1.4; color: var(--text-primary); word-break: break-word;">
                                ${escapeHtml(email.subject || '(No subject)')}
                            </p>
                        </div>
                        
                        <!-- Sender Info and Date -->
                        <div style="display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--text-secondary);">
                            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                                <span style="font-weight: 500;">From:</span>
                                <span id="emailDetailFrom" style="color: var(--text-primary); word-break: break-all;">
                                    ${escapeHtml(email.from || '—')}
                                </span>
                            </div>
                            <div style="display: flex; gap: 8px;">
                                <span style="font-weight: 500;">Date:</span>
                                <span id="emailDetailDate" style="color: var(--text-primary);">
                                    ${formattedDate}
                                </span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Email Body Container -->
                    <div id="emailDetailBody" style="display: flex; flex-direction: column; width: 100%; min-height: 200px; background: var(--bg-secondary);"></div>
                `;

                // Attach back button listener
                document.getElementById('emailDetailBackBtn').addEventListener('click', backToEmailList);

                // Render email body
                const bodyEl = document.getElementById('emailDetailBody');
                const rawBody = email.body || email.html || email.text || email.content || email.snippet || email.message || '';

                console.log('Email object:', email);
                console.log('Raw body length:', rawBody.length);

                // If body is missing, try fetching it from the API
                if (!rawBody && email.id) {
                    console.log('Fetching email content by ID:', email.id);
                    bodyEl.innerHTML = '<p style="padding:20px;color:var(--text-secondary);text-align:center;"><span class="material-icons-round" style="display:block;font-size:32px;margin-bottom:8px;">hourglass_empty</span>Loading message...</p>';
                    fetch(`/api/emails/message/${email.id}`)
                        .then(r => r.json())
                        .then(data => {
                            console.log('Fetched email data:', data);
                            const fetchedBody = data.body || data.html || data.text || data.content || data.snippet || '';
                            renderEmailBody(bodyEl, fetchedBody || '(No message content found)');
                        })
                        .catch((err) => {
                            console.error('Fetch error:', err);
                            renderEmailBody(bodyEl, email.snippet || '(Could not load message content)');
                        });
                } else {
                    console.log('Using local body, rawBody length:', rawBody.length);
                    renderEmailBody(bodyEl, rawBody || '(No message content)');
                }
            }

            function closeEmailDetail() {
                document.getElementById('emailDetailModal').style.display = 'none';
            }

            function renderEmailBody(bodyEl, rawBody) {
                console.log('renderEmailBody called with body length:', rawBody.length);
                bodyEl.innerHTML = '';

                if (!rawBody || rawBody.trim() === '') {
                    bodyEl.innerHTML = '<p style="padding:16px; color:var(--text-secondary); text-align:center;">(No message content)</p>';
                    return;
                }

                const isHtml = /<[a-z][\s\S]*>/i.test(rawBody);

                if (isHtml) {
                    console.log('Body is HTML - using iframe');

                    // Get current theme colors
                    const isDarkTheme = !document.documentElement.hasAttribute('data-theme') || document.documentElement.getAttribute('data-theme') === 'dark';
                    const bgColor = isDarkTheme ? '#111827' : '#ffffff';
                    const textColor = isDarkTheme ? '#f1f5f9' : '#1e293b';

                    // Create iframe for safe HTML rendering
                    const iframe = document.createElement('iframe');
                    iframe.style.cssText = 'width:100% !important;border:none !important;background:' + bgColor + ' !important;color:' + textColor + ' !important;display:block !important;';
                    iframe.setAttribute('sandbox', 'allow-same-origin');
                    iframe.setAttribute('frameborder', '0');
                    iframe.setAttribute('scrolling', 'no');

                    // Wrap the email HTML with proper styling
                    const wrappedHtml = `
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            <style>
                                html, body { 
                                    margin: 0 !important; 
                                    padding: 0 !important;
                                    background: ${bgColor} !important;
                                }
                                body { 
                                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                                    padding: 16px !important; 
                                    background: ${bgColor} !important;
                                    color: ${textColor} !important;
                                    font-size: 14px;
                                    line-height: 1.6;
                                }
                                * { color: ${textColor} !important; }
                                a { color: #6366f1; }
                                img { max-width: 100%; height: auto; }
                                table { width: 100%; border-collapse: collapse; }
                                td, th { padding: 8px; }
                            </style>
                        </head>
                        <body>${rawBody}</body>
                        </html>
                    `;

                    bodyEl.appendChild(iframe);
                    iframe.srcdoc = wrappedHtml;

                    // Resize iframe to fit content immediately
                    setTimeout(() => {
                        try {
                            const contentHeight = iframe.contentDocument.body.scrollHeight;
                            iframe.style.height = contentHeight + 'px';
                            console.log('iframe height set to:', contentHeight);
                        } catch (e) {
                            console.log('iframe resize error:', e);
                        }
                    }, 100);

                    console.log('HTML content loaded in iframe');
                } else {
                    console.log('Body is plain text');
                    // Plain text — preserve line breaks
                    const p = document.createElement('pre');
                    p.style.cssText = 'display:block !important;margin:0 !important;padding:16px !important;font-size:14px !important;line-height:1.8 !important;white-space:pre-wrap !important;word-break:break-word !important;color:var(--text-primary) !important;font-family:inherit !important;background:var(--bg-secondary) !important;';
                    p.textContent = rawBody;
                    bodyEl.appendChild(p);
                    console.log('Text content added');
                }
            }

            // Initialize pagination and render
            let currentPageIndex = 0;
            const emailsPerPage = 10;


            function initializePagination() {
                // Используем onclick вместо addEventListener, чтобы предотвратить дублирование кликов
                document.getElementById('emailNewerBtn').onclick = () => {
                    if (currentPageIndex > 0) {
                        currentPageIndex--;
                        renderEmailList(window._ariaActiveFilter);
                    }
                };

                document.getElementById('emailOlderBtn').onclick = () => {
                    const filtered = window._ariaActiveFilter === 'all'
                        ? visibleEmails
                        : visibleEmails.filter(e => e._category === window._ariaActiveFilter);
                    const maxPages = Math.ceil(filtered.length / emailsPerPage);
                    if (currentPageIndex < maxPages - 1) {
                        currentPageIndex++;
                        renderEmailList(window._ariaActiveFilter);
                    }
                };
            }

            // Initial render
            initializePagination();
            renderEmailList(window._ariaActiveFilter);
        } catch (e) {
            console.error('Load emails error:', e);
            const emailsList = document.getElementById('emails-list');
            if (emailsList) {
                emailsList.innerHTML = `
                    <div class="placeholder-content">
                        <span class="material-icons-round" style="color: #f44336;">error</span>
                        <p style="color: #f44336;">Error loading emails</p>
                    </div>
                `;
            }
        }
    }

    // Get first letter of email
    function getEmailFirstLetter(email) {
        return email ? email.charAt(0).toUpperCase() : '?';
    }

    // Update account display in the avatar
    function updateAccountDisplay() {
        const currentEmail = getCurrentAccount();
        const letter = getEmailFirstLetter(currentEmail);
        accountAvatar.innerHTML = '<span class="material-icons-round" style="font-size: 24px; color: white;">person</span>';
        accountAvatarLarge.textContent = letter;

        if (currentEmail) {
            loginSection.classList.add('hidden');
            registerSection.classList.add('hidden');
            loggedInSection.classList.remove('hidden');
            loggedInEmail.textContent = currentEmail;
            updateAccountsList();
        } else {
            loginSection.classList.remove('hidden');
            registerSection.classList.add('hidden');
            loggedInSection.classList.add('hidden');
        }
    }

    // Get current account
    function getCurrentAccount() {
        return localStorage.getItem(CURRENT_ACCOUNT_KEY);
    }

    // Set current account
    function setCurrentAccount(email) {
        localStorage.setItem(CURRENT_ACCOUNT_KEY, email);
    }

    // Update accounts list
    async function updateAccountsList() {
        try {
            const resp = await fetch('/api/email/accounts');
            const data = await resp.json();
            const accounts = data.accounts || [];
            const currentEmail = getCurrentAccount();
            const otherAccounts = accounts.filter(acc => acc !== currentEmail);

            accountsList.innerHTML = '<p class="accounts-title">Other Accounts</p>';

            if (otherAccounts.length === 0) {
                accountsList.innerHTML += '<p class="no-accounts" style="color: var(--text-secondary); font-size: 12px;">No other accounts</p>';
                return;
            }

            otherAccounts.forEach(email => {
                const letter = getEmailFirstLetter(email);
                const accountItem = document.createElement('div');
                accountItem.className = 'account-item';
                accountItem.innerHTML = `
                    <div class="account-item-avatar">${letter}</div>
                    <span class="account-item-email">${email}</span>
                `;
                accountItem.addEventListener('click', () => {
                    setCurrentAccount(email);
                    updateAccountDisplay();
                    showToast(`Switched to ${email}`, 'success');
                });
                accountsList.appendChild(accountItem);
            });
        } catch (e) {
            console.error('Error updating accounts list:', e);
        }
    }

    // Modal functions
    function openModal() {
        emailAuthModal.classList.add('show');
        modalOverlay.classList.add('show');
        updateAccountDisplay();
        checkGmailStatus();
    }

    function closeModal() {
        emailAuthModal.classList.remove('show');
        modalOverlay.classList.remove('show');
        resetForms();
    }

    function resetForms() {
        loginForm.reset();
        registerForm.reset();
        document.getElementById('loginEmail').value = '';
        document.getElementById('loginPassword').value = '';
        document.getElementById('registerEmail').value = '';
        document.getElementById('registerPassword').value = '';
        document.getElementById('registerConfirmPassword').value = '';
    }

    // Switch between login and register
    function switchToRegister() {
        loginSection.classList.add('hidden');
        registerSection.classList.remove('hidden');
    }

    function switchToLogin() {
        loginSection.classList.remove('hidden');
        registerSection.classList.add('hidden');
    }

    // Login handler
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('loginEmail').value.trim();
        const password = document.getElementById('loginPassword').value.trim();

        if (!email || !password) {
            showToast('Please fill in all fields', 'error');
            return;
        }

        try {
            const resp = await fetch('/api/email/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            const data = await resp.json();

            if (resp.ok) {
                localStorage.setItem(SESSION_TOKEN_KEY, data.session_token);
                setCurrentAccount(email);
                updateAccountDisplay();
                resetForms();
                showToast(`Logged in as ${email}`, 'success');
                closeModal();
            } else {
                showToast(data.error || 'Login failed', 'error');
            }
        } catch (e) {
            showToast('Login error: ' + e.message, 'error');
            console.error('Login error:', e);
        }
    });

    // Register handler
    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('registerEmail').value.trim();
        const password = document.getElementById('registerPassword').value.trim();
        const confirmPassword = document.getElementById('registerConfirmPassword').value.trim();

        if (!email || !password || !confirmPassword) {
            showToast('Please fill in all fields', 'error');
            return;
        }

        if (password !== confirmPassword) {
            showToast('Passwords do not match', 'error');
            return;
        }

        if (password.length < 6) {
            showToast('Password must be at least 6 characters', 'error');
            return;
        }

        try {
            const resp = await fetch('/api/email/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            const data = await resp.json();

            if (resp.ok) {
                showToast('Account created! Please login.', 'success');
                switchToLogin();
                document.getElementById('loginEmail').value = email;
            } else {
                showToast(data.error || 'Registration failed', 'error');
            }
        } catch (e) {
            showToast('Registration error: ' + e.message, 'error');
            console.error('Registration error:', e);
        }
    });

    // Gmail login handler
    gmailLoginBtn.addEventListener('click', async () => {
        try {
            const resp = await fetch('/api/gmail/login');
            const data = await resp.json();

            if (data.auth_url) {
                // Redirect to Gmail OAuth
                window.open(data.auth_url, 'gmailAuth', 'width=500,height=600');

                // Check status every second
                const checkInterval = setInterval(async () => {
                    const statusResp = await fetch('/api/gmail/status');
                    const statusData = await statusResp.json();

                    if (statusData.authenticated && statusData.email) {
                        clearInterval(checkInterval);
                        localStorage.setItem(GMAIL_AUTH_KEY, JSON.stringify({
                            authenticated: true,
                            email: statusData.email
                        }));
                        setCurrentAccount(statusData.email);
                        updateAccountDisplay();
                        showToast(`Logged in with Gmail: ${statusData.email}`, 'success');

                        // Load emails after successful Gmail login
                        setTimeout(() => {
                            loadEmails();
                        }, 1000);

                        closeModal();
                    }
                }, 1000);

                // Stop checking after 5 minutes
                setTimeout(() => clearInterval(checkInterval), 300000);
            } else {
                showToast(data.error || 'Gmail login failed', 'error');
            }
        } catch (e) {
            showToast('Gmail login error: ' + e.message, 'error');
            console.error('Gmail login error:', e);
        }
    });

    // Gmail disconnect handler
    if (gmailDisconnectBtn) {
        gmailDisconnectBtn.addEventListener('click', async () => {
            try {
                await fetch('/api/gmail/logout', { method: 'POST' });
                localStorage.removeItem(GMAIL_AUTH_KEY);
                if (gmailSection) {
                    gmailSection.style.display = 'none';
                }
                showToast('Disconnected from Gmail', 'success');
            } catch (e) {
                showToast('Error disconnecting Gmail: ' + e.message, 'error');
            }
        });
    }

    // Event listeners
    accountIconBtn.addEventListener('click', openModal);

    // Refresh email button
    const refreshEmailBtn = document.getElementById('refreshEmailBtn');
    if (refreshEmailBtn) {
        refreshEmailBtn.addEventListener('click', async () => {
            refreshEmailBtn.disabled = true;
            refreshEmailBtn.style.opacity = '0.5';
            await loadEmails();
            refreshEmailBtn.disabled = false;
            refreshEmailBtn.style.opacity = '1';
        });
    }

    modalOverlay.addEventListener('click', closeModal);
    modalCloseBtn.addEventListener('click', closeModal);
    switchToRegisterLink.addEventListener('click', (e) => {
        e.preventDefault();
        switchToRegister();
    });
    switchToLoginLink.addEventListener('click', (e) => {
        e.preventDefault();
        switchToLogin();
    });
    logoutBtn.addEventListener('click', async () => {
        try {
            const sessionToken = localStorage.getItem(SESSION_TOKEN_KEY);
            if (sessionToken) {
                await fetch('/api/email/logout', {
                    method: 'POST',
                    headers: { 'X-Session-Token': sessionToken }
                });
            }
            localStorage.removeItem(SESSION_TOKEN_KEY);
            localStorage.removeItem(CURRENT_ACCOUNT_KEY);
            updateAccountDisplay();
            showToast('Logged out', 'success');
        } catch (e) {
            console.error('Logout error:', e);
            localStorage.removeItem(SESSION_TOKEN_KEY);
            localStorage.removeItem(CURRENT_ACCOUNT_KEY);
            updateAccountDisplay();
        }
    });
    switchAccountBtn.addEventListener('click', () => {
        switchToLogin();
    });

    // Prevent modal closing when clicking on modal content
    emailAuthModal.addEventListener('click', (e) => {
        if (e.target === emailAuthModal) {
            closeModal();
        }
    });

    // Initialize on page load
    initEmailService();

    // Auto-refresh emails every 3 minutes
    setInterval(() => {
        const gmailAuth = localStorage.getItem(GMAIL_AUTH_KEY);
        if (gmailAuth) {
            loadEmails().catch(e => console.error('Auto-refresh error:', e));
        }
    }, 180000); // 3 minutes

    // ─── Helpers ───
    function escapeHtml(text) { const d = document.createElement("div"); d.textContent = text; return d.innerHTML; }
});