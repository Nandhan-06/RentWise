-- RentWise Module 1: Core Database Schema
-- Run this once against a fresh MySQL 8 server:
--   mysql -u root -p < db/schema.sql

CREATE DATABASE IF NOT EXISTS rentwise
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE rentwise;

-- ---------------------------------------------------------------
-- users
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  user_id       INT AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(100)  NOT NULL,
  phone         VARCHAR(20),
  email         VARCHAR(150)  NOT NULL UNIQUE,
  password_hash VARCHAR(255)  NOT NULL,
  role          ENUM('renter','landlord') NOT NULL DEFAULT 'renter',
  created_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------
-- properties
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS properties (
  property_id     INT AUTO_INCREMENT PRIMARY KEY,
  title           VARCHAR(150)  NOT NULL,
  property_type   ENUM('Apartment','Villa','Independent House','Studio','PG') NOT NULL,
  location        VARCHAR(150)  NOT NULL,
  city            VARCHAR(100)  NOT NULL,
  rent            DECIMAL(10,2) NOT NULL,
  bedrooms        INT           NOT NULL,
  bathrooms       INT           NOT NULL,
  area_sqft       INT,
  furnishing      ENUM('Furnished','Semi-Furnished','Unfurnished') DEFAULT 'Unfurnished',
  parking         BOOLEAN       DEFAULT FALSE,
  description     TEXT,
  image_url       VARCHAR(500),
  availability    BOOLEAN       DEFAULT TRUE,
  created_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_city (city),
  INDEX idx_rent (rent),
  INDEX idx_bedrooms (bedrooms)
);

-- ---------------------------------------------------------------
-- amenities  (lookup table)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS amenities (
  amenity_id    INT AUTO_INCREMENT PRIMARY KEY,
  amenity_name  VARCHAR(100) NOT NULL UNIQUE
);

-- ---------------------------------------------------------------
-- property_amenities  (many-to-many link)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS property_amenities (
  property_id  INT NOT NULL,
  amenity_id   INT NOT NULL,
  PRIMARY KEY (property_id, amenity_id),
  FOREIGN KEY (property_id) REFERENCES properties(property_id) ON DELETE CASCADE,
  FOREIGN KEY (amenity_id)  REFERENCES amenities(amenity_id)   ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- favorites
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS favorites (
  favorite_id  INT AUTO_INCREMENT PRIMARY KEY,
  user_id      INT NOT NULL,
  property_id  INT NOT NULL,
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY unique_favorite (user_id, property_id),
  FOREIGN KEY (user_id)     REFERENCES users(user_id)         ON DELETE CASCADE,
  FOREIGN KEY (property_id) REFERENCES properties(property_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- visits
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS visits (
  visit_id     INT AUTO_INCREMENT PRIMARY KEY,
  user_id      INT NOT NULL,
  property_id  INT NOT NULL,
  visit_date   DATE NOT NULL,
  visit_time   TIME NOT NULL,
  status       ENUM('Scheduled','Completed','Cancelled') DEFAULT 'Scheduled',
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id)     REFERENCES users(user_id)         ON DELETE CASCADE,
  FOREIGN KEY (property_id) REFERENCES properties(property_id) ON DELETE CASCADE,
  INDEX idx_visit_date (property_id, visit_date)
);
