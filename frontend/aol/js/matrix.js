/**
 * Goal-Course Matrix Component
 * Learning levels: 0=None, 1=Introduced, 2=Developing, 3=Mastery
 */

const LEVEL_LABELS = {
    0: { short: '-', label: 'None', class: 'level-none' },
    1: { short: 'I', label: 'Introduced', class: 'level-intro' },
    2: { short: 'D', label: 'Developing', class: 'level-dev' },
    3: { short: 'M', label: 'Mastery', class: 'level-mastery' },
};

class MatrixComponent {
    constructor(containerId, programmeId) {
        this.container = document.getElementById(containerId);
        this.programmeId = programmeId;
        this.data = null;
        this.matrixLookup = {};
        this.methods = { learning: [], assessment: [], technologies: [] };
    }

    async load() {
        if (!this.container) return;

        this.container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

        try {
            // Load matrix data and lookup tables in parallel
            const [matrixData, learningMethods, assessmentMethods, technologies] = await Promise.all([
                api.getMatrix(this.programmeId),
                api.request('/aol/methods/learning'),
                api.request('/aol/methods/assessment'),
                api.request('/aol/technologies'),
            ]);

            this.data = matrixData;
            this.methods.learning = learningMethods;
            this.methods.assessment = assessmentMethods;
            this.methods.technologies = technologies;

            this.buildLookup();
            this.render();
        } catch (error) {
            this.container.innerHTML = `<div class="alert alert-error">${error.message}</div>`;
        }
    }

    buildLookup() {
        this.matrixLookup = {};
        if (this.data && this.data.matrix) {
            this.data.matrix.forEach(entry => {
                const key = `${entry.goal_id}-${entry.course_id}`;
                this.matrixLookup[key] = entry;
            });
        }
    }

    getEntry(goalId, courseId) {
        const key = `${goalId}-${courseId}`;
        return this.matrixLookup[key] || { learning_level: 0, is_assessed: false };
    }

    render() {
        if (!this.data || this.data.goals.length === 0) {
            this.container.innerHTML = `
                <div class="empty-state">
                    <h3>No goals defined</h3>
                    <p>Add learning goals to see the curriculum matrix.</p>
                </div>
            `;
            return;
        }

        if (this.data.courses.length === 0) {
            this.container.innerHTML = `
                <div class="empty-state">
                    <h3>No courses assigned</h3>
                    <p>Add courses to this programme to build the matrix.</p>
                </div>
            `;
            return;
        }

        // Build category header row
        const categoryHeaders = this.buildCategoryHeaders();

        // Group courses by semester
        const coursesBySemester = this.groupCoursesBySemester();

        const html = `
            <div class="matrix-container">
                <table class="matrix">
                    <thead>
                        ${categoryHeaders}
                        <tr>
                            <th class="course-cell">Course</th>
                            <th class="meta-cell">Learning</th>
                            <th class="meta-cell">Assessment</th>
                            <th class="meta-cell">Tech</th>
                            <th class="meta-cell">SDGs</th>
                            ${this.data.goals.map((goal, idx) => `
                                <th class="goal-header" title="${goal.goal_eng || goal.goal_no}">
                                    LO${idx + 1}
                                </th>
                            `).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${this.renderCoursesBySemester(coursesBySemester)}
                    </tbody>
                </table>
            </div>
            <div class="mt-2">
                <div class="flex gap-2 text-sm">
                    <strong>Learning Level:</strong>
                    <span class="level-badge level-none">- None</span>
                    <span class="level-badge level-intro">I Introduced</span>
                    <span class="level-badge level-dev">D Developing</span>
                    <span class="level-badge level-mastery">M Mastery</span>
                    <span style="margin-left: 1rem;"><strong>A</strong> = Assessed</span>
                </div>
            </div>
        `;

        this.container.innerHTML = html;
        this.addStyles();

        // Add click handlers if user is admin
        if (app.isAdmin()) {
            this.container.querySelectorAll('.matrix-cell').forEach(cell => {
                cell.addEventListener('click', () => this.handleCellClick(cell));
            });
            this.container.querySelectorAll('.meta-cell-edit').forEach(cell => {
                cell.addEventListener('click', () => this.handleMetaClick(cell));
            });
        }
    }

