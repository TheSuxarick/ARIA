/* ARIA Smart Home Dashboard — Core JS */

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
        const dirs = ["N","NE","E","SE","S","SW","W","NW"];
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
            const dayNames = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
            const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
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
        } catch {}
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

    // ─── D-Pad ───
    document.querySelectorAll(".dpad-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const map = { "dpad-up": "cam_up", "dpad-down": "cam_down", "dpad-left": "cam_left", "dpad-right": "cam_right", "dpad-center": "cam_center" };
            for (const [cls, key] of Object.entries(map)) {
                if (btn.classList.contains(cls)) { showToast(t(key), "info"); break; }
            }
        });
    });

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
            const resp = await fetch('/api/emails/inbox?max_results=10');
            const data = await resp.json();

            const emailContent = document.getElementById('emailContent');
            if (!emailContent) return;

            if (!data.emails || data.emails.length === 0) {
                emailContent.innerHTML = `
                    <div class="placeholder-content">
                        <span class="material-icons-round">mail_outline</span>
                        <p>No emails yet</p>
                    </div>
                `;
                return;
            }

            // Display emails
            let html = '<div class="emails-list" style="max-height: 400px; overflow-y: auto;">';
            
            data.emails.forEach(email => {
                const date = new Date(email.date);
                const dateStr = date.toLocaleDateString();
                html += `
                    <div class="email-item" style="padding: 12px; border-bottom: 1px solid var(--border-color); cursor: pointer; transition: background 0.2s;">
                        <div style="display: flex; justify-content: space-between; align-items: start; gap: 10px;">
                            <div style="flex: 1; min-width: 0;">
                                <p style="margin: 0; font-weight: 500; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(email.from)}</p>
                                <p style="margin: 4px 0 0 0; font-size: 12px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(email.subject)}</p>
                            </div>
                            <span style="font-size: 11px; color: var(--text-secondary); white-space: nowrap;">${dateStr}</span>
                        </div>
                        <p style="margin: 8px 0 0 0; font-size: 12px; color: var(--text-secondary); line-height: 1.4;">${escapeHtml(email.body)}</p>
                    </div>
                `;
            });

            html += '</div>';
            emailContent.innerHTML = html;
        } catch (e) {
            console.error('Load emails error:', e);
            const emailContent = document.getElementById('emailContent');
            if (emailContent) {
                emailContent.innerHTML = `
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
        accountAvatar.textContent = letter;
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
