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
            // Get current user
            this.user = await api.getCurrentUser();
            this.renderNav();
            await this.loadProgrammes();
        } catch (error) {
            console.error('Failed to initialize:', error);
            window.location.href = '/aacsb/login';
        }
    }

    renderNav() {
        const navUser = document.getElementById('nav-user');
        if (navUser) {
            navUser.innerHTML = `
                <span>${this.user.firstname} ${this.user.lastname}</span>
                <a href="/aacsb/aol/settings" class="btn btn-sm btn-outline" style="color: white; border-color: rgba(255,255,255,0.3);">
                    Settings
                </a>
                <button onclick="app.logout()" class="btn btn-sm btn-outline" style="color: white; border-color: rgba(255,255,255,0.3);">
                    Logout
                </button>
            `;
        }

        // Add Admin link for system admins
        if (this.isAdmin()) {
            const navLinks = document.querySelector('.nav-links');
            if (navLinks && !navLinks.querySelector('a[href="/aacsb/admin"]')) {
                const adminLi = document.createElement('li');
                adminLi.innerHTML = '<a href="/aacsb/admin">Admin</a>';
                navLinks.appendChild(adminLi);
            }
        }
    }

    async logout() {
        try {
            await api.logout();
            window.location.href = '/aacsb/login';
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
                    <h3>No programmes found</h3>
                    <p>Contact an administrator to set up study programmes.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = this.programmes.map(prog => `
            <a href="/aacsb/aol/programme/${prog.id}" class="programme-card">
                <h3>${prog.name_eng || prog.name_no}</h3>
                <div class="code">${prog.programme_code}</div>
                <div class="stats">
                    <span>${prog.goal_count} goals</span>
                    <span>${prog.course_count} courses</span>
                </div>
            </a>
        `).join('');
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
