-- AACSB Schema V2 - Curriculum Matrix Improvements
-- Changes I/P/R to Level (0-3) + Assessed, adds course metadata

-- =============================================
-- UPDATE GOAL-COURSE MATRIX
-- =============================================

-- Add new columns
ALTER TABLE goal_course_matrix
ADD COLUMN IF NOT EXISTS learning_level INT DEFAULT 0 COMMENT '0=None, 1=Introduced, 2=Developing, 3=Mastery',
ADD COLUMN IF NOT EXISTS is_assessed TINYINT(1) DEFAULT 0;

-- Migrate existing data (I=1, P or R=2)
UPDATE goal_course_matrix SET learning_level = 1 WHERE introduced = 1;
UPDATE goal_course_matrix SET learning_level = 2 WHERE practiced = 1 OR reinforced = 1;

-- Note: We'll keep the old columns for now, can be dropped later
-- ALTER TABLE goal_course_matrix DROP COLUMN introduced, DROP COLUMN practiced, DROP COLUMN reinforced;

-- =============================================
-- LOOKUP TABLES FOR LEARNING/ASSESSMENT METHODS
-- =============================================

CREATE TABLE IF NOT EXISTS learning_methods (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(10) NOT NULL UNIQUE,
    name_eng VARCHAR(64) NOT NULL,
    name_no VARCHAR(64),
    description TEXT,
    sort_order INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS assessment_methods (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(10) NOT NULL UNIQUE,
    name_eng VARCHAR(64) NOT NULL,
    name_no VARCHAR(64),
    description TEXT,
    sort_order INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS technologies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(10) NOT NULL UNIQUE,
    name_eng VARCHAR(64) NOT NULL,
    name_no VARCHAR(64),
    description TEXT
);

-- =============================================
-- COURSE METADATA (per programme-course)
-- =============================================

CREATE TABLE IF NOT EXISTS programme_course_metadata (
    id INT AUTO_INCREMENT PRIMARY KEY,
    programme_id INT NOT NULL,
    course_id INT NOT NULL,
    sdgs VARCHAR(255) COMMENT 'Comma-separated SDG numbers (1-17)',
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    updated_by INT,
    FOREIGN KEY (programme_id) REFERENCES study_programme(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (updated_by) REFERENCES users(uuid) ON DELETE SET NULL,
    UNIQUE KEY unique_prog_course (programme_id, course_id)
);

-- Learning methods used per course (many-to-many)
CREATE TABLE IF NOT EXISTS course_learning_methods (
    id INT AUTO_INCREMENT PRIMARY KEY,
    programme_id INT NOT NULL,
    course_id INT NOT NULL,
    method_id INT NOT NULL,
    FOREIGN KEY (programme_id) REFERENCES study_programme(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (method_id) REFERENCES learning_methods(id) ON DELETE CASCADE,
    UNIQUE KEY unique_course_method (programme_id, course_id, method_id)
);

-- Assessment methods used per course (many-to-many)
CREATE TABLE IF NOT EXISTS course_assessment_methods (
    id INT AUTO_INCREMENT PRIMARY KEY,
    programme_id INT NOT NULL,
    course_id INT NOT NULL,
    method_id INT NOT NULL,
    FOREIGN KEY (programme_id) REFERENCES study_programme(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (method_id) REFERENCES assessment_methods(id) ON DELETE CASCADE,
    UNIQUE KEY unique_course_assessment (programme_id, course_id, method_id)
);

-- Technologies used per course (many-to-many)
CREATE TABLE IF NOT EXISTS course_technologies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    programme_id INT NOT NULL,
    course_id INT NOT NULL,
    technology_id INT NOT NULL,
    FOREIGN KEY (programme_id) REFERENCES study_programme(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (technology_id) REFERENCES technologies(id) ON DELETE CASCADE,
    UNIQUE KEY unique_course_tech (programme_id, course_id, technology_id)
);

-- =============================================
-- SEED DATA - Learning Methods
-- =============================================

INSERT IGNORE INTO learning_methods (code, name_eng, name_no, sort_order) VALUES
('L', 'Lectures', 'Forelesninger', 1),
('G', 'Group work', 'Gruppearbeid', 2),
('C', 'Cases', 'Caser', 3),
('E', 'Exercises', 'Oppgaver', 4),
('FC', 'Flipped Classroom', 'Omvendt klasserom', 5),
('Pe', 'Presentations', 'Presentasjoner', 6),
('Fe', 'Feedback', 'Tilbakemelding', 7),
('PR', 'Peer Review', 'Fagfellevurdering', 8),
('Po', 'Projects', 'Prosjekter', 9),
('Ex', 'Excursions', 'Ekskursjoner', 10);

-- =============================================
-- SEED DATA - Assessment Methods
-- =============================================

INSERT IGNORE INTO assessment_methods (code, name_eng, name_no, sort_order) VALUES
('W', 'Written exam', 'Skriftlig eksamen', 1),
('D', 'Digital exam', 'Digital eksamen', 2),
('O', 'Oral exam', 'Muntlig eksamen', 3),
('TH', 'Take-home exam', 'Hjemmeeksamen', 4),
('TP', 'Term paper', 'Semesteroppgave', 5),
('WA', 'Written assignment', 'Skriftlig innlevering', 6),
('Pe', 'Presentations', 'Presentasjoner', 7),
('Po', 'Projects', 'Prosjekter', 8),
('MC', 'Multiple Choice', 'Flervalg', 9),
('E', 'Essays', 'Essays', 10),
('C', 'Cases', 'Caser', 11),
('MT', 'Master thesis', 'Masteroppgave', 12);

-- =============================================
-- SEED DATA - Technologies
-- =============================================

INSERT IGNORE INTO technologies (code, name_eng, name_no) VALUES
('R', 'R Programming', 'R-programmering'),
('AI', 'Artificial Intelligence', 'Kunstig intelligens'),
('PP', 'PowerPoint', 'PowerPoint'),
('EX', 'Excel', 'Excel'),
('PY', 'Python', 'Python'),
('ST', 'Stata', 'Stata');

-- =============================================
-- INDEXES
-- =============================================

CREATE INDEX IF NOT EXISTS idx_course_meta_prog ON programme_course_metadata(programme_id);
CREATE INDEX IF NOT EXISTS idx_course_learning_prog ON course_learning_methods(programme_id, course_id);
CREATE INDEX IF NOT EXISTS idx_course_assess_prog ON course_assessment_methods(programme_id, course_id);
