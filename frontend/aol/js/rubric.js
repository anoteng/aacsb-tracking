/**
 * Rubric Component
 */

class RubricComponent {
    constructor(containerId, goalId) {
        this.container = document.getElementById(containerId);
        this.goalId = goalId;
        this.rubrics = [];
        this.goal = null;
    }

    setGoal(goal) {
        this.goal = goal;
    }

    async load() {
        if (!this.container) return;

        this.container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

        try {
            this.rubrics = await api.getRubrics(this.goalId);
            this.render();
        } catch (error) {
            this.container.innerHTML = `<div class="alert alert-error">${error.message}</div>`;
        }
    }

    render() {
        const canEdit = this.goal && app.canEditGoal(this.goal);

        let html = '';

        if (canEdit) {
            html += `
                <div class="flex-between mb-2">
                    <h3>Rubrics</h3>
                    <button class="btn btn-primary btn-sm" onclick="rubricComponent.showCreateRubricModal()">
                        + Add Rubric
                    </button>
                </div>
            `;
        } else {
            html += '<h3 class="mb-2">Rubrics</h3>';
        }

        if (this.rubrics.length === 0) {
            html += `
                <div class="empty-state">
                    <h3>No rubrics defined</h3>
                    <p>Create a rubric to define assessment criteria for this goal.</p>
                </div>
            `;
        } else {
            html += this.rubrics.map(rubric => this.renderRubric(rubric, canEdit)).join('');
        }

        this.container.innerHTML = html;
    }

    renderRubric(rubric, canEdit) {
        return `
            <div class="rubric-card" data-rubric-id="${rubric.id}">
                <div class="rubric-header">
                    <div>
                        <strong>${rubric.name}</strong>
                        <span class="rubric-type">${rubric.rubric_type}</span>
                        ${!rubric.active ? '<span class="text-muted">(Inactive)</span>' : ''}
                    </div>
                    ${canEdit ? `
                        <div class="flex gap-1">
                            <button class="btn btn-sm btn-outline" onclick="rubricComponent.showAddTraitModal(${rubric.id})">
                                + Trait
                            </button>
                            <button class="btn btn-sm btn-outline" onclick="rubricComponent.showEditRubricModal(${rubric.id})">
                                Edit
                            </button>
                            <button class="btn btn-sm btn-outline" onclick="rubricComponent.showAssessmentModal(${rubric.id})">
                                Assess
                            </button>
                        </div>
                    ` : ''}
                </div>
                ${rubric.description ? `<p class="text-sm text-muted" style="padding: 0 1rem;">${rubric.description}</p>` : ''}
                ${rubric.traits.length === 0 ? `
                    <div class="trait-row text-muted text-sm">
                        No traits defined. ${canEdit ? 'Add traits to define assessment criteria.' : ''}
                    </div>
                ` : rubric.traits.map(trait => this.renderTrait(trait, canEdit)).join('')}
            </div>
        `;
    }

    renderTrait(trait, canEdit) {
        return `
            <div class="trait-row" data-trait-id="${trait.id}">
                <div class="flex-between">
                    <div class="trait-name">${trait.name}</div>
                    ${canEdit ? `
                        <div class="flex gap-1">
                            <button class="btn btn-sm btn-outline" onclick="rubricComponent.showEditTraitModal(${trait.id})">Edit</button>
                            <button class="btn btn-sm btn-danger" onclick="rubricComponent.deleteTrait(${trait.id})">Delete</button>
                        </div>
                    ` : ''}
                </div>
                ${trait.description ? `<p class="text-sm text-muted mb-1">${trait.description}</p>` : ''}
                <div class="trait-levels">
                    <div class="trait-level">
                        <div class="trait-level-header text-danger">Does Not Meet</div>
                        <div class="text-sm">${trait.level_does_not_meet || '-'}</div>
                    </div>
                    <div class="trait-level">
                        <div class="trait-level-header text-warning">Meets</div>
                        <div class="text-sm">${trait.level_meets || '-'}</div>
                    </div>
                    <div class="trait-level">
                        <div class="trait-level-header text-success">Exceeds</div>
                        <div class="text-sm">${trait.level_exceeds || '-'}</div>
                    </div>
                </div>
            </div>
        `;
    }

    showCreateRubricModal() {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h2>Create Rubric</h2>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label class="form-label">Name</label>
                        <input type="text" id="rubric-name" class="form-input" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Description</label>
                        <textarea id="rubric-description" class="form-textarea"></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Type</label>
                        <select id="rubric-type" class="form-select">
                            <option value="analytic">Analytic (multiple traits)</option>
                            <option value="holistic">Holistic (single overall assessment)</option>
                        </select>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
                    <button class="btn btn-primary" id="save-rubric-btn">Create</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.classList.add('active'));