    buildCategoryHeaders() {
        // Group goals by category to build colspan headers
        const categorySpans = [];
        let currentCategory = null;
        let currentSpan = 0;

        this.data.goals.forEach((goal, idx) => {
            const catName = goal.category_name || 'Uncategorized';
            if (catName !== currentCategory) {
                if (currentCategory !== null) {
                    categorySpans.push({ name: currentCategory, span: currentSpan });
                }
                currentCategory = catName;
                currentSpan = 1;
            } else {
                currentSpan++;
            }
        });
        // Push the last category
        if (currentCategory !== null) {
            categorySpans.push({ name: currentCategory, span: currentSpan });
        }

        if (categorySpans.length === 0) return '';

        return `
            <tr class="category-header-row">
                <th colspan="5"></th>
                ${categorySpans.map(cat => `
                    <th colspan="${cat.span}" class="category-header">${cat.name}</th>
                `).join('')}
            </tr>
        `;
    }

    groupCoursesBySemester() {
        const groups = {};
        this.data.courses.forEach(course => {
            const sem = course.semester || 1;
            if (!groups[sem]) {
                groups[sem] = [];
            }
            groups[sem].push(course);
        });
        return groups;
    }

    getSemesterLabel(sem) {
        const suffixes = { 1: 'st', 2: 'nd', 3: 'rd' };
        const suffix = suffixes[sem] || 'th';
        return `${sem}${suffix} semester`;
    }

    renderCoursesBySemester(coursesBySemester) {
        const semesters = Object.keys(coursesBySemester).map(Number).sort((a, b) => a - b);
        const totalCols = 5 + this.data.goals.length;

        return semesters.map(sem => {
            const courses = coursesBySemester[sem];
            const semLabel = this.getSemesterLabel(sem);
            return `
                <tr class="semester-header-row">
                    <td colspan="${totalCols}" class="semester-header">${semLabel}</td>
                </tr>
                ${courses.map(course => this.renderCourseRow(course)).join('')}
            `;
        }).join('');
    }

    renderCourseRow(course) {
        const isAdmin = app.isAdmin();
        return `
            <tr>
                <td class="course-cell" title="${course.name_eng || course.name_no}">
                    ${course.course_code}
                </td>
                <td class="meta-cell ${isAdmin ? 'meta-cell-edit' : ''}" data-course="${course.id}" data-type="learning">
                    ${course.learning_methods?.join(', ') || '-'}
                </td>
                <td class="meta-cell ${isAdmin ? 'meta-cell-edit' : ''}" data-course="${course.id}" data-type="assessment">
                    ${course.assessment_methods?.join(', ') || '-'}
                </td>
                <td class="meta-cell ${isAdmin ? 'meta-cell-edit' : ''}" data-course="${course.id}" data-type="tech">
                    ${course.technologies?.join(', ') || '-'}
                </td>
                <td class="meta-cell ${isAdmin ? 'meta-cell-edit' : ''}" data-course="${course.id}" data-type="sdgs">
                    ${course.sdgs || '-'}
                </td>
                ${this.data.goals.map(goal => {
                    const entry = this.getEntry(goal.id, course.id);
                    return this.renderCell(goal.id, course.id, entry);
                }).join('')}
            </tr>
        `;
    }

    renderCell(goalId, courseId, entry) {
        const isAdmin = app.isAdmin();
        const level = entry.learning_level || 0;
        const levelInfo = LEVEL_LABELS[level] || LEVEL_LABELS[0];
        const assessed = entry.is_assessed;

        return `
            <td class="matrix-cell ${isAdmin ? 'clickable' : ''} ${levelInfo.class}"
                data-goal="${goalId}"
                data-course="${courseId}">
                <span class="level-indicator">${levelInfo.short}</span>
                ${assessed ? '<span class="assessed-indicator">A</span>' : ''}
            </td>
        `;
    }

