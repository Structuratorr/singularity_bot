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

        const { data: rawTasks, error } = await supabase.from('tasks')
            .select('*, communities(name, is_closed, board_columns), checklist_items(*), task_assignees(*, users(name))')
            .is('deleted_at', null)
            .order('created_at', { ascending: false });
        if (error) throw error;

        let tasks = rawTasks.filter(t => { if (t.communities?.is_closed) return myCommunityIds.includes(t.community_id); return true; });
        if (currentView === 'my_communities' && myCommunityIds.length) tasks = tasks.filter(t => myCommunityIds.includes(t.community_id));
        else if (currentView === 'participating') tasks = tasks.filter(t => (t.task_assignees || []).some(a => a.user_id === currentUserId));

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

    // ═══════════ КОРЗИНА ═══════════
    async function trashModal() {
        const { data: deletedTasks } = await supabase.from('tasks').select('*').not('deleted_at', 'is', null).order('deleted_at', { ascending: false });
        const { data: deletedComms } = await supabase.from('communities').select('*').not('deleted_at', 'is', null).order('deleted_at', { ascending: false });

        return `<div class="modal-overlay" id="modal"><div class="modal" style="max-width:600px;">
            <h3 style="margin-bottom:16px;">🗑 Корзина</h3>
            <h4 style="margin-bottom:8px; font-size:0.95rem; color:var(--text-soft);">Удалённые задачи (${deletedTasks?.length || 0})</h4>
            ${(!deletedTasks || !deletedTasks.length) ? '<p style="color:var(--text-soft); font-size:0.85rem;">Пусто</p>' :
                deletedTasks.map(t => `
                    <div class="trash-item">
                        <div class="flex flex-space">
                            <strong>${t.title}</strong>
                            <button class="btn btn-sm restore-task" data-taskid="${t.id}" style="background:rgba(16,185,129,0.2); color:#6ee7b7;">↩ Восстановить</button>
                        </div>
                        <div style="font-size:0.75rem; color:var(--text-soft); margin-top:4px;">Удалено: ${new Date(t.deleted_at).toLocaleString()}</div>
                    </div>
                `).join('')}
            <h4 style="margin:16px 0 8px; font-size:0.95rem; color:var(--text-soft);">Удалённые сообщества (${deletedComms?.length || 0})</h4>
            ${(!deletedComms || !deletedComms.length) ? '<p style="color:var(--text-soft); font-size:0.85rem;">Пусто</p>' :
                deletedComms.map(c => `
                    <div class="trash-item">
                        <div class="flex flex-space">
                            <strong>${c.name}</strong>
                            <button class="btn btn-sm restore-comm" data-commid="${c.id}" style="background:rgba(16,185,129,0.2); color:#6ee7b7;">↩ Восстановить</button>
                        </div>
                        <div style="font-size:0.75rem; color:var(--text-soft); margin-top:4px;">Удалено: ${new Date(c.deleted_at).toLocaleString()}</div>
                    </div>
                `).join('')}
            <button class="btn" id="cancelModal" style="width:100%; justify-content:center; margin-top:16px;">Закрыть</button>
        </div></div>`;
    }

    // ═══════════ МЯГКОЕ УДАЛЕНИЕ ═══════════
    async function softDeleteTask(taskId) {
        if (!confirm('Переместить задачу в корзину? Её можно будет восстановить.')) return;
        const { error } = await supabase.from('tasks').update({ deleted_at: new Date().toISOString() }).eq('id', taskId);
        if (error) return showToast('Ошибка: ' + error.message, 'error');
        showToast('Задача в корзине');
        render();
    }

    // ═══════════ KANBAN ═══════════
    function renderKanbanBoard(allTasks, myCommunityIds, allCommunities) {
        if (!myCommunityIds || !myCommunityIds.length) return '<p style="color:var(--text-soft); margin-top:20px;">Вы пока не состоите ни в одном сообществе.</p>';
        if (!selectedBoardCommId || !myCommunityIds.includes(selectedBoardCommId)) selectedBoardCommId = myCommunityIds[0];
        const activeComm = allCommunities.find(c => c.id === selectedBoardCommId);
        if (!activeComm) return '<p>Ошибка загрузки сообщества</p>';
        const commTasks = allTasks.filter(t => t.community_id === selectedBoardCommId);
        let columns = ['open', 'in_progress', 'review', 'completed'];
        if (activeComm.board_columns && Array.isArray(activeComm.board_columns) && activeComm.board_columns.length) columns = activeComm.board_columns;
        let tabsHtml = '<div class="flex" style="margin-bottom:16px; overflow-x:auto; padding-bottom:4px;">';
        myCommunityIds.forEach(cid => {
            const c = allCommunities.find(x => x.id === cid);
            if (c) tabsHtml += `<button class="comm-tab ${c.id === selectedBoardCommId ? 'active' : ''} comm-board-tab" data-commid="${c.id}">${c.name}</button>`;
        });
        tabsHtml += '</div>';
        let boardHtml = `<div class="board">`;
        columns.forEach(col => {
            const colTasks = commTasks.filter(t => {
                let taskCol = t.board_column;
                if (!taskCol || !columns.includes(taskCol)) taskCol = t.status;
                if (!taskCol || !columns.includes(taskCol)) taskCol = columns[0];
                return taskCol === col;
            });
            boardHtml += `<div class="board-col" data-col="${col}" ondragover="window.dragOver(event,this)" ondragleave="window.dragLeave(event,this)" ondrop="window.handleDrop(event,'${col}')">
                <h4>${statusLabel(col)} <span>${colTasks.length}</span></h4>`;
            colTasks.forEach(t => {
                boardHtml += `<div class="board-card" data-taskid="${t.id}" draggable="true" ondragstart="window.dragStart(event,'${t.id}')" ondragend="window.dragEnd(event)">
                    <div style="font-weight:700; margin-bottom:4px;">${t.title}</div>
                    <div style="margin-top:8px;"><a href="#/task/${t.id}" style="color:var(--accent); font-size:0.8rem; text-decoration:none;">Открыть</a></div>
                </div>`;
            });
            boardHtml += `</div>`;
        });
        boardHtml += `</div>`;
        return `${tabsHtml}<div class="flex" style="justify-content:space-between; margin-bottom:12px;"><h3>Доска: ${activeComm.name}</h3><button class="btn btn-sm" id="editBoardColsBtn" data-commid="${activeComm.id}"><i data-lucide="settings"></i> Столбцы</button></div>${boardHtml}`;
    }

    window.dragOver = (e, el) => { e.preventDefault(); el.classList.add('drag-over'); };
    window.dragLeave = (e, el) => { if (!el.contains(e.relatedTarget)) el.classList.remove('drag-over'); };
    window.dragStart = (e, id) => { e.dataTransfer.setData('text/plain', id); setTimeout(() => e.target.classList.add('dragging'), 0); };
    window.dragEnd = (e) => { e.target.classList.remove('dragging'); document.querySelectorAll('.board-col').forEach(el => el.classList.remove('drag-over')); };
    window.handleDrop = async (e, newCol) => {
        e.preventDefault();
        document.querySelectorAll('.board-col').forEach(el => el.classList.remove('drag-over'));
        const taskId = e.dataTransfer.getData('text/plain');
        if (!taskId) return;
        await supabase.from('tasks').update({ board_column: newCol }).eq('id', taskId);
        if (['open','in_progress','review','completed'].includes(newCol)) await supabase.from('tasks').update({ status: newCol }).eq('id', taskId);
        render();
    };

    // ═══════════ КАРТОЧКА ЗАДАЧИ ═══════════
    async function renderTaskCard(user, taskId) {
        document.getElementById('app').innerHTML = `<div class="nav"><h2>Загрузка...</h2></div><div class="skeleton-card"></div>`;
        const { data: task, error } = await supabase.from('tasks')
            .select('*, communities(name, board_columns), checklist_items(*), task_assignees(*, users(name))')
            .eq('id', taskId).maybeSingle();
        if (error || !task) { document.getElementById('app').innerHTML = `<div class="container"><p>Задача не найдена.</p><button class="btn" onclick="location.hash=''">← Назад</button></div>`; return; }

        const { data: memberships } = await supabase.from('memberships').select('*').eq('user_id', currentUserId).is('deleted_at', null);
        const leaderCommunityIds = (memberships||[]).filter(m => m.role.startsWith('leader')).map(m => m.community_id);
        const isAdmin = !!user.is_admin;
        const isLeader = isAdmin || leaderCommunityIds.includes(task.community_id);
        const isCreator = (task.creator_id === currentUserId);
        const canEdit = isLeader || isCreator;
        const assignees = task.task_assignees || [];
        const isAssignee = assignees.some(a => a.user_id === currentUserId);
        const canTake = task.status === 'open' && !isAssignee;
        const canJoin = task.status === 'in_progress' && !isAssignee;
        const canSubmit = task.status === 'in_progress' && isAssignee;
        const canReview = task.status === 'review' && canEdit;

        const commCols = task.communities?.board_columns || ['open','in_progress','review','completed'];
        let currentCol = task.board_column;
        if (!currentCol || !commCols.includes(currentCol)) currentCol = task.status;
        if (!currentCol || !commCols.includes(currentCol)) currentCol = commCols[0];

        const { data: comments } = await supabase.from('task_comments').select('*').eq('task_id', taskId).is('deleted_at', null).order('created_at', { ascending: true });
        let commentsWithNames = [];
        if (comments && comments.length) {
            const userIds = [...new Set(comments.map(c => c.user_id).filter(Boolean))];
            const { data: users } = await supabase.from('users').select('id, name').in('id', userIds);
            const map = Object.fromEntries((users||[]).map(u => [u.id, u.name]));
            commentsWithNames = comments.map(c => ({...c, name: map[c.user_id] || 'Аноним'}));
        }
        let dlStr = task.deadline ? new Date(task.deadline).toISOString().slice(0,16) : '';

        let html = `<div class="nav"><div><a class="btn" href="#/"><i data-lucide="arrow-left"></i> Назад</a></div><div class="flex">${getAvatar(user.name)}</div></div>
        <div class="card">
            <div class="flex flex-space">
                ${canEdit ? `<input class="input" id="cardTitle" value="${(task.title||'').replace(/"/g,'&quot;')}" style="font-size:1.2rem; font-weight:700; flex:1; margin:0; margin-right:10px; background:rgba(0,0,0,0.3);">` : `<h2>${task.title}</h2>`}
                <span class="badge status-${task.status}">${statusLabel(task.status)}</span>
            </div>
            ${canEdit ? `<textarea class="textarea" id="cardDesc" style="margin-top:12px; min-height:100px;">${task.description||''}</textarea>` : `<p style="margin:12px 0; white-space:pre-wrap; color:var(--text-soft);">${task.description || 'Без описания'}</p>`}
            <div class="flex" style="font-size:0.9rem; color:var(--text-soft); align-items:center; margin-top:12px; background:rgba(0,0,0,0.2); padding:12px; border-radius:12px; border:1px solid var(--border);">
                <span style="display:flex; align-items:center; gap:4px;"><i data-lucide="folder"></i> ${task.communities?.name}</span>
                <span style="display:flex; align-items:center; gap:4px;"><i data-lucide="star"></i> ${canEdit ? `<input type="number" id="cardPoints" value="${task.points||0}" style="width:60px; padding:4px 8px; margin:0; font-size:0.9rem;" class="input">` : task.points} баллов</span>
                <span style="display:flex; align-items:center; gap:4px;"><i data-lucide="calendar"></i> ${canEdit ? `<input type="datetime-local" id="cardDeadline" value="${dlStr}" style="padding:4px 8px; margin:0; font-size:0.9rem;" class="input">` : (task.deadline ? new Date(task.deadline).toLocaleString() : '—')}</span>
            </div>
            <div class="flex" style="margin:12px 0; background:rgba(0,0,0,0.2); padding:12px; border-radius:12px; border:1px solid var(--border);">
                <span style="font-weight:600; font-size:0.9rem; display:flex; align-items:center; gap:4px;"><i data-lucide="columns"></i> Столбец:</span>
                <select class="select" style="width:auto; margin:0; padding:6px 12px; font-weight:600;" onchange="window.changeTaskColFromCard('${task.id}', this.value)">
                    ${commCols.map(c => `<option value="${c}" ${c === currentCol ? 'selected' : ''}>${statusLabel(c)}</option>`).join('')}
                </select>
            </div>
            ${assignees.length ? `<div style="margin:12px 0; font-size:0.9rem;">👥 Исполнители: <b>${assignees.map(a=>a.users?.name).join(', ')}</b></div>` : ''}
            <div class="flex" style="margin-top:16px;">
                ${canEdit ? `<button class="btn btn-primary btn-sm" id="saveTaskCard" data-taskid="${task.id}"><i data-lucide="save"></i> Сохранить</button>` : ''}
                ${canEdit ? `<button class="btn btn-danger btn-sm" id="deleteTaskCard" data-taskid="${task.id}" style="background:rgba(239,68,68,0.2); color:#fca5a5;"><i data-lucide="trash-2"></i> Удалить</button>` : ''}
                ${canTake ? `<button class="btn btn-primary btn-sm take-task" data-taskid="${task.id}"><i data-lucide="hand"></i> Взять</button>` : ''}
                ${canJoin ? `<button class="btn btn-primary btn-sm take-task" data-taskid="${task.id}"><i data-lucide="user-plus"></i> Присоединиться</button>` : ''}
                ${canSubmit ? `<button class="btn btn-sm send-review" data-taskid="${task.id}"><i data-lucide="send"></i> На проверку</button>` : ''}
                ${canReview ? `<button class="btn btn-accent btn-sm accept-task" data-taskid="${task.id}"><i data-lucide="check-circle"></i> Принять</button>
                              <button class="btn btn-sm reject-task" data-taskid="${task.id}"><i data-lucide="x-circle"></i> Отклонить</button>` : ''}
            </div>
        </div>`;

        if (task.checklist_items?.length || canEdit) {
            html += `<div class="card"><h3 style="display:flex; align-items:center; gap:8px; margin-bottom:12px;"><i data-lucide="check-square"></i> Чек-лист</h3><div id="cardChecklistContainer">`;
            if (task.checklist_items?.length) {
                task.checklist_items.filter(ci => !ci.deleted_at).sort((a,b)=>a.order_index-b.order_index).forEach(item => {
                    html += `<div class="flex" style="margin:8px 0;">
                        <input type="checkbox" ${item.is_completed?'checked':''} data-itemid="${item.id}" class="checklist-toggle" ${canEdit ? '' : 'disabled'} style="width:20px; height:20px; accent-color:var(--accent);">
                        ${canEdit ? `<input type="text" class="input card-checklist-input" value="${(item.text||'').replace(/"/g,'&quot;')}" style="margin:0; flex:1;">` : `<span style="${item.is_completed?'text-decoration:line-through;color:var(--text-soft);':''}">${item.text}</span>`}
                    </div>`;
                });
            }
            html += `</div>`;
            if (canEdit) html += `<button class="btn btn-sm" id="addCardChecklistItem" style="margin-top:12px;"><i data-lucide="plus"></i> Пункт</button>`;
            html += `</div>`;
        }

        html += `<div class="card"><h3 style="display:flex; align-items:center; gap:8px; margin-bottom:12px;"><i data-lucide="message-circle"></i> Обсуждение</h3>`;
        if (commentsWithNames.length) {
            commentsWithNames.forEach(c => {
                html += `<div style="border-top:1px solid rgba(255,255,255,0.05); padding:12px 0; display:flex; gap:10px;">
                    ${getAvatar(c.name)}
                    <div>
                        <div style="font-size:0.8rem; color:var(--text-soft); margin-bottom:4px;"><b>${c.name}</b> · ${new Date(c.created_at).toLocaleString()}</div>
                        <div style="font-size:0.9rem; white-space:pre-wrap;">${c.text}</div>
                    </div>
                </div>`;
            });
        } else html += '<p style="color:var(--text-soft); font-size:0.9rem;">Пока нет комментариев.</p>';
        html += `<textarea class="textarea" id="commentText" placeholder="Написать комментарий..." style="margin-top:12px;"></textarea>
            <button class="btn btn-primary" id="sendComment" data-taskid="${task.id}" style="margin-top:8px;"><i data-lucide="send"></i> Отправить</button>
        </div>`;

        if (modal === 'distribute') html += await distributeModal();

        document.getElementById('app').innerHTML = html;
        initIcons();
        attachTaskCardEvents();
    }

    window.changeTaskColFromCard = async (taskId, newCol) => {
        await supabase.from('tasks').update({ board_column: newCol }).eq('id', taskId);
        if (['open','in_progress','review','completed'].includes(newCol)) await supabase.from('tasks').update({ status: newCol }).eq('id', taskId);
        render();
    };

    function attachTaskCardEvents() {
        document.getElementById('saveTaskCard')?.addEventListener('click', async (e) => {
            e.target.disabled = true;
            const taskId = e.target.dataset.taskid;
            const title = document.getElementById('cardTitle')?.value.trim();
            if (!title) { e.target.disabled = false; return showToast('Название не может быть пустым', 'error'); }
            await supabase.from('tasks').update({
                title,
                description: document.getElementById('cardDesc')?.value || '',
                points: parseInt(document.getElementById('cardPoints')?.value) || 0,
                deadline: document.getElementById('cardDeadline')?.value ? new Date(document.getElementById('cardDeadline').value).toISOString() : null
            }).eq('id', taskId);
            const existingItems = Array.from(document.querySelectorAll('.card-checklist-input')).map(inp => inp.value.trim()).filter(Boolean);
            await supabase.from('checklist_items').update({ deleted_at: new Date().toISOString() }).eq('task_id', taskId);
            if (existingItems.length) await supabase.from('checklist_items').insert(existingItems.map((text, i) => ({ task_id: taskId, text, order_index: i })));
            showToast('Задача обновлена');
            render();
        });

        document.getElementById('deleteTaskCard')?.addEventListener('click', async (e) => {
            await softDeleteTask(e.target.dataset.taskid);
            location.hash = '';
        });

        document.getElementById('addCardChecklistItem')?.addEventListener('click', () => {
            const container = document.getElementById('cardChecklistContainer');
            if (!container) return;
            const el = document.createElement('div');
            el.className = 'flex'; el.style.margin = '8px 0';
            el.innerHTML = `<input type="text" class="input card-checklist-input" placeholder="Новый пункт..." style="margin:0; flex:1;">`;
            container.appendChild(el);
        });

        document.getElementById('sendComment')?.addEventListener('click', async (e) => {
            e.target.disabled = true;
            const text = document.getElementById('commentText')?.value.trim();
            if (!text) { e.target.disabled = false; return; }
            await supabase.from('task_comments').insert({ task_id: e.target.dataset.taskid, user_id: currentUserId, text });
            render();
        });

        document.querySelectorAll('.take-task').forEach(b => b.onclick = async () => {
            const taskId = b.dataset.taskid;
            const { data: task } = await supabase.from('tasks').select('*').eq('id', taskId).maybeSingle();
            if (!task) return;
            const { data: memb } = await supabase.from('memberships').select('*').eq('user_id', currentUserId).eq('community_id', task.community_id).is('deleted_at', null).maybeSingle();
            if (!memb) await supabase.from('memberships').insert({ user_id: currentUserId, community_id: task.community_id, role: 'activist' });
            await supabase.from('task_assignees').upsert({ task_id: taskId, user_id: currentUserId, status: 'in_progress' }, { onConflict: 'task_id,user_id' });
            if (task.status === 'open') await supabase.from('tasks').update({ status: 'in_progress' }).eq('id', taskId);
            showToast('Вы взяли задачу!');
            render();
        });

        document.querySelectorAll('.send-review').forEach(b => b.onclick = async () => {
            await supabase.from('tasks').update({ status: 'review', completed_by_id: currentUserId }).eq('id', b.dataset.taskid);
            showToast('Задача на проверке');
            render();
        });

        document.querySelectorAll('.accept-task').forEach(b => b.onclick = () => {
            distributionTaskId = b.dataset.taskid;
            modal = 'distribute';
            render();
        });

        document.querySelectorAll('.reject-task').forEach(b => b.onclick = async () => {
            await supabase.from('tasks').update({ status: 'in_progress', completed_by_id: null }).eq('id', b.dataset.taskid);
            showToast('Задача возвращена');
            render();
        });

        document.querySelectorAll('.checklist-toggle').forEach(chk => {
            chk.onchange = async (e) => {
                await supabase.from('checklist_items').update({ is_completed: e.target.checked }).eq('id', e.target.dataset.itemid);
            };
        });
    }

    // ═══════════ МОДАЛКИ ═══════════
    function createCommunityModal() {
        return `<div class="modal-overlay" id="modal"><div class="modal">
            <h3 style="margin-bottom:16px;">Новое сообщество</h3>
            <input class="input" id="commName" placeholder="Название">
            <textarea class="textarea" id="commDesc" placeholder="Описание"></textarea>
            <label style="display:flex; align-items:center; gap:8px; margin:16px 0; cursor:pointer;">
                <input type="checkbox" id="commClosed" style="width:18px; height:18px; accent-color:var(--accent);"> <span>Закрытое (по заявке)</span>
            </label>
            <div class="flex" style="justify-content:flex-end;"><button class="btn" id="cancelModal">Отмена</button><button class="btn btn-primary" id="saveCommunity">Создать</button></div>
        </div></div>`;
    }

    async function profileModal(user) {
        const { data: pts } = await supabase.from('points_transactions').select('*, communities(name)').eq('user_id', currentUserId).order('created_at', { ascending: false }).limit(10);
        let hist = '';
        if (pts?.length) {
            hist = '<h4 style="margin:16px 0 8px; font-size:0.9rem; color:var(--text-soft);">История баллов</h4>';
            pts.forEach(p => { hist += `<div class="flex flex-space" style="font-size:0.85rem; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.05);"><span>${p.communities?.name}: <b style="color:var(--accent);">+${p.points}</b></span><span style="color:var(--text-soft);">${new Date(p.created_at).toLocaleDateString()}</span></div>`; });
        }
        return `<div class="modal-overlay" id="modal"><div class="modal">
            <div class="flex" style="gap:16px; margin-bottom:20px;">${getAvatar(user.name)}<div><h3 style="margin:0;">${user.name}</h3><p style="color:var(--text-soft); font-size:0.9rem;">Общий балл: <b style="color:var(--accent); font-size:1.1rem;">${user.total_points||0}</b></p></div></div>
            ${hist}
            <button class="btn" id="cancelModal" style="width:100%; justify-content:center; margin-top:20px;">Закрыть</button>
        </div></div>`;
    }

    async function createTaskModal(leaderCommunityIds, user) {
        if (!leaderCommunityIds.length && !user.is_admin) return '<div class="modal-overlay" id="modal"><div class="modal"><p>Вы не лидер.</p><button class="btn" id="cancelModal">Закрыть</button></div></div>';
        const ids = user.is_admin ? (await supabase.from('communities').select('*').is('deleted_at', null)).data.map(c=>c.id) : leaderCommunityIds;
        const { data: comms } = await supabase.from('communities').select('*').in('id', ids).is('deleted_at', null);
        let commOpts = comms.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
        const { data: allUsers } = await supabase.from('users').select('*');
        let userOpts = allUsers.map(u => `<option value="${u.id}">${u.name}</option>`).join('');
        return `<div class="modal-overlay" id="modal"><div class="modal">
            <h3 style="margin-bottom:16px;">Новая задача</h3>
            <select class="select" id="taskCommunity">${commOpts}</select>
            <input class="input" id="taskTitle" placeholder="Название">
            <textarea class="textarea" id="taskDesc" placeholder="Описание"></textarea>
            <input class="input" type="number" id="taskPoints" value="10" min="0" placeholder="Баллы">
            <label style="display:flex; align-items:center; gap:8px; margin:16px 0; cursor:pointer;"><input type="checkbox" id="taskChecklistEnabled" style="width:18px; height:18px; accent-color:var(--accent);"> <span>Добавить чек-лист</span></label>
            <div id="checklistContainer" style="display:none; margin-bottom:12px;"><div id="checklistItems"></div><button class="btn btn-sm" id="addChecklistItem"><i data-lucide="plus"></i> Пункт</button></div>
            <div class="form-group" style="margin-bottom:16px;"><label style="font-size:0.9rem; color:var(--text-soft);">Назначить исполнителей</label><select class="select" id="assigneeSelect" multiple style="height:100px;">${userOpts}</select></div>
            <div class="flex" style="justify-content:flex-end;"><button class="btn" id="cancelModal">Отмена</button><button class="btn btn-primary" id="saveTask">Создать</button></div>
        </div></div>`;
    }

    async function manageCommunityModal() {
        const commId = selectedCommunityId;
        if (!commId) return '';
        const { data: community } = await supabase.from('communities').select('*').eq('id', commId).maybeSingle();
        if (!community) return '';
        const { data: reqs } = await supabase.from('community_join_requests').select('*, users(name)').eq('community_id', commId).eq('status', 'pending');
        let reqsHtml = '';
        if (reqs && reqs.length) {
            reqsHtml = '<h4 style="margin-top:16px; color:var(--accent);">Заявки на вступление</h4>';
            reqs.forEach(r => { reqsHtml += `<div class="flex flex-space" style="margin-bottom:8px; background:rgba(0,0,0,0.2); padding:8px; border-radius:8px;"><span>${r.users?.name}</span><div><button class="btn btn-sm btn-primary approve-req" data-reqid="${r.id}" data-userid="${r.user_id}">Принять</button><button class="btn btn-sm btn-danger reject-req" data-reqid="${r.id}">Отклонить</button></div></div>`; });
        }
        const { data: members } = await supabase.from('memberships').select('*, users(name)').eq('community_id', commId).is('deleted_at', null);
        let membersHtml = members.map(m => {
            const isCreator = m.role === 'leader_creator';
            return `<div class="flex flex-space" style="margin-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:8px;"><span>${m.users.name} – <span style="color:var(--text-soft);">${m.role}</span></span>${!isCreator ? `<button class="btn btn-sm change-role" data-userid="${m.user_id}" data-role="${m.role==='leader_assigned'?'activist':'leader_assigned'}">${m.role==='leader_assigned'?'Разжаловать':'Назначить лидером'}</button>` : '<span style="color:var(--text-soft); font-size:0.8rem;">создатель</span>'}</div>`;
        }).join('');
        return `<div class="modal-overlay" id="modal"><div class="modal">
            <h3 style="margin-bottom:16px;">Управление «${community.name}»</h3>
            <div style="background:rgba(0,0,0,0.2); padding:16px; border-radius:12px; margin-bottom:20px; border:1px solid var(--border);">
                <h4 style="margin-bottom:12px;">Настройки доступа</h4>
                <label style="display:flex; align-items:center; gap:8px; cursor:pointer;"><input type="checkbox" id="commIsClosedToggle" ${community.is_closed ? 'checked' : ''} style="width:18px; height:18px; accent-color:var(--accent);"><span style="font-size:0.9rem;">Закрытое сообщество (по заявке)</span></label>
                <button class="btn btn-sm btn-primary" id="saveCommSettings" data-commid="${community.id}" style="margin-top:12px; width:100%; justify-content:center;">Сохранить настройки</button>
            </div>
            ${reqsHtml}
            <h4 style="margin-top:16px; margin-bottom:12px;">Участники</h4>
            ${membersHtml}
            <button class="btn" id="cancelModal" style="width:100%; justify-content:center; margin-top:16px;">Закрыть</button>
        </div></div>`;
    }

    async function distributeModal() {
        if (!distributionTaskId) return '';
        const { data: task } = await supabase.from('tasks').select('*, task_assignees(*, users(name))').eq('id', distributionTaskId).maybeSingle();
        if (!task) return '';
        const assignees = task.task_assignees || [];
        const total = task.points || 0;
        const perPerson = Math.floor(total / (assignees.length || 1));
        let rows = '';
        if (assignees.length === 0) rows = `<p style="color:var(--text-soft);">Нет исполнителей.</p>`;
        else assignees.forEach(a => { rows += `<div class="flex flex-space" style="margin:8px 0;"><span>${a.users?.name || '—'}</span><input type="number" min="0" value="${perPerson}" data-userid="${a.user_id}" class="dist-input input" style="width:80px; margin:0;"></div>`; });
        return `<div class="modal-overlay" id="modal"><div class="modal">
            <h3 style="margin-bottom:16px;">Распределить баллы</h3>
            <p style="color:var(--text-soft); font-size:0.9rem; margin-bottom:16px;">Всего баллов: <b>${total}</b>.</p>
            ${rows}
            <div class="flex" style="justify-content:flex-end; margin-top:20px;"><button class="btn" id="cancelModal">Отмена</button><button class="btn btn-primary" id="applyDistribution" data-taskid="${task.id}">Принять</button></div>
        </div></div>`;
    }

    async function editBoardColsModal() {
        if (!selectedBoardCommId) return '';
        const { data: community } = await supabase.from('communities').select('board_columns').eq('id', selectedBoardCommId).maybeSingle();
        let cols = ['open','in_progress','review','completed'];
        if (community && community.board_columns && Array.isArray(community.board_columns) && community.board_columns.length) cols = community.board_columns;
        let colsHtml = cols.map((c, i) => `<div class="flex" style="margin-bottom:8px;"><input class="input" type="text" value="${c}" data-idx="${i}" style="margin:0; flex:1;"><button class="btn btn-sm btn-danger" onclick="this.parentElement.remove()">✕</button></div>`).join('');
        return `<div class="modal-overlay" id="modal"><div class="modal">
            <h3 style="margin-bottom:16px;">Настроить столбцы</h3>
            <p style="font-size:0.8rem; color:var(--text-soft); margin-bottom:12px;">Столбцы для выбранного сообщества.</p>
            <div id="boardColsContainer">${colsHtml}</div>
            <button class="btn btn-sm" id="addBoardColBtn" style="margin:12px 0;">+ Столбец</button>
            <div class="flex" style="justify-content:flex-end;"><button class="btn" id="cancelModal">Отмена</button><button class="btn btn-primary" id="saveBoardCols">Сохранить</button></div>
        </div></div>`;
    }

    // ═══════════ ОБРАБОТЧИКИ ═══════════
    function attachEvents() {
        document.getElementById('viewAllBtn')?.addEventListener('click', () => { currentView='all'; render(); });
        document.getElementById('viewMyBtn')?.addEventListener('click', () => { currentView='my_communities'; render(); });
        document.getElementById('viewParticipatingBtn')?.addEventListener('click', () => { currentView='participating'; render(); });
        document.getElementById('viewBoardBtn')?.addEventListener('click', () => { currentView='board'; render(); });
        document.getElementById('createCommunityBtn')?.addEventListener('click', () => { modal='createCommunity'; render(); });
        document.getElementById('profileBtn')?.addEventListener('click', () => { modal='profile'; render(); });
        document.getElementById('logoutBtn')?.addEventListener('click', () => { currentUserId=null; localStorage.removeItem('portal_user_id'); modal=null; location.hash=''; render(); });
        document.getElementById('createTaskBtn')?.addEventListener('click', () => { modal='createTask'; render(); });
        document.getElementById('trashBtn')?.addEventListener('click', () => { modal='trash'; render(); });
        document.getElementById('feedbackBtn')?.addEventListener('click', () => { location.hash='#/feedback'; });
        document.getElementById('cancelModal')?.addEventListener('click', () => { modal=null; distributionTaskId=null; render(); });

        document.querySelectorAll('.comm-board-tab').forEach(b => b.onclick = () => { selectedBoardCommId = b.dataset.commid; render(); });
        document.getElementById('editBoardColsBtn')?.addEventListener('click', () => { modal='editBoardCols'; render(); });

        document.querySelectorAll('.join-comm').forEach(b => b.onclick = async () => {
            const commId = b.dataset.commid;
            const isClosed = b.dataset.closed === 'true';
            if (isClosed) {
                const { data: existing } = await supabase.from('community_join_requests').select('*').eq('user_id', currentUserId).eq('community_id', commId).eq('status', 'pending').maybeSingle();
                if (!existing) { await supabase.from('community_join_requests').insert({ user_id: currentUserId, community_id: commId }); showToast('Заявка отправлена'); }
                else showToast('Заявка уже отправлена', 'error');
            } else {
                const { data: existing } = await supabase.from('memberships').select('*').eq('user_id', currentUserId).eq('community_id', commId).is('deleted_at', null).maybeSingle();
                if (!existing) { await supabase.from('memberships').insert({ user_id: currentUserId, community_id: commId, role: 'activist' }); showToast('Вы вступили'); }
            }
            render();
        });

        document.getElementById('saveCommunity')?.addEventListener('click', async (e) => {
            e.target.disabled = true;
            const name = document.getElementById('commName')?.value.trim();
            if (!name) { e.target.disabled = false; return showToast('Введите название', 'error'); }
            const newId = crypto.randomUUID();
            await supabase.from('communities').insert({ id: newId, name, description: document.getElementById('commDesc')?.value || '', created_by: currentUserId, is_closed: document.getElementById('commClosed')?.checked });
            await supabase.from('memberships').insert({ user_id: currentUserId, community_id: newId, role: 'leader_creator' });
            modal = null; showToast('Сообщество создано'); render();
        });

        document.getElementById('saveTask')?.addEventListener('click', async (e) => {
            e.target.disabled = true;
            const title = document.getElementById('taskTitle')?.value.trim();
            if (!title) { e.target.disabled = false; return showToast('Введите название', 'error'); }
            const taskId = crypto.randomUUID();
            const communityId = document.getElementById('taskCommunity')?.value;
            const selected = Array.from(document.getElementById('assigneeSelect')?.selectedOptions || []).map(o => o.value);
            const initialStatus = selected.length > 0 ? 'in_progress' : 'open';
            await supabase.from('tasks').insert({ id: taskId, community_id: communityId, title, description: document.getElementById('taskDesc')?.value || '', points: parseInt(document.getElementById('taskPoints')?.value) || 0, creator_id: currentUserId, status: initialStatus });
            if (document.getElementById('taskChecklistEnabled')?.checked) {
                const items = editingChecklist.filter(t => t.trim()).map((text, idx) => ({task_id: taskId, text, order_index: idx}));
                if (items.length) await supabase.from('checklist_items').insert(items);
            }
            if (selected.length) await supabase.from('task_assignees').insert(selected.map(uid => ({task_id: taskId, user_id: uid, status: 'in_progress'})));
            modal = null; showToast('Задача создана'); render();
        });

        document.getElementById('addChecklistItem')?.addEventListener('click', () => {
            const container = document.getElementById('checklistItems');
            if (!container) return;
            editingChecklist.push('');
            const idx = editingChecklist.length - 1;
            const el = document.createElement('div');
            el.innerHTML = `<input class="input checklist-input" data-index="${idx}" placeholder="Пункт">`;
            container.appendChild(el);
            el.querySelector('input').oninput = function() { editingChecklist[this.dataset.index] = this.value; };
        });

        document.getElementById('take-task-btn')?.addEventListener('click', () => {});
        document.querySelectorAll('.take-task').forEach(b => b.onclick = async () => {
            const taskId = b.dataset.taskid;
            const { data: task } = await supabase.from('tasks').select('*').eq('id', taskId).maybeSingle();
            if (!task) return;
            const { data: memb } = await supabase.from('memberships').select('*').eq('user_id', currentUserId).eq('community_id', task.community_id).is('deleted_at', null).maybeSingle();
            if (!memb) await supabase.from('memberships').insert({ user_id: currentUserId, community_id: task.community_id, role: 'activist' });
            await supabase.from('task_assignees').upsert({ task_id: taskId, user_id: currentUserId, status: 'in_progress' }, { onConflict: 'task_id,user_id' });
            if (task.status === 'open') await supabase.from('tasks').update({ status: 'in_progress' }).eq('id', taskId);
            showToast('Вы взяли задачу!');
            render();
        });

        document.querySelectorAll('.send-review').forEach(b => b.onclick = async () => {
            await supabase.from('tasks').update({ status: 'review', completed_by_id: currentUserId }).eq('id', b.dataset.taskid);
            showToast('Задача на проверке');
            render();
        });
        document.querySelectorAll('.accept-task').forEach(b => b.onclick = () => { distributionTaskId = b.dataset.taskid; modal = 'distribute'; render(); });
        document.querySelectorAll('.reject-task').forEach(b => b.onclick = async () => {
            await supabase.from('tasks').update({ status: 'in_progress', completed_by_id: null }).eq('id', b.dataset.taskid);
            showToast('Задача возвращена'); render();
        });

        document.querySelectorAll('.delete-task').forEach(b => b.onclick = () => softDeleteTask(b.dataset.taskid));
        document.querySelectorAll('.restore-task').forEach(b => b.onclick = async () => {
            await supabase.from('tasks').update({ deleted_at: null }).eq('id', b.dataset.taskid);
            showToast('Восстановлено'); render();
        });
        document.querySelectorAll('.restore-comm').forEach(b => b.onclick = async () => {
            await supabase.from('communities').update({ deleted_at: null }).eq('id', b.dataset.commid);
            showToast('Восстановлено'); render();
        });

        document.querySelectorAll('.manage-comm').forEach(b => b.onclick = () => {
            selectedCommunityId = b.dataset.commid;
            modal = 'manageCommunity'; render();
        });
        document.getElementById('saveCommSettings')?.addEventListener('click', async (e) => {
            e.target.disabled = true;
            await supabase.from('communities').update({ is_closed: document.getElementById('commIsClosedToggle').checked }).eq('id', e.target.dataset.commid);
            showToast('Настройки сохранены'); render();
        });
        document.querySelectorAll('.approve-req').forEach(b => b.onclick = async () => {
            await supabase.from('memberships').insert({ user_id: b.dataset.userid, community_id: selectedCommunityId, role: 'activist' });
            await supabase.from('community_join_requests').update({ status: 'approved' }).eq('id', b.dataset.reqid);
            showToast('Заявка одобрена'); render();
        });
        document.querySelectorAll('.reject-req').forEach(b => b.onclick = async () => {
            await supabase.from('community_join_requests').update({ status: 'rejected' }).eq('id', b.dataset.reqid);
            render();
        });
        document.querySelectorAll('.change-role').forEach(b => b.onclick = async () => {
            await supabase.from('memberships').update({ role: b.dataset.role }).eq('user_id', b.dataset.userid).eq('community_id', selectedCommunityId);
            render();
        });

        document.getElementById('applyDistribution')?.addEventListener('click', async (e) => {
            e.target.disabled = true;
            const taskId = e.target.dataset.taskid;
            const inputs = document.querySelectorAll('.dist-input');
            for (const inp of inputs) {
                const uid = inp.dataset.userid;
                const val = parseInt(inp.value) || 0;
                if (uid && val > 0) {
                    const { data: u } = await supabase.from('users').select('total_points').eq('id', uid).maybeSingle();
                    await supabase.from('users').update({ total_points: (u?.total_points || 0) + val }).eq('id', uid);
                    const { data: task } = await supabase.from('tasks').select('community_id').eq('id', taskId).single();
                    await supabase.from('points_transactions').insert({ user_id: uid, task_id: taskId, community_id: task.community_id, points: val });
                }
            }
            await supabase.from('tasks').update({ status: 'completed' }).eq('id', taskId);
            modal = null; distributionTaskId = null; showToast('Задача завершена'); render();
        });

        document.getElementById('addBoardColBtn')?.addEventListener('click', () => {
            const container = document.getElementById('boardColsContainer');
            if (!container) return;
            const el = document.createElement('div');
            el.className = 'flex'; el.style.marginBottom = '8px';
            el.innerHTML = `<input class="input" placeholder="Название..." style="margin:0; flex:1;"> <button class="btn btn-sm btn-danger" onclick="this.parentElement.remove()">✕</button>`;
            container.appendChild(el);
        });
        document.getElementById('saveBoardCols')?.addEventListener('click', async (e) => {
            e.target.disabled = true;
            const inputs = Array.from(document.querySelectorAll('#boardColsContainer input')).map(i => i.value.trim()).filter(Boolean);
            if (!inputs.length) { e.target.disabled = false; return showToast('Нужен хотя бы один столбец', 'error'); }
            await supabase.from('communities').update({ board_columns: inputs }).eq('id', selectedBoardCommId);
            modal = null; showToast('Столбцы сохранены'); render();
        });
    }

    // Заглушка (не используется)
    let editingChecklist = [];

    render();
})();
</script>
</body>
</html>
