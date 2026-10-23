-- RentWise Module 9: Contact page
-- Run ONCE against your existing database (safe to re-run):
--   mysql -u root -p rentwise < db/migrate_contact.sql
--
-- To read the messages people send:
--   SELECT message_id, created_at, name, email, topic, message
--   FROM contact_messages ORDER BY created_at DESC;

CREATE TABLE IF NOT EXISTS contact_messages (
  message_id  INT AUTO_INCREMENT PRIMARY KEY,
  user_id     INT NULL,                       -- set when the sender was logged in
  name        VARCHAR(100) NOT NULL,
  email       VARCHAR(255) NOT NULL,
  topic       VARCHAR(50)  NOT NULL,
  message     TEXT NOT NULL,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
  INDEX idx_contact_created (created_at),
  INDEX idx_contact_email (email, created_at)
);