    addStyles() {
        if (document.getElementById('matrix-styles')) return;

        const style = document.createElement('style');
        style.id = 'matrix-styles';
        style.textContent = `
            .matrix .category-header-row th {
                background: var(--primary);
                color: white;
                font-weight: 600;
                text-align: center;
                padding: 0.5rem;
                font-size: 0.85rem;
                border-right: 2px solid white;
            }
            .matrix .category-header-row th:first-child {
                background: transparent;
            }
            .matrix .semester-header-row td {
                background: #334155;
                color: white;
                font-weight: 600;
                padding: 0.4rem 0.75rem;
                font-size: 0.8rem;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .matrix .meta-cell {
                font-size: 0.7rem;
                max-width: 80px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                color: var(--secondary);
            }
            .matrix .meta-cell-edit {
                cursor: pointer;
            }
            .matrix .meta-cell-edit:hover {
                background: var(--light);
            }
            .matrix-cell {
                text-align: center;
                min-width: 45px;
                position: relative;
            }
            .matrix-cell.clickable {
                cursor: pointer;
            }
            .matrix-cell.clickable:hover {
                opacity: 0.8;
            }
            .matrix-cell .level-indicator {
                font-weight: bold;
                font-size: 0.85rem;
            }
            .matrix-cell .assessed-indicator {
                font-size: 0.6rem;
                position: absolute;
                top: 2px;
                right: 2px;
                color: var(--success);
                font-weight: bold;
            }
            .matrix-cell.level-none { background: #f1f5f9; color: #94a3b8; }
            .matrix-cell.level-intro { background: #dbeafe; color: #1e40af; }
            .matrix-cell.level-dev { background: #fef3c7; color: #92400e; }
            .matrix-cell.level-mastery { background: #d1fae5; color: #065f46; }
            .level-badge {
                display: inline-block;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 0.75rem;
            }
            .level-badge.level-none { background: #f1f5f9; color: #94a3b8; }
            .level-badge.level-intro { background: #dbeafe; color: #1e40af; }
            .level-badge.level-dev { background: #fef3c7; color: #92400e; }
            .level-badge.level-mastery { background: #d1fae5; color: #065f46; }
        `;
        document.head.appendChild(style);
    }

    async handleCellClick(cell) {
        const goalId = parseInt(cell.dataset.goal);
        const courseId = parseInt(cell.dataset.course);
        const entry = this.getEntry(goalId, courseId);

        this.showEditModal(goalId, courseId, entry);
    }

    handleMetaClick(cell) {
        const courseId = parseInt(cell.dataset.course);
        const type = cell.dataset.type;
        const course = this.data.courses.find(c => c.id === courseId);

        this.showMetadataModal(course, type);
    }

    showEditModal(goalId, courseId, entry) {
        const goal = this.data.goals.find(g => g.id === goalId);
        const course = this.data.courses.find(c => c.id === courseId);

        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h2>Edit Learning Outcome</h2>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <p class="mb-2">
                        <strong>Goal:</strong> ${goal.goal_eng || goal.goal_no}<br>
                        <strong>Course:</strong> ${course.course_code} - ${course.name_eng || course.name_no}
                    </p>
                    <div class="form-group">
                        <label class="form-label">Learning Level</label>
                        <select id="matrix-level" class="form-select">
                            <option value="0" ${entry.learning_level === 0 ? 'selected' : ''}>0 - None</option>
                            <option value="1" ${entry.learning_level === 1 ? 'selected' : ''}>1 - Introduced (concept first presented)</option>
                            <option value="2" ${entry.learning_level === 2 ? 'selected' : ''}>2 - Developing (students practice skills)</option>
                            <option value="3" ${entry.learning_level === 3 ? 'selected' : ''}>3 - Mastery (thorough learning, assessed)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">
                            <input type="checkbox" id="matrix-assessed" ${entry.is_assessed ? 'checked' : ''}>
                            This learning outcome is assessed in this course
                        </label>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
                    <button class="btn btn-primary" id="save-matrix-btn">Save</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.classList.add('active'));

