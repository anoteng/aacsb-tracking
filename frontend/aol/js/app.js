/**
 * Main AOL Application
 */

class AolApp {
    constructor() {
        this.user = null;
        this.programmes = [];
        this.init();
    }

    async init() {
        try {
            await i18n.init();

            // Get current user
            this.user = await api.getCurrentUser();
            this.renderNav();
            await Promise.all([
                this.loadProgrammes(),
                this.loadUpcomingMeasurements(),
            ]);
        } catch (error) {
            console.error('Failed to initialize:', error);
            window.location.href = window.APP_BASE + '/login';
        }
    }

    renderNav() {
        const navUser = document.getElementById('nav-user');
        if (navUser) {
            navUser.innerHTML = `
                <span>${this.user.firstname} ${this.user.lastname}</span>
                <a href="${window.APP_BASE}/aol/settings" class="btn btn-sm btn-outline" style="color: white; border-color: rgba(255,255,255,0.3);">
                    ${i18n.t('Settings')}
                </a>
                <button onclick="app.logout()" class="btn btn-sm btn-outline" style="color: white; border-color: rgba(255,255,255,0.3);">
                    ${i18n.t('Logout')}
                </button>
            `;
        }

        if (this.user.impersonation && this.user.impersonation.active) {
            const banner = document.getElementById('impersonation-banner');
            if (banner) {
                document.getElementById('impersonating-name').textContent = this.user.impersonation.viewing_as.name;
                banner.style.display = 'flex';
            }
        }
    }

    async logout() {
        try {
            await api.logout();
            window.location.href = window.APP_BASE + '/login';
        } catch (error) {
            console.error('Logout failed:', error);
        }
    }

    async loadProgrammes() {
        const container = document.getElementById('programmes-grid');
        if (!container) return;

        container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

        try {
            this.programmes = await api.getProgrammes();
            this.renderProgrammes();
        } catch (error) {
            container.innerHTML = `<div class="alert alert-error">${error.message}</div>`;
        }
    }

    renderProgrammes() {
        const container = document.getElementById('programmes-grid');
        if (!container) return;

        if (this.programmes.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <h3>${i18n.t('No programmes found')}</h3>
                    <p>${i18n.t('Contact an administrator to set up study programmes.')}</p>
                </div>
            `;
            return;
        }

        container.innerHTML = this.programmes.map(prog => `
            <a href="${window.APP_BASE}/aol/programme/${prog.id}" class="programme-card">
                <h3>${i18n.getLang() === 'no' ? (prog.name_no || prog.name_eng) : (prog.name_eng || prog.name_no)}</h3>
                <div class="code">${prog.programme_code}</div>
                <div class="stats">
                    <span>${i18n.t('{{n}} goals', { n: prog.goal_count })}</span>
                    <span>${i18n.t('{{n}} courses', { n: prog.course_count })}</span>
                </div>
            </a>
        `).join('');
    }

    async loadUpcomingMeasurements() {
        const container = document.getElementById('upcoming-measurements');
        if (!container) return;

        try {
            const items = await api.getUpcomingMeasurements();
            this.renderUpcomingMeasurements(items, container);
        } catch (error) {
            container.innerHTML = `<div class="alert alert-error">${error.message}</div>`;
        }
    }

    renderUpcomingMeasurements(items, container) {
        if (items.length === 0) {
            container.innerHTML = `<p class="text-muted">${i18n.t('No measurements scheduled for the coming years.')}</p>`;
            return;
        }

        // Group by year
        const byYear = {};
        items.forEach(item => {
            if (!byYear[item.year_name]) byYear[item.year_name] = [];
            byYear[item.year_name].push(item);
        });

        container.innerHTML = Object.entries(byYear).map(([yearName, yearItems]) => {
            // Group by programme within year
            const byProgramme = {};
            yearItems.forEach(item => {
                const key = item.programme_code;
                if (!byProgramme[key]) byProgramme[key] = { name: item.programme_name, code: item.programme_code, id: item.programme_id, items: [] };
                byProgramme[key].items.push(item);
            });

            const progHtml = Object.values(byProgramme).map(prog => `
                <div style="margin-bottom:0.75rem;">
                    <a href="${window.APP_BASE}/aol/programme/${prog.id}" style="font-weight:600; color:#1e40af;">${prog.code}</a>
                    <span class="text-muted" style="font-size:0.875rem; margin-left:0.4rem;">${prog.name}</span>
                    <ul style="margin:0.3rem 0 0 1.1rem; padding:0; list-style:disc;">
                        ${prog.items.map(item => `
                            <li style="font-size:0.9rem; margin-bottom:0.2rem;">
                                ${item.has_assessment
                                    ? `<span style="color:#16a34a;" title="${i18n.t('Assessment recorded')}">&#10003;</span>`
                                    : `<span style="color:#d97706;" title="${i18n.t('No assessment yet')}">&#9679;</span>`}
                                <span style="color:#6b7280; font-size:0.8rem;">${item.category_name} &rsaquo;</span>
                                ${item.goal_text.length > 100 ? item.goal_text.slice(0, 100) + '…' : item.goal_text}
                                ${item.teaching_periods.length ? `<span class="badge badge-outline" style="margin-left:0.3rem; font-size:0.75rem;">${item.teaching_periods.join(', ')}</span>` : ''}
                            </li>
                        `).join('')}
                    </ul>
                </div>
            `).join('');

            return `
                <div class="card" style="margin-bottom:1rem;">
                    <h4 style="margin:0 0 0.75rem; font-size:1rem; color:#374151;">${i18n.t('Academic Year')} ${yearName}</h4>
                    ${progHtml}
                </div>
            `;
        }).join('');
    }

    hasRole(role) {
        return this.user && this.user.roles && this.user.roles.includes(role);
    }

    isAdmin() {
        return this.hasRole('system_admin');
    }

    canEditGoal(goal) {
        if (this.isAdmin()) return true;
        if (this.hasRole('programme_leader')) return true;
        // Check if assigned to goal
        if (goal.assigned_staff) {
            return goal.assigned_staff.some(s => s.user_id === this.user.id);
        }
        return false;
    }
}

// Global app instance
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new AolApp();
});
