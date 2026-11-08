<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Портал Сингулярности</title>
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        :root { --bg:#0b0f19; --surface:rgba(30,41,59,0.7); --text:#e2e8f0; --text-soft:#94a3b8; --accent:#10b981; --border:rgba(255,255,255,0.1); --danger:#ef4444; }
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: 'Inter', system-ui, sans-serif; background: var(--bg); color: var(--text); line-height:1.5; background-image: radial-gradient(circle at 15% 50%, rgba(16,185,129,0.08), transparent 25%), radial-gradient(circle at 85% 30%, rgba(139,92,246,0.08), transparent 25%); background-attachment: fixed; }
        .container { max-width:1000px; margin:0 auto; padding:20px; }
        .nav { display:flex; justify-content:space-between; align-items:center; padding:16px 0; border-bottom:1px solid var(--border); margin-bottom:24px; flex-wrap:wrap; gap:8px;}
        .btn { padding:8px 16px; border-radius:12px; border:1px solid var(--border); cursor:pointer; font-weight:600; font-size:0.85rem; color:var(--text); background: rgba(255,255,255,0.05); transition: all 0.2s; display:inline-flex; align-items:center; gap:6px; text-decoration: none; }
        .btn:hover { background: rgba(255,255,255,0.1); }
        .btn-primary { background: linear-gradient(135deg, #10b981, #059669); border:none; color:white;}
        .btn-accent { background: linear-gradient(135deg, #f59e0b, #d97706); border:none; color:white;}
        .card { background:var(--surface); backdrop-filter:blur(16px); border-radius:16px; padding:20px; margin-bottom:16px; border:1px solid var(--border); }
        .input, .textarea, .select { width:100%; padding:10px 14px; border:1px solid var(--border); border-radius:12px; margin:6px 0; background:rgba(0,0,0,0.2); color:var(--text); font-family:inherit; }
        .flex { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
        .flex-space { justify-content:space-between; }
        .section-title { font-weight:700; margin:20px 0 10px; font-size:1.1rem; display:flex; align-items:center; gap:8px;}
        .avatar { width:32px; height:32px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:bold; color:#fff; font-size:0.9rem; }
        .modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.7); backdrop-filter:blur(4px); display:flex; align-items:center; justify-content:center; z-index:100; }
        .modal { background:#1e293b; border:1px solid var(--border); padding:24px; border-radius:16px; width:90%; max-width:520px; max-height:90vh; overflow-y:auto; }
        .skeleton-card { height:100px; background:linear-gradient(90deg, rgba(30,41,59,0.7) 25%, rgba(51,65,85,0.7) 50%, rgba(30,41,59,0.7) 75%); background-size:200% 100%; animation:shimmer 1.5s infinite; border-radius:16px; margin-bottom:16px; }
        @keyframes shimmer { 0% { background-position:200% 0; } 100% { background-position:-200% 0; } }
        #toast-container { position:fixed; bottom:20px; right:20px; z-index:9999; display:flex; flex-direction:column; gap:10px; }
        .toast { background:rgba(30,41,59,0.95); padding:12px 20px; border-radius:12px; border-left:4px solid var(--accent); display:flex; align-items:center; gap:10px; }
        .board { display:flex; gap:16px; overflow-x:auto; padding-bottom:20px; align-items:flex-start; }
        .board-col { background:rgba(15,23,42,0.5); border-radius:12px; min-width:280px; width:280px; padding:12px; flex-shrink:0; min-height:200px; border:1px solid var(--border); }
        .board-col h4 { margin-bottom:12px; font-size:0.95rem; display:flex; justify-content:space-between; color:var(--text-soft); }
        .board-card { background:rgba(30,41,59,0.9); padding:14px; border-radius:10px; margin-bottom:10px; cursor:grab; border:1px solid var(--border); }
        .board-card.dragging { opacity:0.4; }
        .board-col.drag-over { background:rgba(16,185,129,0.1); outline:2px dashed var(--accent); }
        .comm-tab { padding:8px 16px; border-radius:20px; border:1px solid var(--border); background:rgba(255,255,255,0.05); color:var(--text-soft); cursor:pointer; font-size:0.85rem; white-space:nowrap; }
        .comm-tab.active { background:var(--accent); color:white; border-color:var(--accent); }
        .trash-item { padding:12px; border:1px solid var(--border); border-radius:12px; margin-bottom:8px; background:rgba(239,68,68,0.05); }
    </style>
</head>
<body>
<div class="container" id="app">Загрузка...</div>
<div id="toast-container"></div>

<script>
(function() {
    const SUPABASE_URL = 'https://irtixigmkwbzkitzhjvf.supabase.co';
    const SUPABASE_ANON_KEY = 'sb_publishable_kTNliJzwfjPMacV1JBeLdw_C0wzbLg8';
    const supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

    let currentUserId = localStorage.getItem('portal_user_id') || null;
    let currentView = 'all';
    let selectedBoardCommId = null;
    let modal = null;
    let selectedCommunityId = null;
    let distributionTaskId = null;
    let route = { name: 'home' };

    function initIcons() { setTimeout(() => { if(window.lucide) lucide.createIcons(); }, 50); }
    function showToast(msg, type = 'success') {
        const c = document.getElementById('toast-container');
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.innerHTML = `<i data-lucide="${type === 'error' ? 'alert-circle' : 'check-circle'}"></i> <span>${msg}</span>`;
        c.appendChild(el); initIcons();
        setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
    }
    function getAvatar(name) {
        if (!name) name = '?';
        const colors = ['#ef4444','#f97316','#f59e0b','#10b981','#06b6d4','#3b82f6','#6366f1','#8b5cf6','#d946ef','#ec4899'];
        let hash = 0; for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
        return `<div class="avatar" style="background:${colors[Math.abs(hash) % colors.length]}">${name.charAt(0).toUpperCase()}</div>`;
    }
    function statusLabel(s) { return {open:'Открыта', in_progress:'В работе', review:'На проверке', completed:'Завершена', cancelled:'Отменена'}[s] || s; }
    
    function parseHash() {
        const h = location.hash.replace(/^#/, '');
        if (h === '/feedback') return { name: 'feedback' };
        const m = h.match(/^\/task\/(.+)$/);
        return m ? { name:'task', taskId:m[1] } : { name:'home' };
    }

    let realtimeTimeout;
    supabase.channel('schema-db-changes')
        .on('postgres_changes', { event: '*', schema: 'public' }, () => {
            clearTimeout(realtimeTimeout);
            realtimeTimeout = setTimeout(() => { if (!modal) render(); }, 500);
        }).subscribe();

    async function render() {
        route = parseHash();
        if (!currentUserId) return renderLogin();
        try {
            const { data: user, error } = await supabase.from('users').select('*').eq('id', currentUserId).maybeSingle();
            if (error || !user) { currentUserId = null; localStorage.removeItem('portal_user_id'); return renderLogin(); }
            if (route.name === 'task') return renderTaskCard(user, route.taskId);
            if (route.name === 'feedback') return renderFeedbackPage(user);
            await renderMainApp(user);
        } catch (e) {
            document.getElementById('app').innerHTML = `<div class="card" style="border-color:var(--danger);"><p style="color:var(--danger)">Ошибка: ${e.message}</p></div>`;
        }
    }

    async function renderLogin() {
        const tg = window.Telegram?.WebApp;
        if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
            const tgu = tg.initDataUnsafe.user;
            const tgId = tgu.id;
            const name = [tgu.first_name, tgu.last_name].filter(Boolean).join(' ') || tgu.username || ('tg_' + tgId);
            const { data: existing } = await supabase.from('users').select('*').eq('telegram_id', tgId).maybeSingle();
            if (existing) { currentUserId = existing.id; localStorage.setItem('portal_user_id', currentUserId); return render(); }
            const newId = crypto.randomUUID();
            const { error } = await supabase.from('users').insert({ id: newId, name, telegram_id: tgId });
            if (error) { document.getElementById('app').innerHTML = `<p style="color:red;">Ошибка: ${error.message}</p>`; return; }
            currentUserId = newId; localStorage.setItem('portal_user_id', currentUserId); return render();
        }
        const { data: users } = await supabase.from('users').select('*');
        let opts = (users || []).map(u => `<option value="${u.id}">${u.name}</option>`).join('');
        document.getElementById('app').innerHTML = `
            <div style="max-width:400px;margin:60px auto;"><div class="card">
                <h2 style="margin-bottom:16px; display:flex; align-items:center; gap:8px;"><i data-lucide="globe"></i> Портал Сингулярности</h2>
                <select class="select" id="userSelect"><option value="">+ Новый участник</option>${opts}</select>
                <div id="newUserBlock"><input class="input" id="newName" placeholder="Ваше имя"></div>
                <button class="btn btn-primary" style="width:100%; justify-content:center;" id="enterBtn">Войти</button>
            </div></div>`;
        initIcons();
        document.getElementById('userSelect').onchange = function() { document.getElementById('newUserBlock').style.display = this.value ? 'none' : 'block'; };
        document.getElementById('enterBtn').onclick = async () => {
            let userId = document.getElementById('userSelect').value;
            if (!userId) {
                const name = document.getElementById('newName').value.trim();
                if (!name) return showToast('Введите имя', 'error');
                const newId = crypto.randomUUID();
                await supabase.from('users').insert({ id: newId, name, telegram_id: Math.floor(Math.random()*1e9) });
                userId = newId;
            }
            currentUserId = userId; localStorage.setItem('portal_user_id', currentUserId); render();
        };
    }

    async function renderMainApp(user) {
        document.getElementById('app').innerHTML = `<div class="nav"><h2>Загрузка...</h2></div><div class="skeleton-card"></div><div class="skeleton-card"></div>`;
        const { data: memberships } = await supabase.from('memberships').select('*').eq('user_id', currentUserId).is('deleted_at', null);
        const myCommunityIds = (memberships||[]).map(m => m.community_id);
        const leaderMemberships = (memberships||[]).filter(m => m.role.startsWith('leader'));
        const leaderCommunityIds = leaderMemberships.map(m => m.community_id);
        const isAdmin = !!user.is_admin;

        // ⬇️ ФИЛЬТР deleted_at IS NULL
        let query = supabase.from('tasks')
            .select('*, communities(name, is_closed, board_columns), checklist_items(*), task_assignees(*, users(name))')
            .is('deleted_at', null)
            .order('created_at', { ascending: false });
        const { data: rawTasks, error } = await query;
        if (error) throw error;

        let tasks = rawTasks.filter(t => { if (t.communities?.is_closed) return myCommunityIds.includes(t.community_id); return true; });
        if (currentView === 'my_communities' && myCommunityIds.length) tasks = tasks.filter(t => myCommunityIds.includes(t.community_id));
        else if (currentView === 'participating') tasks = tasks.filter(t => (t.task_assignees || []).some(a => a.user_id === currentUserId));

        // ⬇️ ФИЛЬТР deleted_at IS NULL
        const { data: allCommunities } = await supabase.from('communities').select('*').is('deleted_at', null);

        let html = `<div class="nav">
            <h2 style="display:flex; align-items:center; gap:8px; font-size:1.2rem;"><i data-lucide="globe" style="color:var(--accent)"></i> Портал Сингулярности</h2>
            <div class="flex">
                <div class="flex" style="gap:6px; cursor:pointer;" onclick="location.hash='#/feedback'">${getAvatar(user.name)} <span style="font-weight:600">${user.name}</span></div>
                <button class="btn btn-sm" id="feedbackBtn"><i data-lucide="message-square"></i> Отзывы</button>
                <button class="btn btn-sm" id="profileBtn"><i data-lucide="user"></i> Профиль</button>
                ${isAdmin ? `<button class="btn btn-sm" id="trashBtn" style="background:rgba(239,68,68,0.15); color:#fca5a5;"><i data-lucide="trash-2"></i> Корзина</button>` : ''}
                <button class="btn btn-sm" id="logoutBtn" style="background:rgba(239,68,68,0.2); color:#fca5a5;"><i data-lucide="log-out"></i></button>
            </div>
        </div>
        <div class="flex" style="margin-bottom:24px;">
            <button class="btn ${currentView==='all'?'btn-primary':''}" id="viewAllBtn"><i data-lucide="layers"></i> Все задачи</button>
            ${myCommunityIds.length ? `<button class="btn ${currentView==='my_communities'?'btn-primary':''}" id="viewMyBtn"><i data-lucide="users"></i> Мои сообщества</button>` : ''}
            <button class="btn ${currentView==='participating'?'btn-primary':''}" id="viewParticipatingBtn"><i data-lucide="user-check"></i> Я участвую</button>
            <button class="btn ${currentView==='board'?'btn-primary':''}" id="viewBoardBtn"><i data-lucide="kanban-square"></i> Доска</button>
            ${leaderCommunityIds.length || isAdmin ? `<button class="btn btn-accent" id="createTaskBtn"><i data-lucide="plus"></i> Новая задача</button>` : ''}
            <button class="btn" id="createCommunityBtn"><i data-lucide="plus-circle"></i> Сообщество</button>
        </div>`;

        if (currentView === 'board') {
            html += renderKanbanBoard(tasks, myCommunityIds, allCommunities);
        } else {
            html += '<div class="section-title"><i data-lucide="users"></i> Сообщества</div>';
            if (allCommunities && allCommunities.length) {
                html += '<div class="card" style="padding:12px;">';
                allCommunities.forEach(c => {
                    const isMember = myCommunityIds.includes(c.id);
                    const role = memberships?.find(m => m.community_id === c.id)?.role;
                    html += `<div class="flex flex-space" style="padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                        <span style="display:flex; align-items:center; gap:6px;"><i data-lucide="${c.is_closed ? 'lock' : 'unlock'}" style="width:16px; color:var(--text-soft)"></i> ${c.name} ${role ? `<span class="badge" style="background:rgba(255,255,255,0.1); font-size:0.6rem;">${role}</span>` : ''}</span>
                        ${!isMember ? `<button class="btn btn-sm join-comm" data-commid="${c.id}" data-closed="${c.is_closed}">${c.is_closed ? 'Подать заявку' : 'Вступить'}</button>` : `<span style="color:var(--accent); font-size:0.8rem; display:flex; align-items:center; gap:4px;"><i data-lucide="check" style="width:14px;"></i> Участник</span>`}
                    </div>`;
                });
                html += '</div>';
            } else html += '<p>Пока нет сообществ.</p>';

            if (leaderMemberships.length || isAdmin) {
                html += '<div class="section-title"><i data-lucide="shield"></i> Управление сообществами</div>';
                (isAdmin ? allCommunities : allCommunities.filter(c => leaderCommunityIds.includes(c.id))).forEach(c => {
                    html += `<div class="card flex flex-space" style="padding:12px;"><strong>${c.name}</strong><button class="btn btn-sm btn-primary manage-comm" data-commid="${c.id}">Настроить</button></div>`;
                });
            }

            html += '<div class="section-title"><i data-lucide="list-todo"></i> Задачи</div><div id="tasksList">';
            if (!tasks.length) html += '<p style="color:var(--text-soft)">Здесь пока пусто.</p>';
            else tasks.forEach(task => {
                const assignees = task.task_assignees || [];
                const assigneeNames = assignees.map(a => a.users?.name).join(', ');
                const isLeader = isAdmin || leaderCommunityIds.includes(task.community_id);
                const isCreator = (task.creator_id === currentUserId);
                const isAssignee = assignees.some(a => a.user_id === currentUserId);
                const canTake = task.status === 'open' && !isAssignee;
                const canJoin = task.status === 'in_progress' && !isAssignee;
                const canSubmit = task.status === 'in_progress' && isAssignee;
                const canReview = task.status === 'review' && (isLeader || isCreator);
                const canDelete = isLeader || isCreator;

                html += `<div class="card">
                    <div class="flex flex-space" style="margin-bottom:8px;"><a class="task-link" href="#/task/${task.id}" style="font-weight:700; font-size:1.05rem; color:var(--text); text-decoration:none;">${task.title}</a><span class="badge status-${task.status}">${statusLabel(task.status)}</span></div>
                    ${task.description ? `<p style="color:var(--text-soft); font-size:0.9rem; margin-bottom:12px;">${task.description}</p>` : ''}
                    <div class="flex" style="font-size:0.8rem; color:var(--text-soft); margin-bottom:12px;">
                        <span style="display:flex; align-items:center; gap:4px;"><i data-lucide="folder"></i> ${task.communities?.name}</span>
                        <span style="display:flex; align-items:center; gap:4px;"><i data-lucide="star"></i> ${task.points} баллов</span>
                        ${assigneeNames ? `<span style="display:flex; align-items:center; gap:4px;"><i data-lucide="users"></i> ${assigneeNames}</span>` : ''}
                    </div>
                    <div class="flex">
                        <a class="btn btn-sm" href="#/task/${task.id}"><i data-lucide="external-link"></i> Открыть</a>
                        ${canTake ? `<button class="btn btn-primary btn-sm take-task" data-taskid="${task.id}"><i data-lucide="hand"></i> Взять</button>` : ''}
                        ${canJoin ? `<button class="btn btn-primary btn-sm take-task" data-taskid="${task.id}"><i data-lucide="user-plus"></i> Присоединиться</button>` : ''}
                        ${canSubmit ? `<button class="btn btn-sm send-review" data-taskid="${task.id}"><i data-lucide="send"></i> На проверку</button>` : ''}
                        ${canReview ? `<button class="btn btn-accent btn-sm accept-task" data-taskid="${task.id}"><i data-lucide="check-circle"></i> Принять</button>` : ''}
                        ${canDelete ? `<button class="btn btn-sm delete-task" data-taskid="${task.id}" style="background:rgba(239,68,68,0.15); color:#fca5a5;"><i data-lucide="trash-2"></i></button>` : ''}
                    </div>
                </div>`;
            });
            html += '</div>';
        }

        if (modal === 'createCommunity') html += createCommunityModal();
        if (modal === 'profile') html += await profileModal(user);
        if (modal === 'createTask') html += await createTaskModal(leaderCommunityIds, user);
        if (modal === 'manageCommunity') html += await manageCommunityModal();
        if (modal === 'distribute') html += await distributeModal();
        if (modal === 'editBoardCols') html += await editBoardColsModal();
        if (modal === 'trash') html += await trashModal();

        document.getElementById('app').innerHTML = html;
        initIcons();
        attachEvents();
    }

    // ══════════ КОРЗИНА (только для суперадмина) ══════════
    async function trashModal() {
        const { data: deletedTasks } = await supabase.from('tasks').select('*').not('deleted_at', 'is', null).order('deleted_at', { ascending: false });
        const { data: deletedComms } = await supabase.from('communities').select('*').not('deleted_at', 'is', null).order('deleted_at', { ascending: false });

        let html = `<div class="modal-overlay" id="modal"><div class="modal" style="max-width:600px;">
            <h3 style="margin-bottom:16px;">🗑 Корзина</h3>
            <h4 style="margin-bottom:8px; font-size:0.95rem; color:var(--text-soft);">Удалённые задачи (${deletedTasks?.length || 0})</h4>
            ${(!deletedTasks || !deletedTasks.length) ? '<p style="color:var(--text-soft); font-size:0.85rem;">Пусто</p>' :
                deletedTasks.map(t => `
                    <div class="trash-item">
                        <div class="flex flex-space">
                            <strong>${t.title}</strong>
                            <button class="btn btn-sm restore-task" data-taskid="${t.id}" style="background:rgba(16,185,129,0.2); color:#6ee7b7;">↩ Восстановить</button>
                        </div>
                        <div style="font-size:0.75rem; color:var(--text-soft); margin-top:4px;">
                            Удалено: ${new Date(t.deleted_at).toLocaleString()}
                        </div>
                    </div>
                `).join('')
            }
            <h4 style="margin:16px 0 8px; font-size:0.95rem; color:var(--text-soft);">Удалённые сообщества (${deletedComms?.length || 0})</h4>
            ${(!deletedComms || !deletedComms.length) ? '<p style="color:var(--text-soft); font-size:0.85rem;">Пусто</p>' :
                deletedComms.map(c => `
                    <div class="trash-item">
                        <div class="flex flex-space">
                            <strong>${c.name}</strong>
                            <button class="btn btn-sm restore-comm" data-commid="${c.id}" style="background:rgba(16,185,129,0.2); color:#6ee7b7;">↩ Восстановить</button>
                        </div>
                        <div style="font-size:0.75rem; color:var(--text-soft); margin-top:4px;">
                            Удалено: ${new Date(c.deleted_at).toLocaleString()}
                        </div>
                    </div>
                `).join('')
            }
            <button class="btn" id="cancelModal" style="width:100%; justify-content:center; margin-top:16px;">Закрыть</button>
        </div></div>`;
        return html;
    }

    // ══════════ ОСТАЛЬНЫЕ ФУНКЦИИ (сокращённо — как были) ══════════
    // (Вставь сюда всё из предыдущего кода: renderKanbanBoard, renderTaskCard, 
    // createCommunityModal, profileModal, createTaskModal, manageCommunityModal, 
    // distributeModal, editBoardColsModal, attachEvents и т.д.)

    // Для экономии места я не дублирую их здесь, но в реальном файле они должны быть.

    // ... [ВСТАВЬ СЮДА ВСЕ ФУНКЦИИ ИЗ ПРЕДЫДУЩЕГО КОДА] ...

})();
</script>
</body>
</html>