        document.getElementById('save-matrix-btn').addEventListener('click', async () => {
            const data = {
                learning_level: parseInt(document.getElementById('matrix-level').value),
                is_assessed: document.getElementById('matrix-assessed').checked,
            };

            try {
                await api.updateMatrixEntry(goalId, courseId, data);
                const key = `${goalId}-${courseId}`;
                this.matrixLookup[key] = { ...data, goal_id: goalId, course_id: courseId };
                this.render();
                modal.remove();
            } catch (error) {
                alert('Failed to save: ' + error.message);
            }
        });
    }

    showMetadataModal(course, focusType) {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal" style="max-width: 700px;">
                <div class="modal-header">
                    <h2>Edit Course Metadata</h2>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <p class="mb-2">
                        <strong>Course:</strong> ${course.course_code} - ${course.name_eng || course.name_no}
                    </p>

                    <div class="form-group">
                        <label class="form-label">Semester</label>
                        <select id="course-semester" class="form-select" style="width: auto;">
                            ${[1,2,3,4,5,6,7,8,9,10].map(s => `
                                <option value="${s}" ${course.semester === s ? 'selected' : ''}>${this.getSemesterLabel(s)}</option>
                            `).join('')}
                        </select>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Learning Methods</label>
                        <div class="checkbox-grid" id="learning-methods">
                            ${this.methods.learning.map(m => `
                                <label class="checkbox-item">
                                    <input type="checkbox" value="${m.code}" ${course.learning_methods?.includes(m.code) ? 'checked' : ''}>
                                    ${m.code} - ${m.name_eng}
                                </label>
                            `).join('')}
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Assessment Methods</label>
                        <div class="checkbox-grid" id="assessment-methods">
                            ${this.methods.assessment.map(m => `
                                <label class="checkbox-item">
                                    <input type="checkbox" value="${m.code}" ${course.assessment_methods?.includes(m.code) ? 'checked' : ''}>
                                    ${m.code} - ${m.name_eng}
                                </label>
                            `).join('')}
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Technologies</label>
                        <div class="checkbox-grid" id="technologies">
                            ${this.methods.technologies.map(t => `
                                <label class="checkbox-item">
                                    <input type="checkbox" value="${t.code}" ${course.technologies?.includes(t.code) ? 'checked' : ''}>
                                    ${t.code} - ${t.name_eng}
                                </label>
                            `).join('')}
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">SDGs (Sustainable Development Goals)</label>
                        <div class="checkbox-grid" id="sdgs">
                            ${Array.from({length: 17}, (_, i) => i + 1).map(n => `
                                <label class="checkbox-item">
                                    <input type="checkbox" value="${n}" ${course.sdgs?.split(',').includes(String(n)) ? 'checked' : ''}>
                                    SDG ${n}
                                </label>
                            `).join('')}
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
                    <button class="btn btn-primary" id="save-meta-btn">Save</button>
                </div>
            </div>
        `;

        // Add checkbox grid styles
        const style = modal.querySelector('style') || document.createElement('style');
        style.textContent += `
            .checkbox-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                gap: 0.5rem;
                max-height: 150px;
                overflow-y: auto;
                padding: 0.5rem;
                background: var(--light);
                border-radius: 4px;
            }
            .checkbox-item {
                display: flex;
                align-items: center;
                gap: 0.25rem;
                font-size: 0.8rem;
                cursor: pointer;
            }
            .checkbox-item input {
                cursor: pointer;
            }
        `;
        if (!modal.querySelector('style')) modal.appendChild(style);

        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.classList.add('active'));

        document.getElementById('save-meta-btn').addEventListener('click', async () => {
            const getCheckedValues = (containerId) => {
                return Array.from(modal.querySelectorAll(`#${containerId} input:checked`))
                    .map(cb => cb.value);
            };

            const newSemester = parseInt(document.getElementById('course-semester').value);
            const data = {
                learning_methods: getCheckedValues('learning-methods'),
                assessment_methods: getCheckedValues('assessment-methods'),
                technologies: getCheckedValues('technologies'),
                sdgs: getCheckedValues('sdgs').map(Number),
            };

            try {
                // Update semester if changed
                if (newSemester !== course.semester) {
                    await api.request(`/aol/programmes/${this.programmeId}/courses/${course.id}/semester`, {
                        method: 'PUT',
                        body: { semester: newSemester },
                    });
                }

                // Update other metadata
                await api.request(`/aol/programmes/${this.programmeId}/courses/${course.id}/metadata`, {
                    method: 'PUT',
                    body: data,
                });

                // Update local data
                const courseIdx = this.data.courses.findIndex(c => c.id === course.id);
                if (courseIdx >= 0) {
                    this.data.courses[courseIdx].semester = newSemester;
                    this.data.courses[courseIdx].learning_methods = data.learning_methods;
                    this.data.courses[courseIdx].assessment_methods = data.assessment_methods;
                    this.data.courses[courseIdx].technologies = data.technologies;
                    this.data.courses[courseIdx].sdgs = data.sdgs.join(',');
                }

                // Re-sort courses by semester and re-render
                this.data.courses.sort((a, b) => (a.semester || 1) - (b.semester || 1) || a.course_code.localeCompare(b.course_code));
                this.render();
                modal.remove();
            } catch (error) {
                alert('Failed to save: ' + error.message);
            }
        });
    }
}
