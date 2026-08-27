(() => {
    "use strict";

    const state = {
        token: localStorage.getItem("echo_token") || "",
        userId: Number(localStorage.getItem("echo_user_id") || 0),
        username: localStorage.getItem("echo_username") || "",
        role: localStorage.getItem("echo_role") || "learner",
        program: null,
        modules: [],
        moduleId: null,
        knowledgePoints: [],
        microLearners: [],
        quizPreviewId: null,
        sessionId: null,
        assessmentProgress: null,
        authMode: "login",
        mediaRecorder: null,
        mediaChunks: [],
        recordedBlob: null,
        activeVideoId: null,
        activeVideoProgress: null,
        videos: [],
        activeCheckpoints: [],
        triggeredCheckpointIds: new Set(),
        activeCheckpoint: null,
        selectedAdminVideoId: null,
        adminVideos: [],
        videoCheckpoints: new Set(),
        videoEvidenceContext: null,
        lastVideoProgressSave: 0,
        charts: {},
    };

    const $ = (selector) => document.querySelector(selector);
    const $$ = (selector) => Array.from(document.querySelectorAll(selector));

    function iconRefresh() {
        if (window.lucide) window.lucide.createIcons();
    }

    function toast(message) {
        const node = $("#toast");
        node.textContent = message;
        node.classList.add("show");
        window.setTimeout(() => node.classList.remove("show"), 2600);
    }

    async function api(path, options = {}) {
        const headers = new Headers(options.headers || {});
        if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
        if (options.body && !(options.body instanceof FormData)) {
            headers.set("Content-Type", "application/json");
        }
        const response = await fetch(path, {...options, headers});
        if (response.status === 401) {
            logout();
            throw new Error("登录已失效，请重新登录");
        }
        if (!response.ok) {
            let detail = `请求失败（${response.status}）`;
            try {
                const payload = await response.json();
                detail = payload.detail || detail;
                if (typeof detail === "object") detail = detail.message || JSON.stringify(detail);
            } catch (_) {
                // Keep the HTTP fallback when a service returns no JSON body.
            }
            throw new Error(detail);
        }
        return response;
    }

    function setAuthMode(mode) {
        state.authMode = mode;
        const register = mode === "register";
        $("#auth-title").textContent = register ? "开始你的学习路径" : "欢迎回来";
        $("#auth-submit-label").textContent = register ? "创建账号" : "继续学习";
        $("#auth-mode-toggle").textContent = register ? "已有账号？返回登录" : "第一次使用？创建学习账号";
        $("#auth-error").textContent = "";
    }

    async function submitAuth(event) {
        event.preventDefault();
        const username = $("#auth-username").value.trim();
        const password = $("#auth-password").value;
        const endpoint = state.authMode === "register" ? "/auth/register" : "/auth/login";
        try {
            const response = await api(endpoint, {
                method: "POST",
                body: JSON.stringify({username, password}),
            });
            const payload = await response.json();
            state.token = payload.access_token;
            state.userId = Number(payload.user_id);
            state.username = payload.username;
            state.role = payload.role || "learner";
            localStorage.setItem("echo_token", state.token);
            localStorage.setItem("echo_user_id", String(state.userId));
            localStorage.setItem("echo_username", state.username);
            localStorage.setItem("echo_role", state.role);
            await enterApp();
        } catch (error) {
            $("#auth-error").textContent = error.message;
        }
    }

    function logout() {
        releaseVideoObjectUrl();
        ["echo_token", "echo_user_id", "echo_username", "echo_role"].forEach((key) => localStorage.removeItem(key));
        state.token = "";
        state.userId = 0;
        state.username = "";
        state.role = "learner";
        state.program = null;
        state.modules = [];
        state.moduleId = null;
        state.knowledgePoints = [];
        state.microLearners = [];
        state.quizPreviewId = null;
        state.sessionId = null;
        state.assessmentProgress = null;
        state.activeVideoId = null;
        state.activeVideoProgress = null;
        state.videos = [];
        state.activeCheckpoints = [];
        state.triggeredCheckpointIds = new Set();
        state.activeCheckpoint = null;
        state.videoCheckpoints = new Set();
        state.videoEvidenceContext = null;
        $("#video-empty-state").classList.remove("hidden");
        $("#video-progress-label").textContent = "尚未开始";
        $("#video-checkpoint").classList.add("hidden");
        resetPrivilegedViews();
        showView("workspace");
        $("#auth-password").value = "";
        $("#app-shell").classList.add("hidden");
        $("#auth-screen").classList.remove("hidden");
    }

    function resetPrivilegedViews() {
        $("#member-list").innerHTML = "";
        $("#member-status").textContent = "等待加载成员。";
        $("#knowledge-list").innerHTML = "";
        $("#knowledge-status").textContent = "等待上传课程材料。";
        $("#quiz-preview-list").innerHTML = "";
        $("#quiz-preview-section").classList.add("hidden");
        $("#quiz-import-status").textContent = "选择模块、知识点和题库文件后开始识别。";
        $("#mentor-learner-select").innerHTML = '<option value="">请先确认说话人</option>';
        $("#speaker-confirmed").checked = false;
        syncSpeakerBindingControl();
    }

    async function enterApp() {
        resetPrivilegedViews();
        showView("courses");
        $("#auth-screen").classList.add("hidden");
        $("#app-shell").classList.remove("hidden");
        $("#user-name").textContent = state.username || `学习者 ${state.userId}`;
        $("#user-role").textContent = roleLabel(state.role);
        $$(".manager-only").forEach((node) => {
            node.classList.toggle("hidden", !["mentor", "system_admin"].includes(state.role));
        });
        $$(".system-admin-only").forEach((node) => {
            node.classList.toggle("hidden", state.role !== "system_admin");
        });
        await loadCatalog();
        await loadMicroLearners();
        await Promise.all([restoreLatestSession(), checkHealth()]);
        await Promise.all([loadInsight(), loadResources(), loadAssessmentProgress()]);
        renderCourseCenter();
        iconRefresh();
    }

    function roleLabel(role) {
        return {learner: "学习者", mentor: "讲师 / 导师", system_admin: "系统管理员"}[role] || role;
    }

    async function checkHealth() {
        const node = $("#service-status");
        node.classList.remove("healthy", "degraded", "offline");
        try {
            const response = await api("/api/health");
            const payload = await response.json();
            if (payload.status === "ok") {
                node.classList.add("healthy");
                node.innerHTML = '<span class="status-dot"></span>系统在线';
                node.title = "业务数据库与辅助服务均可用";
                return;
            }
            const unavailable = Object.entries(payload.dependencies || {})
                .filter(([, item]) => item.status !== "ok")
                .map(([name]) => dependencyLabel(name));
            node.classList.add("degraded");
            node.innerHTML = `<span class="status-dot"></span>核心在线 · ${Number(payload.unavailable_count || unavailable.length)} 项降级`;
            node.title = unavailable.length ? `暂不可用：${unavailable.join("、")}` : "部分辅助服务暂不可用";
        } catch (error) {
            node.classList.add("offline");
            node.innerHTML = '<span class="status-dot"></span>核心服务异常';
            node.title = error.message;
        }
    }

    function dependencyLabel(name) {
        return {
            database: "业务数据库",
            punditrag_import: "知识库导入",
            punditrag_query: "官方知识检索",
            simplemem: "长期记忆",
            micro_representation: "语音微表征",
        }[name] || name;
    }

    async function loadCatalog() {
        const programsResponse = await api("/v1/catalog/programs");
        const programs = await programsResponse.json();
        state.program = programs[0];
        if (!state.program) throw new Error("尚未配置培训项目");
        $("#program-name").textContent = state.program.name;
        const modulesResponse = await api(`/v1/catalog/programs/${state.program.id}/modules`);
        state.modules = await modulesResponse.json();
        state.moduleId = state.moduleId || state.modules[0]?.id;
        const select = $("#module-select");
        select.innerHTML = state.modules
            .map((item) => `<option value="${item.id}">${escapeHtml(item.code)} · ${escapeHtml(item.name)}</option>`)
            .join("");
        select.value = String(state.moduleId || "");
        populateImportModuleSelects();
        renderCourseCenter();
    }

    async function restoreLatestSession() {
        const response = await api(`/sessions/${state.userId}`);
        const sessions = await response.json();
        const latest = sessions[0];
        if (!latest) return;
        const moduleExists = state.modules.some((item) => item.id === Number(latest.module_id));
        if (!moduleExists) return;

        state.sessionId = Number(latest.id);
        state.moduleId = Number(latest.module_id);
        $("#module-select").value = String(state.moduleId);
        $("#echo-stage").textContent = `${latest.echo_state || "E"} · ${stageLabel(latest.echo_state || "E")}`;

        const historyResponse = await api(`/history/${state.sessionId}`);
        const messages = await historyResponse.json();
        if (!messages.length) return;
        $("#chat-messages").innerHTML = "";
        messages.forEach((message) => appendMessage(message.role, message.content));
        renderCourseCenter();
    }

    function stageLabel(stage) {
        return {E: "唤起", C: "建构", H: "深化", O: "迁移"}[stage] || "唤起";
    }

    function currentModule() {
        return state.modules.find((item) => item.id === Number(state.moduleId));
    }

    function moduleFromSelect(selector) {
        const moduleId = Number($(selector)?.value || 0);
        return state.modules.find((item) => item.id === moduleId);
    }

    function populateImportModuleSelects() {
        const options = state.modules
            .map((item) => `<option value="${item.id}">${escapeHtml(item.code)} · ${escapeHtml(item.name)}</option>`)
            .join("");
        ["#material-module-select", "#quiz-module-select", "#video-module-select"].forEach((selector) => {
            const select = $(selector);
            if (!select) return;
            select.innerHTML = options;
            select.value = String(state.moduleId || state.modules[0]?.id || "");
        });
    }

    function renderCourseCenter() {
        if (!state.program) return;
        $("#course-center-title").textContent = state.program.name;
        $("#course-center-description").textContent = state.program.description
            || "围绕 Kernel、Agent、流程、部署与质量评测开展可追溯的对话训练。";
        $("#available-course-count").textContent = "1 门";
        $("#course-module-count").textContent = `${state.modules.length} 个模块`;
        const activeModule = currentModule() || state.modules[0];
        $("#course-current-module").textContent = activeModule
            ? `当前：${activeModule.code} ${activeModule.name}`
            : "尚未配置模块";
        const continueButton = $("#course-continue");
        const videoButton = $("#course-video");
        continueButton.disabled = !activeModule;
        videoButton.disabled = !activeModule;
        continueButton.querySelector("span").textContent = state.sessionId ? "继续上次学习" : "进入 ECHO 学习";
        $("#course-module-list").innerHTML = state.modules.length
            ? state.modules.map((item) => `
                <button class="course-module-item ${item.id === Number(state.moduleId) ? "active" : ""}" type="button" data-course-module-id="${item.id}">
                    <span>${escapeHtml(item.code)}</span>
                    <div><strong>${escapeHtml(item.name)}</strong><small>${courseModuleDescription(item.code)}</small></div>
                    <em>${item.id === Number(state.moduleId) ? "当前学习" : "进入模块"}</em>
                    <i data-lucide="arrow-right"></i>
                </button>`).join("")
            : '<div class="course-empty"><strong>暂时没有可学习模块</strong><span>请联系讲师检查课程目录。</span></div>';
        $$("[data-course-module-id]").forEach((button) => {
            button.addEventListener("click", () => selectCourseModule(Number(button.dataset.courseModuleId)));
        });
        updateVideoHeading();
        iconRefresh();
    }

    function courseModuleDescription(code) {
        return {
            M1: "Kernel、模型服务、提示词、插件与函数调用",
            M2: "Agent、对话状态、记忆与多智能体协作",
            M3: "流程框架、可观测、安全、部署与质量评测",
        }[code] || "按学习进度完成对话、练习与测验";
    }

    async function selectCourseModule(moduleId) {
        if (!state.modules.some((item) => item.id === moduleId)) return;
        if (moduleId !== Number(state.moduleId)) {
            $("#module-select").value = String(moduleId);
            await changeModule();
        }
        showView("workspace");
    }

    function openCourseWorkspace() {
        if (!currentModule()) return;
        showView("workspace");
        $("#chat-input").focus();
    }

    function openVideoLearning() {
        if (!currentModule()) return;
        updateVideoHeading();
        loadCourseVideos();
        showView("video");
    }

    function updateVideoHeading() {
        const module = currentModule();
        if (!module) return;
        $("#video-module-label").textContent = `${module.code} ${module.name}`;
        if (!state.activeVideoId) $("#video-lesson-title").textContent = "选择一段课程视频";
    }

    async function loadVideoKnowledgePoints() {
        const select = $("#video-knowledge-point");
        if (!state.moduleId) {
            select.innerHTML = '<option value="">尚未选择模块</option>';
            return;
        }
        select.disabled = true;
        select.innerHTML = '<option value="">读取知识点中</option>';
        try {
            const response = await api(`/v1/catalog/modules/${state.moduleId}/knowledge-points`);
            const items = await response.json();
            select.innerHTML = items.length
                ? items.map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("")
                : '<option value="">本模块暂无知识点</option>';
            select.disabled = !items.length;
        } catch (error) {
            select.innerHTML = '<option value="">知识点加载失败</option>';
            select.disabled = true;
        }
    }

    function releaseVideoObjectUrl() {
        const player = $("#course-video-player");
        if (player) {
            player.pause();
            player.removeAttribute("src");
            player.load();
        }
        state.activeVideoId = null;
        state.activeVideoProgress = null;
        state.videos = [];
        state.videoCheckpoints = new Set();
        const list = $("#course-video-list");
        if (list) list.innerHTML = "";
    }

    async function loadCourseVideos() {
        const module = currentModule();
        if (!module) return;
        const list = $("#course-video-list");
        list.innerHTML = '<small class="muted">正在读取课程视频…</small>';
        try {
            const response = await api(`/v1/modules/${module.id}/videos`);
            const payload = await response.json();
            state.videos = payload.items;
            renderCourseVideoList();
        } catch (error) {
            list.innerHTML = `<small class="muted">${escapeHtml(error.message)}</small>`;
        }
    }

    function renderCourseVideoList() {
        const list = $("#course-video-list");
        if (!state.videos.length) {
            list.innerHTML = '<small class="muted">当前模块还没有课程视频，请联系讲师上传。</small>';
            return;
        }
        list.innerHTML = state.videos.map((video) => {
            const progress = video.progress;
            const label = progress
                ? (progress.completed ? "已看完" : `上次看到 ${formatVideoTime(progress.current_time)}`)
                : "尚未开始";
            return `<button class="video-list-item ${video.id === state.activeVideoId ? "active" : ""}" type="button" data-video-id="${video.id}">
                <i data-lucide="circle-play"></i>
                <span><strong>${escapeHtml(video.title)}</strong><small>${label} · ${formatBytes(video.file_size)}</small></span>
            </button>`;
        }).join("");
        $$("[data-video-id]").forEach((button) => {
            button.addEventListener("click", () => {
                const video = state.videos.find((item) => item.id === Number(button.dataset.videoId));
                if (video) playCourseVideo(video);
            });
        });
        iconRefresh();
    }

    function playCourseVideo(video) {
        const player = $("#course-video-player");
        player.src = video.stream_url;
        state.activeVideoId = video.id;
        state.activeVideoProgress = video.progress;
        state.videoCheckpoints = new Set();
        state.activeCheckpoints = [];
        state.triggeredCheckpointIds = new Set();
        state.activeCheckpoint = null;
        state.lastVideoProgressSave = 0;
        $("#video-empty-state").classList.add("hidden");
        $("#video-lesson-title").textContent = video.title;
        $("#video-progress-label").textContent = "读取视频信息";
        $("#video-checkpoint").classList.add("hidden");
        renderCourseVideoList();
        loadCourseCheckpoints(video.id);
        player.load();
    }

    async function loadCourseCheckpoints(videoId) {
        try {
            const response = await api(`/v1/videos/${videoId}/checkpoints`);
            const payload = await response.json();
            state.activeCheckpoints = payload.items
                .filter((item) => item.status === "frozen")
                .sort((a, b) => a.time_offset_seconds - b.time_offset_seconds);
        } catch (_) {
            state.activeCheckpoints = [];
        }
    }

    function restoreVideoProgress() {
        const player = $("#course-video-player");
        if (!state.activeVideoId || !Number.isFinite(player.duration)) return;
        const saved = state.activeVideoProgress;
        if (saved?.current_time > 0 && saved.current_time < player.duration - 3) {
            player.currentTime = Math.min(saved.current_time, player.duration);
        }
        updateVideoProgressLabel();
    }

    function saveVideoProgress(force = false) {
        const player = $("#course-video-player");
        if (!state.activeVideoId || !Number.isFinite(player.duration) || !player.duration) return;
        const now = Date.now();
        if (!force && now - state.lastVideoProgressSave < 5000) return;
        state.lastVideoProgressSave = now;
        api(`/v1/videos/${state.activeVideoId}/progress`, {
            method: "PUT",
            body: JSON.stringify({
                current_time: Math.round(player.currentTime * 10) / 10,
                duration: Math.round(player.duration * 10) / 10,
                completed: player.ended,
            }),
        }).catch(() => undefined);
    }

    function updateVideoProgressLabel() {
        const player = $("#course-video-player");
        if (!Number.isFinite(player.duration) || !player.duration) {
            $("#video-progress-label").textContent = "尚未开始";
            return;
        }
        const percent = Math.min(100, Math.round(player.currentTime / player.duration * 100));
        $("#video-progress-label").textContent = player.ended
            ? "已看完"
            : `${formatVideoTime(player.currentTime)} / ${formatVideoTime(player.duration)}  ${percent}%`;
    }

    function handleVideoTimeUpdate() {
        const player = $("#course-video-player");
        updateVideoProgressLabel();
        saveVideoProgress();
        if (!Number.isFinite(player.duration)) return;
        if (state.activeCheckpoints.length) {
            const pending = state.activeCheckpoints.find(
                (item) => player.currentTime >= item.time_offset_seconds
                    && !state.triggeredCheckpointIds.has(item.id)
            );
            if (!pending) return;
            state.triggeredCheckpointIds.add(pending.id);
            player.pause();
            showVideoCheckpoint(pending);
            return;
        }
        if (player.duration < 40) return;
        const ratio = player.currentTime / player.duration;
        const threshold = [0.25, 0.5, 0.75].find((item) => ratio >= item && !state.videoCheckpoints.has(item));
        if (!threshold) return;
        state.videoCheckpoints.add(threshold);
        player.pause();
        showVideoCheckpoint();
    }

    function showVideoCheckpoint(checkpoint = null) {
        state.activeCheckpoint = checkpoint;
        const panel = $("#video-checkpoint");
        panel.classList.remove("hidden");
        if (checkpoint) {
            $("#video-checkpoint-title").textContent = "完成这道口述练习";
            $("#video-checkpoint-prompt").textContent = checkpoint.question;
        } else {
            $("#video-checkpoint-title").textContent = "用自己的话讲清本节内容";
            $("#video-checkpoint-prompt").textContent = "请用 30-90 秒说明你刚刚理解的关键概念，并举一个应用例子。";
        }
        panel.scrollIntoView({block: "nearest"});
        iconRefresh();
    }

    function skipVideoCheckpoint() {
        $("#video-checkpoint").classList.add("hidden");
        const player = $("#course-video-player");
        if (player.src) player.play().catch(() => undefined);
    }

    function startVideoEvidence() {
        const player = $("#course-video-player");
        player.pause();
        saveVideoProgress(true);
        const select = $("#video-knowledge-point");
        const selectedOption = select.options[select.selectedIndex];
        const module = currentModule();
        state.videoEvidenceContext = {
            moduleId: state.moduleId,
            moduleLabel: module ? `${module.code} ${module.name}` : "当前模块",
            knowledgePointId: Number(select.value) || null,
            knowledgePointLabel: selectedOption?.textContent || "本节知识点",
            promptText: state.activeCheckpoint?.question || null,
            progressPercent: Number.isFinite(player.duration) && player.duration
                ? Math.round(player.currentTime / player.duration * 100)
                : null,
        };
        $("#learner-consent").checked = false;
        renderVideoEvidenceContext();
        showView("evidence");
        setLearnerJobStatus("等待你授权并开始录音", "idle");
        $("#video-evidence-context").scrollIntoView({block: "start"});
    }

    function renderVideoEvidenceContext() {
        const context = state.videoEvidenceContext;
        const panel = $("#video-evidence-context");
        panel.classList.toggle("hidden", !context);
        if (!context) return;
        $("#video-evidence-title").textContent = `视频口述练习：${context.moduleLabel}`;
        const progress = context.progressPercent == null ? "" : `，视频进度 ${context.progressPercent}%`;
        const promptText = context.promptText
            || `请用 30-90 秒说明“${context.knowledgePointLabel}”${progress}。录音提交后只作为提示方式的辅助证据。`;
        $("#video-evidence-prompt").textContent = promptText;
        iconRefresh();
    }

    function clearVideoEvidenceContext() {
        state.videoEvidenceContext = null;
        renderVideoEvidenceContext();
    }

    function formatVideoTime(value) {
        const seconds = Math.max(0, Math.floor(Number(value) || 0));
        const minutes = Math.floor(seconds / 60);
        return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
    }

    async function changeModule() {
        const nextId = Number($("#module-select").value);
        if (!nextId || nextId === state.moduleId) return;
        if (state.sessionId) {
            await sendMessage("切换到所选培训模块", nextId);
        }
        releaseVideoObjectUrl();
        clearVideoEvidenceContext();
        $("#video-empty-state").classList.remove("hidden");
        $("#video-progress-label").textContent = "尚未开始";
        state.moduleId = nextId;
        $("#echo-stage").textContent = "E · 唤起";
        renderCourseCenter();
        await Promise.all([loadInsight(), loadResources(), loadAssessmentProgress()]);
    }

    async function loadAssessmentProgress() {
        if (!state.moduleId) return;
        try {
            const response = await api(`/v1/modules/${state.moduleId}/assessment-progress`);
            renderAssessmentProgress(await response.json());
        } catch (error) {
            renderAssessmentProgress({
                state: "unavailable",
                title: "学习进度暂不可用",
                description: error.message,
                button_label: "稍后重试",
                button_enabled: false,
            });
        }
    }

    function renderAssessmentProgress(progress) {
        state.assessmentProgress = progress || null;
        const panel = $("#assessment-next");
        panel.dataset.state = progress?.state || "unavailable";
        $("#assessment-title").textContent = progress?.title || "正在读取学习进度";
        $("#assessment-description").textContent = progress?.description
            || "系统会根据作答证据安排下一步。";
        $("#assessment-action-label").textContent = progress?.button_label || "加载中";
        $("#assessment-action").disabled = !progress?.button_enabled;
        iconRefresh();
    }

    async function triggerAssessmentAction() {
        const progress = state.assessmentProgress;
        if (!progress?.button_enabled) return;
        if (progress.next_action === "view_report") {
            showView("insight");
            return;
        }
        if (progress.command_text) await sendMessage(progress.command_text);
    }

    function showView(viewName) {
        $$(".nav-item").forEach((button) => button.classList.toggle(
            "active",
            button.dataset.view === viewName || (viewName === "video" && button.dataset.view === "courses"),
        ));
        $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${viewName}`));
        document.body.dataset.view = viewName;
        if (viewName === "courses") renderCourseCenter();
        if (viewName === "video") loadVideoKnowledgePoints();
        if (viewName === "insight") loadInsight();
        if (viewName === "resources") loadResources();
        if (viewName === "content") {
            loadKnowledgeDocuments();
            loadQuizKnowledgePoints();
        }
        if (viewName === "members") loadMembers();
        if (viewName === "demo") loadDemoTrace();
        iconRefresh();
    }

    function appendMessage(role, content) {
        const container = $("#chat-messages");
        const empty = container.querySelector(".empty-state");
        if (empty) empty.remove();
        const message = document.createElement("div");
        message.className = `message ${role}`;
        message.textContent = content;
        container.appendChild(message);
        container.scrollTop = container.scrollHeight;
    }

    async function parseNdjson(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        const result = {meta: null, content: ""};
        while (true) {
            const {done, value} = await reader.read();
            buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) {
                if (!line.trim()) continue;
                const item = JSON.parse(line);
                if (item.type === "meta") result.meta = item;
                if (item.type === "content") result.content += item.content || "";
            }
            if (done) break;
        }
        if (buffer.trim()) {
            const item = JSON.parse(buffer);
            if (item.type === "meta") result.meta = item;
            if (item.type === "content") result.content += item.content || "";
        }
        return result;
    }

    async function sendMessage(text, requestedModuleId = null) {
        if (!text.trim()) return;
        appendMessage("user", text.trim());
        $("#chat-input").value = "";
        const body = {
            user_input: text.trim(),
            user_id: state.userId,
            session_id: state.sessionId,
            program_id: state.program.id,
            module_id: state.moduleId,
            request_id: crypto.randomUUID().replaceAll("-", ""),
            requested_module_id: requestedModuleId,
        };
        try {
            const response = await api("/chat", {method: "POST", body: JSON.stringify(body)});
            const result = await parseNdjson(response);
            state.sessionId = result.meta?.session_id || state.sessionId;
            appendMessage("assistant", result.content || "本轮已完成。");
            renderTrace(result.meta || {});
            renderQuiz(result.meta?.quiz);
            if (result.meta?.assessment_progress) {
                renderAssessmentProgress(result.meta.assessment_progress);
            } else {
                await loadAssessmentProgress();
            }
            setEchoStage(result.meta?.echo_state || "E");
        } catch (error) {
            appendMessage("assistant", `本轮执行失败：${error.message}`);
        }
    }

    function renderQuiz(quiz) {
        if (!quiz) return;
        const container = $("#chat-messages");
        const note = document.createElement("div");
        note.className = "quiz-note";
        const purpose = {
            pretest: "前测",
            posttest: "后测",
            stage_test: "阶段测验",
            practice: "练习",
        }[quiz.purpose] || "测验";
        const difficulty = {
            foundation: "基础",
            standard: "标准",
            advanced: "进阶",
        }[quiz.difficulty] || quiz.difficulty;
        note.textContent = `${purpose} · ${difficulty}难度。请使用“答案是：……”提交，本轮将只执行判题动作。`;
        container.appendChild(note);
    }

    function setEchoStage(stage) {
        const labels = {E: "E · 唤起", C: "C · 建构", H: "H · 深化", O: "O · 迁移"};
        $("#echo-stage").textContent = labels[stage] || stage;
    }

    function renderTrace(meta) {
        const degraded = (meta.degradation || []).filter(Boolean);
        if (degraded.length) toast("部分辅助能力暂不可用，本轮学习记录已保留");
        if (state.sessionId) loadDemoTrace();
    }

    function prettyJson(value, maxLength = 1400) {
        if (value == null) return "暂无";
        let text;
        try {
            text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
        } catch (_) {
            text = String(value);
        }
        return text.length > maxLength ? `${text.slice(0, maxLength)}\n…` : text;
    }

    function traceAgentLabel(key) {
        return {
            analysis: "学习情况分析 Agent",
            retrieval: "官方资料检索",
            generation: "内容生成 Agent",
            validation: "内容检查 Agent",
            next_action: "下一步安排 Agent",
        }[key] || key;
    }

    function traceStatusLabel(status) {
        return {
            completed: "已完成",
            completed_with_degradation: "完成（有降级）",
            failed: "失败",
            pending: "等待",
        }[status] || status || "未知";
    }

    async function loadDemoTrace() {
        const status = $("#demo-trace-status");
        const list = $("#demo-trace-list");
        if (!status || !list) return;
        if (!state.sessionId) {
            status.textContent = "进入一个学习会话后，这里会显示 Agent 输入、输出和校验过程。";
            list.innerHTML = "";
            return;
        }
        status.textContent = "正在读取服务端协作记录…";
        try {
            const response = await api(`/v1/sessions/${state.sessionId}/turns`);
            const payload = await response.json();
            const turns = payload.items || [];
            if (!turns.length) {
                status.textContent = "当前会话还没有可展示的协作记录。";
                list.innerHTML = "";
                return;
            }
            status.textContent = `当前会话 ${turns.length} 轮，按最近发生时间排列。`;
            list.innerHTML = turns.map((turn) => {
                const result = turn.result || {};
                const records = result.agent_records || {};
                const agents = Object.entries(records).map(([key, record]) => {
                    const output = record.output ?? record.output_summary ?? record.result;
                    const input = record.input_summary ?? record.input;
                    const failure = record.failure_reason;
                    return `<article class="trace-agent">
                        <header><strong>${escapeHtml(traceAgentLabel(key))}</strong><span class="trace-status ${record.status || ""}">${escapeHtml(traceStatusLabel(record.status))}</span></header>
                        <dl><div><dt>输入</dt><dd><pre>${escapeHtml(prettyJson(input))}</pre></dd></div><div><dt>输出</dt><dd><pre>${escapeHtml(prettyJson(output))}</pre></dd></div></dl>
                        ${failure ? `<p class="trace-failure">失败原因：${escapeHtml(failure)}</p>` : ""}
                        <small>${record.persisted_in_system ? "已写入系统记录" : "未确认持久化"}</small>
                    </article>`;
                }).join("");
                return `<article class="trace-turn"><header><div><span class="eyebrow">${escapeHtml(turn.primary_action || turn.intent)}</span><strong>${escapeHtml(turn.trace_id || "本轮")}</strong></div><time>${escapeHtml(formatDateTime(turn.started_at))}</time></header><div class="trace-turn-meta"><span>状态：${escapeHtml(traceStatusLabel(turn.status))}</span><span>请求：${escapeHtml(turn.request_id || "-")}</span></div>${turn.error_message ? `<p class="trace-failure">${escapeHtml(turn.error_message)}</p>` : ""}<div class="trace-agents">${agents || `<small class="muted">本轮未返回 Agent 明细。</small>`}</div></article>`;
            }).join("");
            iconRefresh();
        } catch (error) {
            status.textContent = `协作记录暂不可用：${error.message}`;
            list.innerHTML = "";
        }
    }

    function formatDateTime(value) {
        if (!value) return "";
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", {hour12: false});
    }

    async function loadInsight() {
        if (!state.moduleId || !state.userId) return;
        try {
            const response = await api(`/users/${state.userId}/learning-insight?module_id=${state.moduleId}`);
            renderInsight(await response.json());
        } catch (error) {
            toast(`洞察暂不可用：${error.message}`);
        }
    }

    function renderInsight(profile) {
        const abilityView = profile.views?.ability_and_trend || {};
        const evidenceView = profile.views?.evidence_and_blind_spots || {};
        const pathView = profile.views?.path_and_resources || {};
        const ability = abilityView.ability || {};
        ["u", "a", "r"].forEach((key) => {
            const value = Number(ability[key.toUpperCase()] || 0);
            $(`#metric-${key}`).textContent = value.toFixed(2);
            $(`#bar-${key}`).style.width = `${Math.min(100, Math.max(0, (value + 3) / 6 * 100))}%`;
        });
        $("#metric-accuracy").textContent = abilityView.average_accuracy == null
            ? "暂无"
            : `${Math.round(abilityView.average_accuracy * 100)}%`;
        $("#metric-attempts").textContent = `${ability.attempt_count || 0} 次有效作答`;
        $("#diagnosis-confidence").textContent = `诊断置信度 ${Math.round((evidenceView.diagnosis_confidence || 0) * 100)}%`;
        renderLearningPath(pathView.learning_path || []);
        $("#recommendation-reason").textContent = pathView.recommendation_reason || "先完成模块前测以建立推荐基线。";
        renderTrendChart(abilityView.daily_series || []);
        renderDifficultyChart(pathView.difficulty_match_curve || []);
    }

    function renderTags(selector, items, emptyText) {
        const node = $(selector);
        node.innerHTML = items?.length
            ? items.map((item) => `<span>${escapeHtml(item.name)}</span>`).join("")
            : `<small class="muted">${emptyText}</small>`;
    }

    function renderRecords(selector, items, emptyText, mapper) {
        const node = $(selector);
        node.innerHTML = items?.length
            ? items.slice(0, 8).map((item) => {
                const view = mapper(item);
                return `<article class="record"><strong>${escapeHtml(view.title)}</strong><small>${escapeHtml(view.detail)}</small></article>`;
            }).join("")
            : `<small class="muted">${emptyText}</small>`;
    }

    function renderLearningPath(items) {
        $("#learning-path").innerHTML = items.length
            ? items.map((item, index) => `<li><span>${index + 1}</span><strong>${escapeHtml(item.name)}</strong><em>${item.status === "priority_review" ? "优先复习" : "计划学习"}</em></li>`).join("")
            : "<li><span>1</span><strong>等待模块知识点配置</strong><em>未开始</em></li>";
    }

    function replaceChart(name, canvas, config) {
        if (!window.Chart) return;
        state.charts[name]?.destroy();
        state.charts[name] = new window.Chart(canvas, config);
    }

    function renderTrendChart(series) {
        const visible = series.slice(-14);
        replaceChart("trend", $("#trend-chart"), {
            type: "line",
            data: {
                labels: visible.map((item) => item.date.slice(5)),
                datasets: [{
                    label: "正确率",
                    data: visible.map((item) => item.attempt_count ? item.correct_count / item.attempt_count : null),
                    borderColor: "#466270",
                    backgroundColor: "rgba(70,98,112,.12)",
                    pointRadius: 3,
                    tension: .25,
                }],
            },
            options: {responsive: true, maintainAspectRatio: false, scales: {y: {min: 0, max: 1}}},
        });
    }

    function renderDifficultyChart(items) {
        replaceChart("difficulty", $("#difficulty-chart"), {
            type: "bar",
            data: {
                labels: items.map((_, index) => `作答 ${index + 1}`),
                datasets: [
                    {label: "预计答对概率", data: items.map((item) => item.predicted_probability), backgroundColor: "#466270"},
                    {label: "实际结果", data: items.map((item) => item.actual_result ? 1 : 0), backgroundColor: "#78909c"},
                ],
            },
            options: {responsive: true, maintainAspectRatio: false, scales: {y: {min: 0, max: 1}}},
        });
    }

    function eventLabel(type) {
        return {hesitation: "犹豫", guessing: "猜测", thinking_pause: "思考停顿", uncertainty: "不确定", self_correction: "自我修正"}[type] || "其他";
    }

    function memoryLabel(type) {
        return {misconception: "稳定误区", learning_preference: "学习偏好", intervention_outcome: "历史干预效果"}[type] || "长期记忆";
    }

    async function generateResources() {
        const button = $("#generate-resources");
        button.disabled = true;
        try {
            const response = await api("/v1/resources/generate", {
                method: "POST",
                body: JSON.stringify({
                    user_id: state.userId,
                    module_id: state.moduleId,
                }),
            });
            const payload = await response.json();
            renderResourcePlan(payload.plan);
            const verified = (payload.items || []).filter((item) => item.verification_passed).length;
            toast(payload.degradation?.length ? `已生成 ${payload.items?.length || 0} 项资源，其中 ${verified} 项通过校验` : "个性化资源已生成并进入人工发布门禁");
            await loadResources();
        } catch (error) {
            toast(error.message);
        } finally {
            button.disabled = false;
        }
    }

    function difficultyLabel(value) {
        return {foundation: "基础", standard: "标准", advanced: "进阶"}[value] || value;
    }

    function renderResourcePlan(plan) {
        if (!plan) return;
        $("#resource-difficulty-label").textContent = difficultyLabel(plan.difficulty);
        const reason = $("#resource-plan-reason");
        reason.textContent = `重点知识点：${plan.knowledge_point_name}。${plan.reason}提示方式：${plan.support_strategy}。`;
        reason.classList.remove("hidden");
    }

    async function loadResources() {
        if (!state.moduleId) return;
        try {
            const response = await api(`/v1/resources?module_id=${state.moduleId}`);
            const payload = await response.json();
            const node = $("#resource-list");
            if (payload.items?.length) {
                $("#resource-difficulty-label").textContent = difficultyLabel(payload.items[0].difficulty);
            } else {
                $("#resource-difficulty-label").textContent = "画像分析后确定";
                $("#resource-plan-reason").classList.add("hidden");
            }
            node.innerHTML = payload.items?.length
                ? payload.items.map(resourceCard).join("")
                : `<div class="empty-state"><strong>尚无个性化资源</strong><p>系统将根据当前画像确定知识点与难度。</p></div>`;
        } catch (_) {
            // The resource view remains usable for the first generation request.
        }
    }

    function resourceCard(item) {
        const typeLabel = {custom_note: "定制学习资料", practice_guide: "实操指南", staged_test: "阶段练习"}[item.resource_type] || item.resource_type;
        const statusLabel = {verified: "已发布", pending_review: "待人工发布", draft: "草稿"}[item.status] || item.status;
        const sources = (item.evidence_sources || []).map((source) => {
            const title = source.source_title || source.title || source.document_title || "官方资料";
            const section = source.source_section || source.section || source.chapter || "未标注章节";
            const url = source.source_url || source.url || source.link;
            const link = url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">打开出处</a>` : "无可打开链接";
            return `<li><strong>${escapeHtml(title)}</strong><span>${escapeHtml(section)} · ${link}</span></li>`;
        }).join("") || `<li class="muted">没有官方证据，资源只能保留为草稿。</li>`;
        const details = item.verification_details && Object.keys(item.verification_details).length
            ? `<pre>${escapeHtml(prettyJson(item.verification_details, 2200))}</pre>`
            : "暂无校验明细";
        const history = (item.verification_history || []).map((entry) => `<li>第 ${Number(entry.retry_count || 0) + 1} 次：${entry.passed ? "通过" : "未通过"}${entry.issues?.length ? ` · ${escapeHtml(entry.issues.join("；"))}` : ""}</li>`).join("") || "暂无重做记录";
        const publish = state.role === "mentor" || state.role === "system_admin"
            ? (item.status === "pending_review" && item.verification_passed ? `<button class="button secondary compact-button" type="button" data-publish-resource="${escapeHtml(item.resource_id)}"><i data-lucide="send"></i>人工发布</button>` : "")
            : "";
        return `<article class="resource-card">
            <header><span class="eyebrow">${escapeHtml(typeLabel)}</span><span class="resource-status ${item.status}">${escapeHtml(statusLabel)}</span></header>
            <h2>${escapeHtml(item.title)}</h2>
            <p class="resource-content">${escapeHtml(item.content)}</p>
            <p><strong>个性化理由：</strong>${escapeHtml(item.personalization_reason)}</p>
            <details class="resource-proof"><summary>查看官方引用与校验明细</summary><section><h3>官方引用（${item.evidence_sources?.length || 0}）</h3><ul>${sources}</ul><h3>校验结果</h3><div class="verification-detail">${details}</div><h3>重做历史（${item.retry_count || 0} 次）</h3><ul>${history}</ul></section></details>
            <footer><span>难度：${escapeHtml(difficultyLabel(item.difficulty))} · 证据来源：${item.evidence_sources?.length || 0}</span>${publish}</footer>
        </article>`;
    }

    async function publishResource(resourceId, button) {
        button.disabled = true;
        try {
            await api(`/v1/resources/${encodeURIComponent(resourceId)}/publish`, {method: "POST"});
            toast("资源已完成人工发布");
            await loadResources();
        } catch (error) {
            toast(`发布失败：${error.message}`);
            button.disabled = false;
        }
    }

    function openDeletionPanel() {
        $("#data-deletion-panel").classList.remove("hidden");
        $("#confirm-data-deletion").checked = false;
        $("#submit-deletion").disabled = true;
        $("#data-deletion-status").textContent = "等待确认。";
        $("#confirm-data-deletion").focus();
    }

    function closeDeletionPanel() {
        $("#data-deletion-panel").classList.add("hidden");
    }

    async function submitDataDeletion() {
        const button = $("#submit-deletion");
        button.disabled = true;
        const status = $("#data-deletion-status");
        status.textContent = "正在删除本地记录并同步外部服务…";
        try {
            const response = await api("/v1/users/me/data-deletion", {
                method: "POST",
                body: JSON.stringify({request_id: crypto.randomUUID().replaceAll("-", ""), confirm: true}),
            });
            const payload = await response.json();
            const result = payload.result || {};
            status.textContent = `${payload.status === "completed" ? "删除完成" : "删除完成，但部分外部服务需要重试"}。本地会话 ${result.local?.sessions || 0} 个，文件 ${result.files?.deleted || 0} 个。`;
            toast(payload.status === "completed" ? "学习数据已删除" : "数据已删除，部分外部同步失败");
            window.setTimeout(logout, 1400);
        } catch (error) {
            status.textContent = `删除失败：${error.message}`;
            button.disabled = false;
        }
    }

    function roleOptions(current) {
        return [
            ["learner", "学习者"],
            ["mentor", "讲师 / 导师"],
            ["system_admin", "系统管理员"],
        ].map(([value, label]) => `<option value="${value}" ${value === current ? "selected" : ""}>${label}</option>`).join("");
    }

    async function loadMembers() {
        if (state.role !== "system_admin") return;
        try {
            const response = await api("/v1/admin/users");
            const payload = await response.json();
            $("#member-list").innerHTML = (payload.items || []).map((item) => {
                const isSelf = item.id === state.userId;
                return `<tr data-member-id="${item.id}">
                    <td><strong>${escapeHtml(item.username)}</strong>${isSelf ? "<small>当前账号</small>" : ""}</td>
                    <td>${escapeHtml(roleLabel(item.role))}</td>
                    <td>${item.status === "active" ? "有效" : escapeHtml(item.status)}</td>
                    <td><select data-member-role ${isSelf ? "disabled" : ""}>${roleOptions(item.role)}</select></td>
                    <td><button class="icon-button" type="button" data-save-role title="保存身份" ${isSelf ? "disabled" : ""}><i data-lucide="save"></i></button></td>
                </tr>`;
            }).join("");
            $$("[data-save-role]").forEach((button) => {
                button.addEventListener("click", () => updateMemberRole(button.closest("[data-member-id]")));
            });
            $("#member-status").textContent = `共 ${payload.items?.length || 0} 名成员。`;
            iconRefresh();
        } catch (error) {
            $("#member-status").textContent = error.message;
        }
    }

    async function updateMemberRole(row) {
        const userId = Number(row.dataset.memberId);
        const role = row.querySelector("[data-member-role]").value;
        const button = row.querySelector("[data-save-role]");
        button.disabled = true;
        try {
            await api(`/v1/admin/users/${userId}/role`, {
                method: "PATCH",
                body: JSON.stringify({role}),
            });
            toast("成员身份已更新");
            await loadMembers();
        } catch (error) {
            toast(error.message);
            button.disabled = false;
        }
    }

    async function startOrStopRecording() {
        const button = $("#record-button");
        if (state.mediaRecorder?.state === "recording") {
            state.mediaRecorder.stop();
            button.classList.remove("is-recording");
            button.setAttribute("aria-pressed", "false");
            button.querySelector("strong").textContent = "开始录音";
            return;
        }
        if (!navigator.mediaDevices?.getUserMedia) {
            toast("当前浏览器不支持录音，请选择本地音频文件");
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({audio: true});
            state.mediaChunks = [];
            state.mediaRecorder = new MediaRecorder(stream);
            state.mediaRecorder.ondataavailable = (event) => state.mediaChunks.push(event.data);
            state.mediaRecorder.onstop = () => {
                state.recordedBlob = new Blob(state.mediaChunks, {type: state.mediaRecorder.mimeType || "audio/webm"});
                stream.getTracks().forEach((track) => track.stop());
                setLearnerJobStatus("录音已就绪，可以提交本轮音频", "ready");
            };
            state.mediaRecorder.start();
            button.classList.add("is-recording");
            button.setAttribute("aria-pressed", "true");
            button.querySelector("strong").textContent = "停止录音";
            setLearnerJobStatus("正在录音，停止后才会生成待提交音频", "recording");
        } catch (error) {
            toast(`无法开始录音：${error.message}`);
        }
    }

    function setLearnerJobStatus(message, status = "idle") {
        const statusBox = $("#learner-job-status");
        statusBox.dataset.state = status;
        $("#learner-job-status-text").textContent = message;
    }

    async function uploadLearnerAudio() {
        if (!$("#learner-consent").checked) return toast("请先确认本轮录音授权");
        const selected = $("#learner-audio-file").files[0];
        const blob = selected || state.recordedBlob;
        if (!blob) return toast("请先录音或选择音频文件");
        const data = new FormData();
        data.append("module_id", String(state.moduleId));
        data.append("source_type", "learner_voice");
        data.append("consent_granted", "true");
        if (state.sessionId) data.append("session_id", String(state.sessionId));
        if (
            state.videoEvidenceContext?.moduleId === state.moduleId
            && state.videoEvidenceContext.knowledgePointId
        ) {
            data.append("knowledge_point_id", String(state.videoEvidenceContext.knowledgePointId));
        }
        data.append("audio", blob, selected?.name || "learner-turn.webm");
        try {
            setLearnerJobStatus("正在提交并创建检测任务", "processing");
            const response = await api("/v1/micro/detection-jobs", {method: "POST", body: data});
            const payload = await response.json();
            setLearnerJobStatus(`任务 ${payload.job_id} 已提交，状态：${payload.status}`, "submitted");
        } catch (error) {
            setLearnerJobStatus(error.message, "error");
        }
    }

    async function uploadMentorAudio() {
        if (!$("#mentor-consent").checked) return toast("请先确认录音分析授权");
        const files = Array.from($("#mentor-audio-files").files);
        if (!files.length) return toast("请选择至少一个录音文件");
        const speakerConfirmed = $("#speaker-confirmed").checked;
        const learnerId = $("#mentor-learner-select").value;
        if (speakerConfirmed && !learnerId) return toast("请选择已确认的学习者");
        const data = new FormData();
        data.append("module_id", String(state.moduleId));
        data.append("consent_granted", "true");
        data.append("speaker_mapping_confirmed", String(speakerConfirmed));
        if (speakerConfirmed) data.append("learner_id", learnerId);
        files.forEach((file) => data.append("audio_files", file));
        try {
            const response = await api("/v1/micro/mentor-batches", {method: "POST", body: data});
            const payload = await response.json();
            const duplicateNote = payload.already_submitted
                ? `，${payload.already_submitted} 段录音已由其他讲师提交`
                : "";
            $("#mentor-job-status").textContent = `已创建 ${payload.accepted} 个异步检测任务${duplicateNote}。`;
        } catch (error) {
            $("#mentor-job-status").textContent = error.message;
        }
    }

    function syncSpeakerBindingControl() {
        const confirmed = $("#speaker-confirmed").checked;
        const select = $("#mentor-learner-select");
        select.disabled = !confirmed || !state.microLearners.length;
        if (!confirmed) select.value = "";
    }

    async function loadMicroLearners() {
        if (!["mentor", "system_admin"].includes(state.role)) {
            state.microLearners = [];
            syncSpeakerBindingControl();
            return;
        }
        try {
            const response = await api("/v1/micro/learners");
            state.microLearners = await response.json();
            $("#mentor-learner-select").innerHTML = [
                '<option value="">请选择学习者</option>',
                ...state.microLearners.map((learner) => (
                    `<option value="${learner.id}">${escapeHtml(learner.username)}</option>`
                )),
            ].join("");
        } catch (error) {
            state.microLearners = [];
            $("#mentor-learner-select").innerHTML = '<option value="">学员列表加载失败</option>';
            $("#mentor-job-status").textContent = error.message;
        }
        syncSpeakerBindingControl();
    }

    async function uploadKnowledge() {
        const file = $("#knowledge-file").files[0];
        const module = moduleFromSelect("#material-module-select");
        const sourceTitle = $("#knowledge-source-title").value.trim();
        const sourceUrl = $("#knowledge-source-url").value.trim();
        const sourceSection = $("#knowledge-source-section").value.trim();
        const sourceVersion = $("#knowledge-source-version").value.trim();
        if (!file || !module) return toast("请选择知识库文档");
        if (!sourceTitle || !sourceUrl || !sourceSection || !sourceVersion) {
            return toast("请完整填写资料名称、官方链接、相关章节和版本信息");
        }
        const data = new FormData();
        data.append("module_id", String(module.id));
        data.append("source_title", sourceTitle);
        data.append("source_url", sourceUrl);
        data.append("source_section", sourceSection);
        data.append("source_version", sourceVersion);
        data.append("document", file);
        try {
            const response = await api(`/v1/knowledge-bases/${module.knowledge_base_id}/documents`, {method: "POST", body: data});
            const payload = await response.json();
            $("#knowledge-status").textContent = payload.degradation || `索引任务状态：${payload.status}`;
            await loadKnowledgeDocuments();
        } catch (error) {
            $("#knowledge-status").textContent = error.message;
        }
    }

    async function loadKnowledgeDocuments() {
        const module = moduleFromSelect("#material-module-select");
        if (!module || !["mentor", "system_admin"].includes(state.role)) return;
        try {
            const response = await api(`/v1/knowledge-bases/${module.knowledge_base_id}/documents?module_id=${module.id}`);
            const payload = await response.json();
            renderRecords("#knowledge-list", payload.items, "当前模块尚未上传知识文档", (item) => ({
                title: item.source_title || item.filename,
                detail: `${item.index_status || "stored"} · ${item.source_section || "未登记章节"} · ${item.source_version || "未登记版本"} · ${item.index_error || formatBytes(item.file_size)}`,
            }));
        } catch (error) {
            $("#knowledge-status").textContent = error.message;
        }
    }

    function switchImportTab(tabName) {
        $$("[data-import-tab]").forEach((button) => {
            button.classList.toggle("active", button.dataset.importTab === tabName);
        });
        $$(".import-pane").forEach((pane) => {
            pane.classList.toggle("active", pane.id === `import-${tabName}`);
        });
        if (tabName === "materials") loadKnowledgeDocuments();
        if (tabName === "quizzes") loadQuizKnowledgePoints();
        if (tabName === "videos") {
            loadVideoKnowledgePoints();
            loadAdminVideos();
        }
        iconRefresh();
    }

    async function loadVideoKnowledgePoints() {
        const module = moduleFromSelect("#video-module-select");
        const select = $("#video-knowledge-point-select");
        if (!module || !select) return;
        try {
            const response = await api(`/v1/catalog/modules/${module.id}/knowledge-points`);
            const items = await response.json();
            select.innerHTML = [
                '<option value="">不指定</option>',
                ...items.map((item) => `<option value="${item.id}">${escapeHtml(item.code)} · ${escapeHtml(item.name)}</option>`),
            ].join("");
        } catch (error) {
            select.innerHTML = '<option value="">知识点加载失败</option>';
        }
    }

    async function loadAdminVideos() {
        const module = moduleFromSelect("#video-module-select");
        if (!module || !["mentor", "system_admin"].includes(state.role)) return;
        try {
            const response = await api(`/v1/modules/${module.id}/videos`);
            const payload = await response.json();
            state.adminVideos = payload.items;
            renderAdminVideos(state.adminVideos);
        } catch (error) {
            $("#video-upload-status").textContent = error.message;
        }
    }

    function renderAdminVideos(items) {
        const node = $("#admin-video-list");
        if (!items.length) {
            node.innerHTML = '<small class="muted">当前模块尚未上传课程视频。</small>';
            return;
        }
        node.innerHTML = items.map((item) => `
            <article class="admin-video-item ${item.id === state.selectedAdminVideoId ? "is-selected" : ""}">
                <div><strong>${escapeHtml(item.title)}</strong><small>${formatBytes(item.file_size)} · ${item.knowledge_point_id ? `知识点 ${item.knowledge_point_id}` : "未绑定知识点"}</small></div>
                <div class="row-actions">
                    <button class="button secondary" type="button" data-admin-video-select="${item.id}"><i data-lucide="list-video"></i>口述题</button>
                    <button class="button primary" type="button" data-admin-video-generate="${item.id}"><i data-lucide="sparkles"></i>生成口述题</button>
                </div>
            </article>`).join("");
        $$("[data-admin-video-select]").forEach((button) => {
            button.addEventListener("click", () => selectAdminVideo(Number(button.dataset.adminVideoSelect)));
        });
        $$("[data-admin-video-generate]").forEach((button) => {
            button.addEventListener("click", () => generateCheckpoints(Number(button.dataset.adminVideoGenerate)));
        });
        iconRefresh();
    }

    function selectAdminVideo(videoId) {
        state.selectedAdminVideoId = videoId;
        renderAdminVideos(state.adminVideos);
        const selected = state.adminVideos.find((item) => item.id === videoId);
        $("#admin-checkpoint-video-label").textContent = selected?.title || "";
        $("#generate-checkpoints").disabled = false;
        $("#freeze-checkpoints").disabled = false;
        loadAdminCheckpoints();
    }

    async function loadAdminCheckpoints() {
        if (!state.selectedAdminVideoId) return;
        try {
            const response = await api(`/v1/videos/${state.selectedAdminVideoId}/checkpoints`);
            const payload = await response.json();
            renderAdminCheckpoints(payload.items);
        } catch (error) {
            $("#admin-checkpoint-status").textContent = error.message;
        }
    }

    function renderAdminCheckpoints(items) {
        const node = $("#admin-checkpoint-list");
        if (!items.length) {
            node.innerHTML = '<small class="muted">该视频还没有口述题，点击“生成口述题”。</small>';
            return;
        }
        node.innerHTML = items.map((item) => `
            <article class="checkpoint-item" data-checkpoint-id="${item.id}">
                <div class="checkpoint-head"><strong>${formatVideoTime(item.time_offset_seconds)} · ${item.status === "frozen" ? "已冻结" : "草稿"}</strong></div>
                <label>题干<textarea data-checkpoint-field="question">${escapeHtml(item.question)}</textarea></label>
                <label>参考要点（可选，每行一条）<textarea data-checkpoint-field="points">${escapeHtml((item.expected_points || []).join("\n"))}</textarea></label>
                <label>官方出处（可选，每行一个 URL）<textarea data-checkpoint-field="sources">${escapeHtml((item.official_sources || []).join("\n"))}</textarea></label>
                <div class="row-actions"><button class="button secondary" type="button" data-checkpoint-save="${item.id}"><i data-lucide="save"></i>保存</button></div>
            </article>`).join("");
        $$("[data-checkpoint-save]").forEach((button) => {
            button.addEventListener("click", () => saveCheckpoint(Number(button.dataset.checkpointSave)));
        });
        iconRefresh();
    }

    async function saveCheckpoint(checkpointId) {
        const row = $(`[data-checkpoint-id="${checkpointId}"]`);
        const question = row.querySelector('[data-checkpoint-field="question"]').value.trim();
        const points = row.querySelector('[data-checkpoint-field="points"]').value
            .split("\n").map((item) => item.trim()).filter(Boolean);
        const sources = row.querySelector('[data-checkpoint-field="sources"]').value
            .split("\n").map((item) => item.trim()).filter(Boolean);
        try {
            await api(`/v1/videos/${state.selectedAdminVideoId}/checkpoints/${checkpointId}`, {
                method: "PUT",
                body: JSON.stringify({question, expected_points: points, official_sources: sources}),
            });
            $("#admin-checkpoint-status").textContent = "已保存口述题修改。";
        } catch (error) {
            $("#admin-checkpoint-status").textContent = error.message;
        }
    }

    async function generateCheckpoints(videoId) {
        const status = $("#admin-checkpoint-status");
        status.textContent = "正在提交抽帧识别任务…";
        try {
            const response = await api(`/v1/videos/${videoId}/generate-checkpoints`, {method: "POST"});
            const payload = await response.json();
            status.textContent = `任务 ${payload.job_id} 已提交，正在抽帧识别。`;
            pollVideoAnalysisJob(payload.job_id);
        } catch (error) {
            status.textContent = error.message;
        }
    }

    async function pollVideoAnalysisJob(jobId) {
        for (let index = 0; index < 30; index++) {
            await new Promise((resolve) => setTimeout(resolve, 2000));
            try {
                const response = await api(`/v1/video-analysis/${jobId}`);
                const payload = await response.json();
                if (["completed", "failed", "requires_manual"].includes(payload.status)) {
                    $("#admin-checkpoint-status").textContent = payload.status === "completed"
                        ? `已生成口述题草稿，请逐条核对后冻结。`
                        : (payload.error || "生成失败");
                    loadAdminCheckpoints();
                    return;
                }
                $("#admin-checkpoint-status").textContent = `识别中（${payload.status}）…`;
            } catch (_) {
                // Keep polling while the background task is still running.
            }
        }
    }

    async function freezeCheckpoints() {
        if (!state.selectedAdminVideoId) return;
        try {
            const response = await api(`/v1/videos/${state.selectedAdminVideoId}/checkpoints/freeze`, {method: "POST"});
            const payload = await response.json();
            $("#admin-checkpoint-status").textContent = `已冻结 ${payload.items.length} 条口述题。`;
            loadAdminCheckpoints();
        } catch (error) {
            $("#admin-checkpoint-status").textContent = error.message;
        }
    }

    async function uploadVideos() {
        const module = moduleFromSelect("#video-module-select");
        const files = $("#video-files").files;
        const knowledgePointId = Number($("#video-knowledge-point-select").value) || null;
        if (!module || !files.length) return toast("请选择学习模块和至少一个视频文件");
        const data = new FormData();
        if (knowledgePointId) data.append("knowledge_point_id", String(knowledgePointId));
        Array.from(files).forEach((file) => data.append("files", file));
        const status = $("#video-upload-status");
        status.textContent = `正在上传 ${files.length} 个视频…`;
        try {
            const response = await api(`/v1/modules/${module.id}/videos`, {method: "POST", body: data});
            const payload = await response.json();
            status.textContent = `已上传 ${payload.items.length} 个视频，共 ${formatBytes(payload.total_size)}。`;
            $("#video-files").value = "";
            await loadAdminVideos();
        } catch (error) {
            status.textContent = error.message;
        }
    }

    async function loadQuizKnowledgePoints() {
        const module = moduleFromSelect("#quiz-module-select");
        const select = $("#quiz-knowledge-select");
        if (!module || !select) return;
        try {
            const response = await api(`/v1/catalog/modules/${module.id}/knowledge-points`);
            state.knowledgePoints = await response.json();
            select.innerHTML = state.knowledgePoints
                .map((item) => `<option value="${item.id}">${escapeHtml(item.code)} · ${escapeHtml(item.name)}</option>`)
                .join("");
        } catch (error) {
            $("#quiz-import-status").textContent = error.message;
        }
    }

    function setImportStep(step) {
        $$(".import-steps li").forEach((item) => {
            item.classList.toggle("active", Number(item.dataset.importStep) <= step);
        });
    }

    async function previewQuizImport() {
        const module = moduleFromSelect("#quiz-module-select");
        const knowledgePointId = Number($("#quiz-knowledge-select").value || 0);
        const file = $("#quiz-file").files[0];
        if (!module || !knowledgePointId || !file) {
            return toast("请先选择模块、知识点和题库文件");
        }
        const button = $("#preview-quiz-import");
        const data = new FormData();
        data.append("module_id", String(module.id));
        data.append("knowledge_point_id", String(knowledgePointId));
        data.append("document", file);
        button.disabled = true;
        $("#quiz-import-status").textContent = "正在读取并识别题目…";
        setImportStep(2);
        try {
            const response = await api("/v1/quiz-imports/preview", {method: "POST", body: data});
            const payload = await response.json();
            state.quizPreviewId = payload.preview_id;
            renderQuizPreview(payload.items || []);
            $("#quiz-import-status").textContent = `已从 ${payload.filename} 识别 ${payload.items.length} 道题，请逐题检查。`;
            setImportStep(3);
        } catch (error) {
            state.quizPreviewId = null;
            $("#quiz-preview-section").classList.add("hidden");
            $("#quiz-import-status").textContent = error.message;
            setImportStep(1);
        } finally {
            button.disabled = false;
        }
    }

    function selectOptions(options, current) {
        return options
            .map(([value, label]) => `<option value="${value}" ${value === current ? "selected" : ""}>${label}</option>`)
            .join("");
    }

    function renderQuizPreview(items) {
        const container = $("#quiz-preview-list");
        $("#quiz-preview-section").classList.remove("hidden");
        $("#quiz-preview-count").textContent = `${items.length} 道题`;
        container.innerHTML = items.map((item, index) => `
            <article class="quiz-preview-item" data-quiz-index="${index}">
                <header>
                    <label class="include-question"><input type="checkbox" data-include checked>导入第 ${index + 1} 题</label>
                    <span class="preview-validity"></span>
                </header>
                <div class="quiz-editor-grid">
                    <label class="span-2">题目<textarea rows="3" data-field="content">${escapeHtml(item.content)}</textarea></label>
                    <label>题目用途<select data-field="purpose">${selectOptions([
                        ["pretest", "前测"],
                        ["posttest", "后测"],
                        ["stage_test", "阶段测试"],
                        ["practice", "练习"],
                    ], item.purpose)}</select></label>
                    <label>难度<select data-field="difficulty">${selectOptions([
                        ["foundation", "基础"],
                        ["standard", "标准"],
                        ["advanced", "进阶"],
                    ], item.difficulty)}</select></label>
                    <label>题型<select data-field="type">${selectOptions([
                        ["Open", "开放题"],
                        ["MCQ", "选择题"],
                        ["TrueFalse", "判断题"],
                        ["Scenario", "情境题"],
                        ["Project", "操作题"],
                    ], item.type)}</select></label>
                    <label class="mirt-toggle"><span>更新 MIRT</span><input type="checkbox" data-field="counts_for_mirt" ${item.counts_for_mirt ? "checked" : ""}></label>
                    <label class="span-2">答案<textarea rows="2" data-field="answer">${escapeHtml(item.answer)}</textarea></label>
                    <label class="span-2">评分方法<textarea rows="2" data-field="scoring_method">${escapeHtml(item.scoring_method)}</textarea></label>
                    <label>资料名称<input data-field="source_title" value="${escapeHtml(item.source_title)}"></label>
                    <label>出处章节<input data-field="source_section" value="${escapeHtml(item.source_section)}"></label>
                    <label class="span-2">官方链接<input data-field="source_url" type="url" value="${escapeHtml(item.source_url)}" placeholder="https://learn.microsoft.com/..."></label>
                </div>
            </article>
        `).join("");
        container.querySelectorAll("input, select, textarea").forEach((input) => {
            input.addEventListener("input", updateQuizPreviewValidation);
            input.addEventListener("change", updateQuizPreviewValidation);
        });
        updateQuizPreviewValidation();
        iconRefresh();
    }

    function readQuizPreviewItems() {
        return $$(".quiz-preview-item")
            .filter((card) => card.querySelector("[data-include]").checked)
            .map((card) => {
                const value = (field) => card.querySelector(`[data-field="${field}"]`).value.trim();
                return {
                    content: value("content"),
                    answer: value("answer"),
                    type: value("type"),
                    purpose: value("purpose"),
                    difficulty: value("difficulty"),
                    scoring_method: value("scoring_method"),
                    source_title: value("source_title"),
                    source_url: value("source_url"),
                    source_section: value("source_section"),
                    counts_for_mirt: card.querySelector('[data-field="counts_for_mirt"]').checked,
                };
            });
    }

    function missingQuizFields(card) {
        const labels = {
            content: "题目",
            answer: "答案",
            scoring_method: "评分方法",
            source_title: "资料名称",
            source_url: "官方链接",
            source_section: "出处章节",
        };
        return Object.entries(labels)
            .filter(([field]) => !card.querySelector(`[data-field="${field}"]`).value.trim())
            .map(([, label]) => label);
    }

    function updateQuizPreviewValidation() {
        let selected = 0;
        let valid = true;
        $$(".quiz-preview-item").forEach((card) => {
            const included = card.querySelector("[data-include]").checked;
            card.classList.toggle("excluded", !included);
            const missing = included ? missingQuizFields(card) : [];
            if (included) selected += 1;
            if (missing.length) valid = false;
            const status = card.querySelector(".preview-validity");
            status.className = `preview-validity ${missing.length ? "invalid" : "valid"}`;
            status.textContent = included
                ? (missing.length ? `待补充：${missing.join("、")}` : "检查通过")
                : "已排除";
        });
        $("#confirm-quiz-import").disabled = !state.quizPreviewId || !selected || !valid;
        $("#quiz-preview-count").textContent = `${selected} 道待导入`;
    }

    async function confirmQuizImport() {
        const items = readQuizPreviewItems();
        if (!state.quizPreviewId || !items.length) return toast("没有可确认的题目");
        const button = $("#confirm-quiz-import");
        button.disabled = true;
        $("#quiz-import-status").textContent = "正在写入固定题库…";
        try {
            const response = await api(`/v1/quiz-imports/${state.quizPreviewId}/confirm`, {
                method: "POST",
                body: JSON.stringify({items}),
            });
            const payload = await response.json();
            $("#quiz-import-status").textContent = `已导入 ${payload.imported_count} 道题，跳过 ${payload.skipped_count} 道重复题。`;
            setImportStep(4);
            state.quizPreviewId = null;
            $("#quiz-preview-section").classList.add("hidden");
            $("#quiz-file").value = "";
            toast("固定题库导入完成");
            if (Number($("#quiz-module-select").value) === Number(state.moduleId)) {
                await loadAssessmentProgress();
            }
        } catch (error) {
            $("#quiz-import-status").textContent = error.message;
            updateQuizPreviewValidation();
        }
    }

    function formatBytes(value) {
        if (value < 1024) return `${value} B`;
        if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
        return `${(value / 1024 / 1024).toFixed(1)} MB`;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function bindEvents() {
        $("#auth-form").addEventListener("submit", submitAuth);
        $("#auth-mode-toggle").addEventListener("click", () => setAuthMode(state.authMode === "login" ? "register" : "login"));
        $("#logout-button").addEventListener("click", logout);
        $("#delete-data-button").addEventListener("click", openDeletionPanel);
        $("#close-deletion").addEventListener("click", closeDeletionPanel);
        $("#cancel-deletion").addEventListener("click", closeDeletionPanel);
        $("#confirm-data-deletion").addEventListener("change", (event) => {
            $("#submit-deletion").disabled = !event.target.checked;
        });
        $("#submit-deletion").addEventListener("click", submitDataDeletion);
        $("#course-continue").addEventListener("click", openCourseWorkspace);
        $("#course-video").addEventListener("click", openVideoLearning);
        $("#video-back-to-course").addEventListener("click", () => showView("courses"));
        $("#course-video-player").addEventListener("loadedmetadata", restoreVideoProgress);
        $("#course-video-player").addEventListener("timeupdate", handleVideoTimeUpdate);
        $("#course-video-player").addEventListener("pause", () => saveVideoProgress(true));
        $("#course-video-player").addEventListener("ended", () => {
            saveVideoProgress(true);
            updateVideoProgressLabel();
        });
        $("#course-video-player").addEventListener("play", () => $("#video-checkpoint").classList.add("hidden"));
        $("#video-start-evidence").addEventListener("click", startVideoEvidence);
        $("#video-manual-evidence").addEventListener("click", () => {
            $("#course-video-player").pause();
            showVideoCheckpoint();
        });
        $("#video-skip-checkpoint").addEventListener("click", skipVideoCheckpoint);
        $("#clear-video-evidence").addEventListener("click", clearVideoEvidenceContext);
        $("#module-select").addEventListener("change", changeModule);
        $$(".nav-item").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
        $("#chat-form").addEventListener("submit", (event) => {
            event.preventDefault();
            sendMessage($("#chat-input").value);
        });
        $$('[data-chat-prompt]').forEach((button) => {
            button.addEventListener("click", () => sendMessage(button.dataset.chatPrompt || ""));
        });
        $("#assessment-action").addEventListener("click", triggerAssessmentAction);
        $$(".segmented button").forEach((button) => button.addEventListener("click", () => {
            $$(".segmented button").forEach((item) => item.classList.toggle("active", item === button));
            $$(".insight-pane").forEach((pane) => pane.classList.toggle("active", pane.id === `insight-${button.dataset.insightTab}`));
        }));
        $("#refresh-insight").addEventListener("click", loadInsight);
        $("#refresh-demo-trace").addEventListener("click", loadDemoTrace);
        $("#generate-resources").addEventListener("click", generateResources);
        $("#resource-list").addEventListener("click", (event) => {
            const button = event.target.closest("[data-publish-resource]");
            if (button) publishResource(button.dataset.publishResource, button);
        });
        $("#refresh-members").addEventListener("click", loadMembers);
        $("#record-button").addEventListener("click", startOrStopRecording);
        $("#learner-audio-file").addEventListener("change", (event) => {
            const selected = event.target.files[0];
            $("#learner-audio-file-name").textContent = selected?.name || "MP3、WAV、M4A 或 WebM";
            if (selected) setLearnerJobStatus("已选择本地音频，可以提交", "ready");
        });
        $("#upload-learner-audio").addEventListener("click", uploadLearnerAudio);
        $("#upload-mentor-audio").addEventListener("click", uploadMentorAudio);
        $("#speaker-confirmed").addEventListener("change", syncSpeakerBindingControl);
        $("#upload-knowledge").addEventListener("click", uploadKnowledge);
        $("#material-module-select").addEventListener("change", loadKnowledgeDocuments);
        $("#quiz-module-select").addEventListener("change", () => {
            setImportStep(1);
            loadQuizKnowledgePoints();
        });
        $("#video-module-select").addEventListener("change", () => {
            state.selectedAdminVideoId = null;
            $("#admin-checkpoint-video-label").textContent = "未选择视频";
            $("#generate-checkpoints").disabled = true;
            $("#freeze-checkpoints").disabled = true;
            $("#admin-checkpoint-list").innerHTML = "";
            loadVideoKnowledgePoints();
            loadAdminVideos();
        });
        $("#upload-videos").addEventListener("click", uploadVideos);
        $("#generate-checkpoints").addEventListener("click", () => generateCheckpoints(state.selectedAdminVideoId));
        $("#freeze-checkpoints").addEventListener("click", freezeCheckpoints);
        $$("[data-import-tab]").forEach((button) => {
            button.addEventListener("click", () => switchImportTab(button.dataset.importTab));
        });
        $("#preview-quiz-import").addEventListener("click", previewQuizImport);
        $("#confirm-quiz-import").addEventListener("click", confirmQuizImport);
    }

    bindEvents();
    iconRefresh();
    if (state.token && state.userId) {
        enterApp().catch((error) => {
            toast(error.message);
            logout();
        });
    }
})();
