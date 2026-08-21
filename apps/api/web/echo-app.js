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
        quizPreviewId: null,
        sessionId: null,
        authMode: "login",
        mediaRecorder: null,
        mediaChunks: [],
        recordedBlob: null,
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
        $("#auth-title").textContent = register ? "创建学习者账号" : "登录工作台";
        $("#auth-submit-label").textContent = register ? "创建并登录" : "登录";
        $("#auth-mode-toggle").textContent = register ? "已有账号？返回登录" : "没有账号？创建学习者账号";
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
        ["echo_token", "echo_user_id", "echo_username", "echo_role"].forEach((key) => localStorage.removeItem(key));
        state.token = "";
        state.userId = 0;
        state.username = "";
        state.role = "learner";
        state.program = null;
        state.modules = [];
        state.moduleId = null;
        state.knowledgePoints = [];
        state.quizPreviewId = null;
        state.sessionId = null;
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
    }

    async function enterApp() {
        resetPrivilegedViews();
        showView("workspace");
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
        await Promise.all([restoreLatestSession(), checkHealth()]);
        await Promise.all([loadInsight(), loadResources()]);
        iconRefresh();
    }

    function roleLabel(role) {
        return {learner: "学习者", mentor: "讲师 / 导师", system_admin: "系统管理员"}[role] || role;
    }

    async function checkHealth() {
        try {
            const response = await api("/api/health");
            await response.json();
            $("#service-status").innerHTML = '<span class="status-dot"></span>系统在线';
        } catch (error) {
            $("#service-status").textContent = "服务异常";
        }
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
        ["#material-module-select", "#quiz-module-select"].forEach((selector) => {
            const select = $(selector);
            if (!select) return;
            select.innerHTML = options;
            select.value = String(state.moduleId || state.modules[0]?.id || "");
        });
    }

    async function changeModule() {
        const nextId = Number($("#module-select").value);
        if (!nextId || nextId === state.moduleId) return;
        if (state.sessionId) {
            await sendMessage("切换到所选培训模块", nextId);
        }
        state.moduleId = nextId;
        $("#echo-stage").textContent = "E · 唤起";
        await Promise.all([loadInsight(), loadResources()]);
    }

    function showView(viewName) {
        $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === viewName));
        $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${viewName}`));
        if (viewName === "insight") loadInsight();
        if (viewName === "resources") loadResources();
        if (viewName === "content") {
            loadKnowledgeDocuments();
            loadQuizKnowledgePoints();
        }
        if (viewName === "members") loadMembers();
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
            setEchoStage(result.meta?.echo_state || "E");
        } catch (error) {
            appendMessage("assistant", `本轮执行失败：${error.message}`);
        }
    }

    function renderQuiz(quiz) {
        if (!quiz) return;
        const container = $("#chat-messages");
        const note = document.createElement("div");
        note.className = "trace-detail";
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
        $$(".agent-loop li").forEach((item) => item.classList.remove("active"));
        const action = meta.primary_action || "";
        const active = action === "LEARNING_DIALOGUE"
            ? ["diagnosis", "retrieval", "decision"]
            : action === "GENERATE_QUIZ" || action === "GRADE_ANSWER"
                ? ["diagnosis", "decision"]
                : ["decision"];
        active.forEach((step) => $(`[data-agent-step="${step}"]`)?.classList.add("active"));
        const degraded = (meta.degradation || []).filter(Boolean);
        $("#trace-detail").textContent = [
            `意图：${meta.intent || "—"}`,
            `主要动作：${action || "—"}`,
            `Trace：${meta.trace_id || "—"}`,
            degraded.length ? `降级：${degraded.join("；")}` : "依赖服务：正常或未触发",
        ].join("\n");
        loadTurns();
    }

    async function loadTurns() {
        if (!state.sessionId) return;
        try {
            const response = await api(`/v1/sessions/${state.sessionId}/turns`);
            const payload = await response.json();
            const latest = payload.items?.[0];
            if (latest) {
                $("#trace-detail").textContent += `\n状态：${latest.status}`;
            }
        } catch (_) {
            // The current turn metadata already provides a useful trace.
        }
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
            ? "—"
            : `${Math.round(abilityView.average_accuracy * 100)}%`;
        $("#metric-attempts").textContent = `${ability.attempt_count || 0} 次有效作答`;
        $("#diagnosis-confidence").textContent = `诊断置信度 ${Math.round((evidenceView.diagnosis_confidence || 0) * 100)}%`;
        renderTags("#mastered-list", evidenceView.mastered_knowledge_points, "暂无已掌握知识点");
        renderTags("#blind-list", evidenceView.knowledge_blind_spots, "暂无已确认知识盲区");
        renderRecords("#micro-evidence-list", evidenceView.micro_evidence?.items, "暂无已确认微表征证据", (item) => ({
            title: `${eventLabel(item.event_type)} · ${Math.round(item.confidence * 100)}%`,
            detail: item.transcript || "未提供短转写",
        }));
        renderRecords("#memory-list", evidenceView.memory_summary, "暂无长期记忆摘要", (item) => ({
            title: memoryLabel(item.memory_type || item.type),
            detail: item.content || item.summary || "已检索到相关记忆",
        }));
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
                    borderColor: "#1565c0",
                    backgroundColor: "rgba(21,101,192,.1)",
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
                    {label: "预计答对概率", data: items.map((item) => item.predicted_probability), backgroundColor: "#1565c0"},
                    {label: "实际结果", data: items.map((item) => item.actual_result ? 1 : 0), backgroundColor: "#23835c"},
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
            activateAgentSteps(["diagnosis", "retrieval", "generation", "verification", "decision"]);
            const verified = (payload.items || []).filter((item) => item.verification_passed).length;
            toast(
                payload.degradation?.length || verified < 3
                    ? `已生成 ${payload.items?.length || 0} 项资源，其中 ${verified} 项通过校验`
                    : "个性化资源已生成并完成校验"
            );
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
        const statusLabel = {verified: "已校验", draft: "草稿"}[item.status] || item.status;
        return `<article class="resource-card">
            <header><span class="eyebrow">${escapeHtml(typeLabel)}</span><span class="resource-status ${item.status}">${escapeHtml(statusLabel)}</span></header>
            <h2>${escapeHtml(item.title)}</h2>
            <p class="resource-content">${escapeHtml(item.content)}</p>
            <p><strong>个性化理由：</strong>${escapeHtml(item.personalization_reason)}</p>
            <footer>难度：${escapeHtml(difficultyLabel(item.difficulty))} · 证据来源：${item.evidence_sources?.length || 0}</footer>
        </article>`;
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

    function activateAgentSteps(steps) {
        $$(".agent-loop li").forEach((item) => item.classList.toggle("active", steps.includes(item.dataset.agentStep)));
    }

    async function startOrStopRecording() {
        const button = $("#record-button");
        if (state.mediaRecorder?.state === "recording") {
            state.mediaRecorder.stop();
            button.querySelector("span").textContent = "开始录音";
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
                $("#learner-job-status").textContent = "录音已停止，可提交本轮音频。";
            };
            state.mediaRecorder.start();
            button.querySelector("span").textContent = "停止录音";
            $("#learner-job-status").textContent = "正在录音，仅在停止后提交。";
        } catch (error) {
            toast(`无法开始录音：${error.message}`);
        }
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
        data.append("audio", blob, selected?.name || "learner-turn.webm");
        try {
            const response = await api("/v1/micro/detection-jobs", {method: "POST", body: data});
            const payload = await response.json();
            $("#learner-job-status").textContent = `任务 ${payload.job_id} 已提交，状态：${payload.status}`;
        } catch (error) {
            $("#learner-job-status").textContent = error.message;
        }
    }

    async function uploadMentorAudio() {
        if (!$("#mentor-consent").checked) return toast("请先确认录音分析授权");
        const files = Array.from($("#mentor-audio-files").files);
        if (!files.length) return toast("请选择至少一个录音文件");
        const data = new FormData();
        data.append("module_id", String(state.moduleId));
        data.append("consent_granted", "true");
        data.append("speaker_mapping_confirmed", String($("#speaker-confirmed").checked));
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
        iconRefresh();
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
        $("#module-select").addEventListener("change", changeModule);
        $$(".nav-item").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
        $("#chat-form").addEventListener("submit", (event) => {
            event.preventDefault();
            sendMessage($("#chat-input").value);
        });
        $("#quick-quiz").addEventListener("click", () => {
            const purpose = $("#quiz-purpose-select").value;
            const prompt = {
                pretest: "开始当前模块前测",
                stage_test: "请给我一道当前模块的阶段测验",
                posttest: "开始当前模块后测",
            }[purpose];
            sendMessage(prompt);
        });
        $$(".segmented button").forEach((button) => button.addEventListener("click", () => {
            $$(".segmented button").forEach((item) => item.classList.toggle("active", item === button));
            $$(".insight-pane").forEach((pane) => pane.classList.toggle("active", pane.id === `insight-${button.dataset.insightTab}`));
        }));
        $("#refresh-insight").addEventListener("click", loadInsight);
        $("#generate-resources").addEventListener("click", generateResources);
        $("#refresh-members").addEventListener("click", loadMembers);
        $("#record-button").addEventListener("click", startOrStopRecording);
        $("#upload-learner-audio").addEventListener("click", uploadLearnerAudio);
        $("#upload-mentor-audio").addEventListener("click", uploadMentorAudio);
        $("#upload-knowledge").addEventListener("click", uploadKnowledge);
        $("#material-module-select").addEventListener("change", loadKnowledgeDocuments);
        $("#quiz-module-select").addEventListener("change", () => {
            setImportStep(1);
            loadQuizKnowledgePoints();
        });
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
