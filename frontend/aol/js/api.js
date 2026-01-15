/**
 * API Client for AACSB AOL
 */

const API_BASE = '/aacsb/api';

class ApiClient {
    constructor() {
        this.token = null;
    }

    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const config = {
            ...options,
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        };

        if (options.body && typeof options.body === 'object') {
            config.body = JSON.stringify(options.body);
        }

        const response = await fetch(url, config);

        if (response.status === 401) {
            window.location.href = '/aacsb/login';
            throw new Error('Unauthorized');
        }

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || 'Request failed');
        }

        if (response.status === 204) {
            return null;
        }

        return response.json();
    }

    // Auth
    async getCurrentUser() {
        return this.request('/auth/me');
    }

    async logout() {
        return this.request('/auth/logout', { method: 'POST' });
    }

    async setPassword(password) {
        return this.request('/auth/set-password', {
            method: 'POST',
            body: { password },
        });
    }

    // Programmes
    async getProgrammes() {
        return this.request('/aol/programmes');
    }

    async getProgramme(id) {
        return this.request(`/aol/programmes/${id}`);
    }

    // Categories
    async getCategories() {
        return this.request('/aol/categories');
    }

    // Goals
    async getGoals(programmeId) {
        return this.request(`/aol/programmes/${programmeId}/goals`);
    }

    async createGoal(programmeId, data) {
        return this.request(`/aol/programmes/${programmeId}/goals`, {
            method: 'POST',
            body: data,
        });
    }

    async updateGoal(goalId, data) {
        return this.request(`/aol/goals/${goalId}`, {
            method: 'PATCH',
            body: data,
        });
    }

    async deleteGoal(goalId) {
        return this.request(`/aol/goals/${goalId}`, { method: 'DELETE' });
    }

    // Staff Assignments
    async assignStaffToGoal(goalId, userId) {
        return this.request(`/aol/goals/${goalId}/assign/${userId}`, { method: 'POST' });
    }

    async unassignStaffFromGoal(goalId, userId) {
        return this.request(`/aol/goals/${goalId}/assign/${userId}`, { method: 'DELETE' });
    }

    // Matrix
    async getMatrix(programmeId) {
        return this.request(`/aol/programmes/${programmeId}/matrix`);
    }

    async updateMatrixEntry(goalId, courseId, data) {
        return this.request(`/aol/matrix/${goalId}/${courseId}`, {
            method: 'PUT',
            body: data,
        });
    }

    // Courses
    async getProgrammeCourses(programmeId) {
        return this.request(`/aol/programmes/${programmeId}/courses`);
    }

    async searchCourses(query) {
        return this.request(`/aol/courses/search?q=${encodeURIComponent(query)}`);
    }

    async addCourseToProgramme(programmeId, courseId, year = 1, semester = 1) {
        return this.request(`/aol/programmes/${programmeId}/courses/${courseId}?year=${year}&semester=${semester}`, {
            method: 'POST',
        });
    }

    // Rubrics
    async getRubrics(goalId) {
        return this.request(`/aol/goals/${goalId}/rubrics`);
    }

    async createRubric(goalId, data) {
        return this.request(`/aol/goals/${goalId}/rubrics`, {
            method: 'POST',
            body: data,
        });
    }

    async updateRubric(rubricId, data) {
        return this.request(`/aol/rubrics/${rubricId}`, {
            method: 'PATCH',
            body: data,
        });
    }

    // Traits
    async createTrait(rubricId, data) {
        return this.request(`/aol/rubrics/${rubricId}/traits`, {
            method: 'POST',
            body: data,
        });
    }

    async updateTrait(traitId, data) {
        return this.request(`/aol/traits/${traitId}`, {
            method: 'PATCH',
            body: data,
        });
    }

    async deleteTrait(traitId) {
        return this.request(`/aol/traits/${traitId}`, { method: 'DELETE' });
    }

    // Assessments
    async getAssessments(rubricId) {
        return this.request(`/aol/rubrics/${rubricId}/assessments`);
    }

    async createAssessment(data) {
        return this.request('/aol/assessments', {
            method: 'POST',
            body: data,
        });
    }

    async addAssessmentResults(assessmentId, results) {
        return this.request(`/aol/assessments/${assessmentId}/results`, {
            method: 'POST',
            body: results,
        });
    }

    // Users
    async getUsers() {
        return this.request('/users');
    }

    async createUser(data) {
        return this.request('/users', {
            method: 'POST',
            body: data,
        });
    }

    async updateUser(userId, data) {
        return this.request(`/users/${userId}`, {
            method: 'PATCH',
            body: data,
        });
    }

    async assignRole(userId, roleName) {
        return this.request(`/users/${userId}/roles`, {
            method: 'POST',
            body: { role_name: roleName },
        });
    }

    async removeRole(userId, roleName) {
        return this.request(`/users/${userId}/roles/${roleName}`, { method: 'DELETE' });
    }

    async getRoles() {
        return this.request('/users/roles/available');
    }
}

// Export singleton
const api = new ApiClient();
