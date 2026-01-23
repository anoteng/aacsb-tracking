-- Research and Faculty Qualification Schema
-- Run after schema_v2.sql

-- Configurable degrees (PhD, MSc, etc.)
CREATE TABLE IF NOT EXISTS degrees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Prefill degrees
INSERT IGNORE INTO degrees (name) VALUES ('PhD'), ('MSc');

-- Configurable disciplines (M, AF, DAQM, E)
CREATE TABLE IF NOT EXISTS disciplines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    shorthand VARCHAR(20) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Prefill disciplines
INSERT IGNORE INTO disciplines (name, shorthand) VALUES
    ('Management', 'M'),
    ('Accounting and Finance', 'AF'),
    ('Data Analytics and Quantitative Methods', 'DAQM'),
    ('Economics', 'E');

-- Configurable professional responsibilities
CREATE TABLE IF NOT EXISTS professional_responsibilities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    shorthand VARCHAR(20) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User discipline allocations (percentages must sum to 100)
CREATE TABLE IF NOT EXISTS user_disciplines (
    user_id INT NOT NULL,
    discipline_id INT NOT NULL,
    percentage DECIMAL(5,2) NOT NULL CHECK (percentage >= 0 AND percentage <= 100),
    PRIMARY KEY (user_id, discipline_id),
    FOREIGN KEY (user_id) REFERENCES users(uuid) ON DELETE CASCADE,
    FOREIGN KEY (discipline_id) REFERENCES disciplines(id) ON DELETE CASCADE
);

-- User professional responsibilities
CREATE TABLE IF NOT EXISTS user_responsibilities (
    user_id INT NOT NULL,
    responsibility_id INT NOT NULL,
    PRIMARY KEY (user_id, responsibility_id),
    FOREIGN KEY (user_id) REFERENCES users(uuid) ON DELETE CASCADE,
    FOREIGN KEY (responsibility_id) REFERENCES professional_responsibilities(id) ON DELETE CASCADE
);

-- User teaching productivity per academic year
CREATE TABLE IF NOT EXISTS user_teaching_productivity (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    academic_year VARCHAR(9) NOT NULL,  -- e.g., "2024-2025"
    credits DECIMAL(6,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_year (user_id, academic_year),
    FOREIGN KEY (user_id) REFERENCES users(uuid) ON DELETE CASCADE
);

-- Add new columns to users table
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS faculty_category ENUM('SA', 'PA', 'SP', 'IP', 'Other') DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS is_participating BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS participating_note TEXT,
    ADD COLUMN IF NOT EXISTS employment_percentage DECIMAL(5,2) DEFAULT 100.00,
    ADD COLUMN IF NOT EXISTS highest_degree_id INT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS degree_year INT DEFAULT NULL,
    ADD CONSTRAINT fk_users_degree FOREIGN KEY (highest_degree_id) REFERENCES degrees(id) ON DELETE SET NULL;

-- Intellectual contributions (from NVA, deduplicated by nva_id)
CREATE TABLE IF NOT EXISTS intellectual_contributions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nva_id VARCHAR(255) NOT NULL UNIQUE,
    title TEXT NOT NULL,
    year INT,
    publication_type ENUM('prj_article', 'peer_reviewed_other', 'other_ic') DEFAULT 'other_ic',
    portfolio_category ENUM('basic_discovery', 'applied_integration', 'teaching_learning') DEFAULT NULL,
    nva_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_ic_year (year),
    INDEX idx_ic_type (publication_type)
);

-- User-IC relationship with per-user categorization
CREATE TABLE IF NOT EXISTS user_intellectual_contributions (
    user_id INT NOT NULL,
    ic_id INT NOT NULL,
    publication_type ENUM('prj_article', 'peer_reviewed_other', 'other_ic') DEFAULT NULL,
    portfolio_category ENUM('basic_discovery', 'applied_integration', 'teaching_learning') DEFAULT NULL,
    societal_impact TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, ic_id),
    FOREIGN KEY (user_id) REFERENCES users(uuid) ON DELETE CASCADE,
    FOREIGN KEY (ic_id) REFERENCES intellectual_contributions(id) ON DELETE CASCADE
);

