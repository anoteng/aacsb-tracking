-- AACSB Web App Schema Updates
-- Run this to add new tables and modify existing ones

-- =============================================
-- AUTHENTICATION TABLES
-- =============================================

-- Add authentication fields to users table
ALTER TABLE users
ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255) NULL,
ADD COLUMN IF NOT EXISTS google_id VARCHAR(255) NULL,
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN IF NOT EXISTS last_login TIMESTAMP NULL,
ADD COLUMN IF NOT EXISTS active TINYINT(1) DEFAULT 1;

-- Magic link tokens
CREATE TABLE IF NOT EXISTS auth_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token VARCHAR(64) NOT NULL UNIQUE,
    token_type ENUM('magic_link', 'password_reset') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(uuid) ON DELETE CASCADE,
    INDEX idx_token (token),
    INDEX idx_expires (expires_at)
);

-- Session tokens
CREATE TABLE IF NOT EXISTS sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(255) NULL,
    FOREIGN KEY (user_id) REFERENCES users(uuid) ON DELETE CASCADE,
    INDEX idx_token (token),
    INDEX idx_user (user_id)
);

-- =============================================
-- ROLES AND PERMISSIONS
-- =============================================

-- Insert roles if they don't exist
INSERT IGNORE INTO roles (role_name, role_desc, root) VALUES
('system_admin', 'Full system access to all functions', 1),
('admin_staff', 'Administrative staff - maintain course coordinators, view all AOL data', 0),
('programme_leader', 'Programme leader - edit rubrics/traits, assign staff to goals', 0),
('course_coordinator', 'Course coordinator - edit rubrics/traits for assigned courses', 0),
('staff', 'Staff member - edit rubrics/traits for assigned goals only', 0),
('dean', 'Dean - view all scientific staff (research section)', 0),
('vice_dean', 'Vice dean - view all scientific staff (research section)', 0);

-- Programme-specific roles (e.g., leader of a specific programme)
CREATE TABLE IF NOT EXISTS user_programme_roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    programme_id INT NOT NULL,
    role_id INT NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by INT NULL,
    FOREIGN KEY (user_id) REFERENCES users(uuid) ON DELETE CASCADE,
    FOREIGN KEY (programme_id) REFERENCES study_programme(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_by) REFERENCES users(uuid) ON DELETE SET NULL,
    UNIQUE KEY unique_user_programme_role (user_id, programme_id, role_id)
);

-- Course coordinators
CREATE TABLE IF NOT EXISTS course_coordinators (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    user_id INT NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by INT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(uuid) ON DELETE CASCADE,
    FOREIGN KEY (assigned_by) REFERENCES users(uuid) ON DELETE SET NULL,
    UNIQUE KEY unique_course_coordinator (course_id, user_id)
);

-- =============================================
-- AOL TABLES
-- =============================================

-- Goal-Course Matrix (I/P/R designations)
CREATE TABLE IF NOT EXISTS goal_course_matrix (
    id INT AUTO_INCREMENT PRIMARY KEY,
    goal_id INT NOT NULL,
    course_id INT NOT NULL,
    introduced TINYINT(1) DEFAULT 0,
    practiced TINYINT(1) DEFAULT 0,
    reinforced TINYINT(1) DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    updated_by INT NULL,
    FOREIGN KEY (goal_id) REFERENCES learning_goals(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (updated_by) REFERENCES users(uuid) ON DELETE SET NULL,
    UNIQUE KEY unique_goal_course (goal_id, course_id)
);

-- Staff assigned to goals (for editing rubrics)
CREATE TABLE IF NOT EXISTS goal_staff_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    goal_id INT NOT NULL,
    user_id INT NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by INT NULL,
    FOREIGN KEY (goal_id) REFERENCES learning_goals(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(uuid) ON DELETE CASCADE,
    FOREIGN KEY (assigned_by) REFERENCES users(uuid) ON DELETE SET NULL,
    UNIQUE KEY unique_goal_staff (goal_id, user_id)
);

-- Add target percentage to learning_goals
ALTER TABLE learning_goals
ADD COLUMN IF NOT EXISTS is_measured TINYINT(1) DEFAULT 0,
ADD COLUMN IF NOT EXISTS target_percentage DECIMAL(5,2) DEFAULT 80.00 COMMENT 'Target % of students meeting or exceeding expectations';

-- Rubrics (holistic or analytic)
CREATE TABLE IF NOT EXISTS rubrics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    goal_id INT NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    rubric_type ENUM('holistic', 'analytic') NOT NULL DEFAULT 'analytic',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    active TINYINT(1) DEFAULT 1,
    FOREIGN KEY (goal_id) REFERENCES learning_goals(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(uuid) ON DELETE SET NULL
);

-- Rubric traits (for analytic: multiple rows; for holistic: single row)
CREATE TABLE IF NOT EXISTS rubric_traits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rubric_id INT NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    sort_order INT DEFAULT 0,
    -- Level descriptions for each achievement level
    level_does_not_meet TEXT NULL COMMENT 'Description for "Does not meet expectations"',
    level_meets TEXT NULL COMMENT 'Description for "Meets expectations"',
    level_exceeds TEXT NULL COMMENT 'Description for "Exceeds expectations"',
    FOREIGN KEY (rubric_id) REFERENCES rubrics(id) ON DELETE CASCADE
);

-- =============================================
-- ASSESSMENT DATA
-- =============================================

-- Assessment sessions (when an assessment was conducted)
CREATE TABLE IF NOT EXISTS assessments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rubric_id INT NOT NULL,
    course_id INT NOT NULL,
    academic_year_id INT NOT NULL,
    semester_id INT NULL,
    assessment_date DATE NULL,
    total_students INT DEFAULT 0,
    notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INT NULL,
    FOREIGN KEY (rubric_id) REFERENCES rubrics(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (academic_year_id) REFERENCES acad_year(id),
    FOREIGN KEY (semester_id) REFERENCES semester(id),
    FOREIGN KEY (created_by) REFERENCES users(uuid) ON DELETE SET NULL
);

-- Assessment results per trait
CREATE TABLE IF NOT EXISTS assessment_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    assessment_id INT NOT NULL,
    trait_id INT NOT NULL,
    count_does_not_meet INT DEFAULT 0,
    count_meets INT DEFAULT 0,
    count_exceeds INT DEFAULT 0,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    FOREIGN KEY (trait_id) REFERENCES rubric_traits(id) ON DELETE CASCADE,
    UNIQUE KEY unique_assessment_trait (assessment_id, trait_id)
);

-- =============================================
-- INDEXES FOR PERFORMANCE
-- =============================================

CREATE INDEX IF NOT EXISTS idx_learning_goals_programme ON learning_goals(programme_id);
CREATE INDEX IF NOT EXISTS idx_goal_course_matrix_goal ON goal_course_matrix(goal_id);
CREATE INDEX IF NOT EXISTS idx_goal_course_matrix_course ON goal_course_matrix(course_id);
CREATE INDEX IF NOT EXISTS idx_rubrics_goal ON rubrics(goal_id);
CREATE INDEX IF NOT EXISTS idx_assessments_rubric ON assessments(rubric_id);
CREATE INDEX IF NOT EXISTS idx_assessments_course ON assessments(course_id);
