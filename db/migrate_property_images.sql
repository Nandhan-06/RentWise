-- RentWise: Property Detail page support
-- Run ONCE against your existing database (safe to re-run):
--   mysql -u root -p rentwise < db/migrate_property_images.sql
--
-- Part 1: gallery table. A property's main picture is still
-- properties.image_url; rows here are EXTRA photos shown after it.
-- A property with no rows here simply shows its single main image.
CREATE TABLE IF NOT EXISTS property_images (
  image_id     INT AUTO_INCREMENT PRIMARY KEY,
  property_id  INT NOT NULL,
  image_url    VARCHAR(500) NOT NULL,
  sort_order   INT NOT NULL DEFAULT 0,
  FOREIGN KEY (property_id) REFERENCES properties(property_id) ON DELETE CASCADE,
  INDEX idx_property_sort (property_id, sort_order)
);

-- Part 2: fix image paths. The original seed data pointed at
-- /static/images/prop1.jpg ... prop10.jpg, which don't exist. These only
-- touch rows that are empty or still use the old broken paths, so any image
-- you set yourself is left alone.
UPDATE properties SET image_url = '/static/images/properties/sunrise-apt-2bhk.png'
  WHERE title = 'Sunrise Apartments 2BHK' AND (image_url IS NULL OR image_url LIKE '/static/images/prop%.jpg');
UPDATE properties SET image_url = '/static/images/properties/green-valley-villa.png'
  WHERE title = 'Green Valley Villa' AND (image_url IS NULL OR image_url LIKE '/static/images/prop%.jpg');
UPDATE properties SET image_url = '/static/images/properties/budget-studio.avif'
  WHERE title = 'Budget Studio near Metro' AND (image_url IS NULL OR image_url LIKE '/static/images/prop%.jpg');
UPDATE properties SET image_url = '/static/images/properties/lakeview-independent.png'
  WHERE title = 'Lakeview Independent House' AND (image_url IS NULL OR image_url LIKE '/static/images/prop%.jpg');
UPDATE properties SET image_url = '/static/images/properties/cozy-pg.avif'
  WHERE title = 'Cozy PG for Students' AND (image_url IS NULL OR image_url LIKE '/static/images/prop%.jpg');
UPDATE properties SET image_url = '/static/images/properties/Palmgroove-apt-3bhk.png'
  WHERE title = 'Palm Grove Apartments 3BHK' AND (image_url IS NULL OR image_url LIKE '/static/images/prop%.jpg');
UPDATE properties SET image_url = '/static/images/properties/Techpark-residency1BHK.png'
  WHERE title = 'Techpark Residency 1BHK' AND (image_url IS NULL OR image_url LIKE '/static/images/prop%.jpg');
UPDATE properties SET image_url = '/static/images/properties/riverside-independent-house.png'
  WHERE title = 'Riverside Independent House' AND (image_url IS NULL OR image_url LIKE '/static/images/prop%.jpg');
UPDATE properties SET image_url = '/static/images/properties/downtown-studio-loft.png'
  WHERE title = 'Downtown Studio Loft' AND (image_url IS NULL OR image_url LIKE '/static/images/prop%.jpg');
-- 'Hillside Villa' has no picture file yet: clear the broken path so the
-- site shows its placeholder image instead.
UPDATE properties SET image_url = NULL
  WHERE title = 'Hillside Villa' AND image_url LIKE '/static/images/prop%.jpg';

-- To add extra gallery photos later (put the files in static/images/properties/):
-- INSERT INTO property_images (property_id, image_url, sort_order) VALUES
--   (1, '/static/images/properties/sunrise-apt-2bhk-living.png', 1);