-- Professional activities (for PA/IP qualification tracking)
CREATE TABLE IF NOT EXISTS professional_activities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    year INT NOT NULL,
    activity_type VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(uuid) ON DELETE CASCADE,
    INDEX idx_pa_user_year (user_id, year)
);

-- Exemption types for qualification requirements
CREATE TABLE IF NOT EXISTS exemption_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    -- What this exemption affects
    reduces_ic_requirement BOOLEAN DEFAULT FALSE,
    reduces_prj_requirement BOOLEAN DEFAULT FALSE,
    reduces_activity_requirement BOOLEAN DEFAULT FALSE,
    grants_full_exemption BOOLEAN DEFAULT FALSE,  -- e.g., new PhD within X years
    -- How much to reduce (if applicable)
    ic_reduction INT DEFAULT 0,
    prj_reduction INT DEFAULT 0,
    activity_reduction INT DEFAULT 0,
    -- For time-based exemptions (e.g., years after degree)
    years_after_degree INT DEFAULT NULL,
    -- Grace period after exemption ends (e.g., 4 years after stepping down as Dean)
    grace_period_years INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Prefill common exemption types
-- New Doctoral Graduate: Full exemption for 6 years after earning doctorate
INSERT IGNORE INTO exemption_types (name, description, grants_full_exemption, years_after_degree) VALUES
    ('New Doctoral Graduate', 'Within 6 years of earning doctoral degree - qualifies as SA based on degree alone', TRUE, 6);

-- ABD Doctoral Student: Full exemption for 3 years (set year_from when becoming ABD, year_to = year_from + 3)
INSERT IGNORE INTO exemption_types (name, description, grants_full_exemption) VALUES
    ('ABD Doctoral Student', 'ABD doctoral students are considered SA for three years from ABD status', TRUE);

-- Administrative duties: Full exemption while serving + 4 years grace period after stepping down
INSERT IGNORE INTO exemption_types (name, description, grants_full_exemption, grace_period_years) VALUES
    ('Dean', 'Serving as Dean - maintains qualification status + 4 years after stepping down', TRUE, 4),
    ('Associate Dean', 'Serving as Associate Dean - maintains qualification status + 4 years after stepping down', TRUE, 4),
    ('Department Chair', 'Serving as Department Chair - maintains qualification status + 4 years after stepping down', TRUE, 4),
    ('Heavy Administrative Load', 'Significant administrative responsibilities - maintains qualification + 4 years after stepping down', TRUE, 4);

-- Programme Leader: Reduced requirements (not full exemption)
-- SA: 4 ICs (1 PRJ), PA: 3 activities, SP: 3 ICs (1 PRJ), IP: 3 activities
INSERT IGNORE INTO exemption_types (name, description, reduces_ic_requirement, reduces_prj_requirement, reduces_activity_requirement, ic_reduction, prj_reduction, activity_reduction) VALUES
    ('Programme Leader', 'Serving as Programme Leader - reduced requirements while serving', TRUE, TRUE, TRUE, 2, 2, 3);

INSERT IGNORE INTO exemption_types (name, description, reduces_activity_requirement, activity_reduction) VALUES
    ('Research Leave', 'On research leave - reduced professional activity requirements', TRUE, 3);

-- User exemptions (tracks which users have which exemptions)
CREATE TABLE IF NOT EXISTS user_exemptions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    exemption_type_id INT NOT NULL,
    year_from INT NOT NULL,  -- Start year of exemption
    year_to INT DEFAULT NULL,  -- End year (NULL = ongoing)
    notes TEXT,
    approved_by INT DEFAULT NULL,  -- User who approved the exemption
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(uuid) ON DELETE CASCADE,
    FOREIGN KEY (exemption_type_id) REFERENCES exemption_types(id) ON DELETE CASCADE,
    FOREIGN KEY (approved_by) REFERENCES users(uuid) ON DELETE SET NULL,
    INDEX idx_ue_user (user_id),
    INDEX idx_ue_years (year_from, year_to)
);
