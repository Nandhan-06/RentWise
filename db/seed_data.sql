-- RentWise Module 1: Sample seed data
-- Run after schema.sql:
--   mysql -u root -p rentwise < db/seed_data.sql

USE rentwise;

-- Demo user. Password is "changeme123" — this is a pre-computed Argon2id
-- hash of that string (Argon2 can't be computed in plain SQL, so this
-- literal is generated once via Python's argon2-cffi at seed-authoring
-- time, same as any real signup would produce it at runtime).
INSERT INTO users (name, phone, email, password_hash, role) VALUES
  ('Demo User', '9876543210', 'demo@rentwise.test',
   '$argon2id$v=19$m=65536,t=3,p=4$VAmL8w9vVYEr0WRgLuUUog$Nv88GyrGYEywNIaMaRflHdsGMUED9+x5dIy3EiTX/t8',
   'renter');

-- Amenities lookup
INSERT INTO amenities (amenity_name) VALUES
  ('Lift'), ('Power Backup'), ('Security'), ('Gym'),
  ('Swimming Pool'), ('Children Play Area'), ('Clubhouse'),
  ('Water Supply 24x7'), ('Covered Parking'), ('Pet Friendly');

-- Sample properties
INSERT INTO properties
  (title, property_type, location, city, rent, bedrooms, bathrooms, area_sqft, furnishing, parking, description, image_url, availability)
VALUES
  ('Sunrise Apartments 2BHK', 'Apartment', 'Kakkanad', 'Kochi', 18000, 2, 2, 950, 'Semi-Furnished', TRUE,
   'A well-ventilated 2BHK close to Infopark with easy access to public transport.', '/static/images/prop1.jpg', TRUE),
  ('Green Valley Villa', 'Villa', 'Kakkanad', 'Kochi', 45000, 3, 3, 1800, 'Furnished', TRUE,
   'Spacious independent villa with a private garden in a gated community.', '/static/images/prop2.jpg', TRUE),
  ('Budget Studio near Metro', 'Studio', 'Edapally', 'Kochi', 9000, 1, 1, 400, 'Unfurnished', FALSE,
   'Compact studio ideal for a single working professional, walking distance to the metro.', '/static/images/prop3.jpg', TRUE),
  ('Lakeview Independent House', 'Independent House', 'Kumbalangi', 'Kochi', 25000, 3, 2, 1400, 'Semi-Furnished', TRUE,
   'Independent house with a lake view and a quiet neighbourhood.', '/static/images/prop4.jpg', TRUE),
  ('Cozy PG for Students', 'PG', 'Vytilla', 'Kochi', 6500, 1, 1, 200, 'Furnished', FALSE,
   'Shared PG accommodation with meals included, close to major colleges.', '/static/images/prop5.jpg', TRUE),
  ('Palm Grove Apartments 3BHK', 'Apartment', 'Marine Drive', 'Kochi', 32000, 3, 2, 1300, 'Furnished', TRUE,
   'Premium apartment with a sea-facing balcony in the heart of the city.', '/static/images/prop6.jpg', TRUE),
  ('Techpark Residency 1BHK', 'Apartment', 'Infopark', 'Kochi', 12000, 1, 1, 600, 'Semi-Furnished', TRUE,
   'Ideal for IT professionals, five minutes from Infopark Phase 1.', '/static/images/prop7.jpg', TRUE),
  ('Hillside Villa', 'Villa', 'Kakkanad', 'Kochi', 55000, 4, 4, 2400, 'Furnished', TRUE,
   'Luxury 4BHK villa with a private pool and landscaped garden.', '/static/images/prop8.jpg', FALSE),
  ('Riverside Independent House', 'Independent House', 'Aluva', 'Kochi', 20000, 2, 2, 1100, 'Unfurnished', TRUE,
   'Peaceful riverside property, ten minutes from Aluva metro station.', '/static/images/prop9.jpg', TRUE),
  ('Downtown Studio Loft', 'Studio', 'MG Road', 'Kochi', 14000, 1, 1, 500, 'Furnished', FALSE,
   'Stylish studio loft above a commercial complex on MG Road.', '/static/images/prop10.jpg', TRUE);

-- Property <-> amenity links
INSERT INTO property_amenities (property_id, amenity_id) VALUES
  (1, 1), (1, 2), (1, 3),
  (2, 3), (2, 5), (2, 7), (2, 9),
  (3, 3),
  (4, 8), (4, 9),
  (5, 3), (5, 8),
  (6, 1), (6, 2), (6, 3), (6, 4),
  (7, 1), (7, 2), (7, 3), (7, 9),
  (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 6), (8, 7), (8, 9), (8, 10),
  (9, 8), (9, 9),
  (10, 3), (10, 8);