        document.getElementById('save-rubric-btn').addEventListener('click', async () => {
            const data = {
                name: document.getElementById('rubric-name').value,
                description: document.getElementById('rubric-description').value,
                rubric_type: document.getElementById('rubric-type').value,
            };

            if (!data.name) {
                alert('Name is required');
                return;
            }

            try {
                await api.createRubric(this.goalId, data);
                modal.remove();
                this.load();
            } catch (error) {
                alert('Failed to create rubric: ' + error.message);
            }
        });
    }

    showEditRubricModal(rubricId) {
        const rubric = this.rubrics.find(r => r.id === rubricId);
        if (!rubric) return;

        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h2>Edit Rubric</h2>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label class="form-label">Name</label>
                        <input type="text" id="rubric-name" class="form-input" value="${rubric.name}" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Description</label>
                        <textarea id="rubric-description" class="form-textarea">${rubric.description || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">
                            <input type="checkbox" id="rubric-active" ${rubric.active ? 'checked' : ''}>
                            Active
                        </label>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
                    <button class="btn btn-primary" id="save-rubric-btn">Save</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.classList.add('active'));

        document.getElementById('save-rubric-btn').addEventListener('click', async () => {
            const data = {
                name: document.getElementById('rubric-name').value,
                description: document.getElementById('rubric-description').value,
                active: document.getElementById('rubric-active').checked,
            };

            try {
                await api.updateRubric(rubricId, data);
                modal.remove();
                this.load();
            } catch (error) {
                alert('Failed to update rubric: ' + error.message);
            }
        });
    }

    showAddTraitModal(rubricId) {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h2>Add Trait</h2>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label class="form-label">Trait Name</label>
                        <input type="text" id="trait-name" class="form-input" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Description</label>
                        <textarea id="trait-description" class="form-textarea"></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Does Not Meet Expectations</label>
                        <textarea id="trait-level-dnm" class="form-textarea" rows="2"></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Meets Expectations</label>
                        <textarea id="trait-level-meets" class="form-textarea" rows="2"></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Exceeds Expectations</label>
                        <textarea id="trait-level-exceeds" class="form-textarea" rows="2"></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
                    <button class="btn btn-primary" id="save-trait-btn">Add</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.classList.add('active'));

        document.getElementById('save-trait-btn').addEventListener('click', async () => {
            const data = {
                name: document.getElementById('trait-name').value,
                description: document.getElementById('trait-description').value,
                level_does_not_meet: document.getElementById('trait-level-dnm').value,
                level_meets: document.getElementById('trait-level-meets').value,
                level_exceeds: document.getElementById('trait-level-exceeds').value,
            };

            if (!data.name) {
                alert('Trait name is required');
                return;
            }

            try {
                await api.createTrait(rubricId, data);
                modal.remove();
                this.load();
            } catch (error) {
                alert('Failed to add trait: ' + error.message);
            }
        });
    }

    showEditTraitModal(traitId) {
        // Find trait across all rubrics
        let trait = null;
        for (const rubric of this.rubrics) {
            trait = rubric.traits.find(t => t.id === traitId);
            if (trait) break;
        }
        if (!trait) return;

        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h2>Edit Trait</h2>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label class="form-label">Trait Name</label>
                        <input type="text" id="trait-name" class="form-input" value="${trait.name}" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Description</label>
                        <textarea id="trait-description" class="form-textarea">${trait.description || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Does Not Meet Expectations</label>
                        <textarea id="trait-level-dnm" class="form-textarea" rows="2">${trait.level_does_not_meet || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Meets Expectations</label>
                        <textarea id="trait-level-meets" class="form-textarea" rows="2">${trait.level_meets || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Exceeds Expectations</label>
                        <textarea id="trait-level-exceeds" class="form-textarea" rows="2">${trait.level_exceeds || ''}</textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
                    <button class="btn btn-primary" id="save-trait-btn">Save</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.classList.add('active'));

        document.getElementById('save-trait-btn').addEventListener('click', async () => {
            const data = {
                name: document.getElementById('trait-name').value,
                description: document.getElementById('trait-description').value,
                level_does_not_meet: document.getElementById('trait-level-dnm').value,
                level_meets: document.getElementById('trait-level-meets').value,
                level_exceeds: document.getElementById('trait-level-exceeds').value,
            };

            try {
                await api.updateTrait(traitId, data);
                modal.remove();
                this.load();
            } catch (error) {
                alert('Failed to update trait: ' + error.message);
            }
        });
    }

    async deleteTrait(traitId) {
        if (!confirm('Are you sure you want to delete this trait?')) return;

        try {
            await api.deleteTrait(traitId);
            this.load();
        } catch (error) {
            alert('Failed to delete trait: ' + error.message);
        }
    }

    showAssessmentModal(rubricId) {
        const rubric = this.rubrics.find(r => r.id === rubricId);
        if (!rubric || rubric.traits.length === 0) {
            alert('Please add traits to the rubric before creating an assessment.');
            return;
        }

        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal" style="max-width: 800px;">
                <div class="modal-header">
                    <h2>Record Assessment - ${rubric.name}</h2>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="grid grid-2 mb-2">
                        <div class="form-group">
                            <label class="form-label">Course</label>
                            <input type="text" id="assessment-course-search" class="form-input" placeholder="Search courses...">
                            <select id="assessment-course" class="form-select hidden" style="margin-top: 0.5rem;"></select>
                            <input type="hidden" id="assessment-course-id">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Academic Year</label>
                            <select id="assessment-year" class="form-select">
                                <option value="1">2024/2025</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Notes</label>
                        <textarea id="assessment-notes" class="form-textarea" rows="2"></textarea>
                    </div>
                    <h4 class="mb-1">Results per Trait</h4>
                    <p class="text-sm text-muted mb-2">Enter the number of students at each performance level.</p>
                    ${rubric.traits.map(trait => `
                        <div class="card mb-1" data-trait="${trait.id}">
                            <strong>${trait.name}</strong>
                            <div class="grid grid-3 mt-1">
                                <div class="form-group">
                                    <label class="form-label text-danger">Does Not Meet</label>
                                    <input type="number" class="form-input trait-dnm" min="0" value="0">
                                </div>
                                <div class="form-group">
                                    <label class="form-label text-warning">Meets</label>
                                    <input type="number" class="form-input trait-meets" min="0" value="0">
                                </div>
                                <div class="form-group">
                                    <label class="form-label text-success">Exceeds</label>
                                    <input type="number" class="form-input trait-exceeds" min="0" value="0">
                                </div>
                            </div>
                        </div>
                    `).join('')}
                </div>
                <div class="modal-footer">
                    <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
                    <button class="btn btn-primary" id="save-assessment-btn">Save Assessment</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.classList.add('active'));

        // Course search
        const searchInput = document.getElementById('assessment-course-search');
        const courseSelect = document.getElementById('assessment-course');
        const courseIdInput = document.getElementById('assessment-course-id');
        let searchTimeout;

        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(async () => {
                const query = searchInput.value.trim();
                if (query.length < 2) {
                    courseSelect.classList.add('hidden');
                    return;
                }

                try {
                    const courses = await api.searchCourses(query);
                    courseSelect.innerHTML = courses.map(c =>
                        `<option value="${c.id}">${c.course_code} - ${c.name_eng || c.name_no}</option>`
                    ).join('');
                    courseSelect.classList.remove('hidden');
                } catch (error) {
                    console.error('Course search failed:', error);
                }
            }, 300);
        });

        courseSelect.addEventListener('change', () => {
            courseIdInput.value = courseSelect.value;
        });

        document.getElementById('save-assessment-btn').addEventListener('click', async () => {
            const courseId = courseIdInput.value || courseSelect.value;
            if (!courseId) {
                alert('Please select a course');
                return;
            }

            try {
                // Create assessment
                const assessment = await api.createAssessment({
                    rubric_id: rubricId,
                    course_id: parseInt(courseId),
                    academic_year_id: parseInt(document.getElementById('assessment-year').value),
                    notes: document.getElementById('assessment-notes').value,
                });

                // Add results
                const results = [];
                modal.querySelectorAll('[data-trait]').forEach(traitDiv => {
                    const traitId = parseInt(traitDiv.dataset.trait);
                    results.push({
                        trait_id: traitId,
                        count_does_not_meet: parseInt(traitDiv.querySelector('.trait-dnm').value) || 0,
                        count_meets: parseInt(traitDiv.querySelector('.trait-meets').value) || 0,
                        count_exceeds: parseInt(traitDiv.querySelector('.trait-exceeds').value) || 0,
                    });
                });

                await api.addAssessmentResults(assessment.id, results);
                modal.remove();
                alert('Assessment saved successfully!');
            } catch (error) {
                alert('Failed to save assessment: ' + error.message);
            }
        });
    }
}

let rubricComponent;
