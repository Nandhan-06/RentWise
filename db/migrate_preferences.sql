-- RentWise Module 11: rental preferences on the profile page
-- Run ONCE against your existing database (safe to re-run):
--   mysql -u root -p rentwise -e "source db/migrate_preferences.sql"
--
-- Your existing users table is NOT changed - preferences live in their own
-- table, so nothing about current accounts or logins is touched.

CREATE TABLE IF NOT EXISTS user_preferences (
  user_id         INT PRIMARY KEY,
  preferred_city  VARCHAR(100)  NULL,
  min_budget      DECIMAL(10,2) NULL,
  max_budget      DECIMAL(10,2) NULL,
  bedrooms        INT           NULL,
  property_type   ENUM('Apartment','Villa','Independent House','Studio','PG') NULL,
  furnishing      ENUM('Furnished','Semi-Furnished','Unfurnished') NULL,
  needs_parking   BOOLEAN       NOT NULL DEFAULT FALSE,
  updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
